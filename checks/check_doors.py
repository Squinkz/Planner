"""Verify door drag/drop, swing controls, opening collisions and history."""

import math
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtWidgets

from check_history import Drag
from planner import MainWindow, Wall, Window, Door
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    if os.path.exists("C:/Windows/Fonts/segoeui.ttf"):
        QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.unitsMode = "Adaptive Metric"
    gridImage = viewport.grab().toImage()
    point = QtCore.QPointF
    parent = Wall(point(-2000, 0), point(2000, 0))
    viewport.walls = [parent]
    position = viewport.WorldToViewport(point(-1000, 50))
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-door", b"door")
    enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                 QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, enter)
    move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                               QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, move)
    assert move.isAccepted() and isinstance(viewport.windowDropPreview, Door)
    drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
                           QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, drop)
    assert drop.isAccepted()
    door = viewport.windows[0]
    assert isinstance(door, Door) and door.parentWall is parent
    assert door.firstVertex == point(-1450, 0) and door.secondVertex == point(-550, 0)
    assert window.selectionLabel.text() == f"Standard Door (#{door.objectId:04d})" and window.doorProperties.isVisible()
    assert not window.wallProperties.layout().isRowVisible(window.propertyFields["width"])
    viewport.Undo()
    assert not viewport.windows
    viewport.Redo()
    assert viewport.windows[0] is door
    assert viewport.PlaceWindow(position) is None
    assert viewport.PlaceWindow(position, Door) is None
    assert viewport.PlaceWindow(position + point(0, 200), Door) is None

    # Four swing combinations produce the correct leaf and curved sweep.
    for hingeAtSecond in (False, True):
        for outward in (False, True):
            if door.hingeAtSecond != hingeAtSecond:
                window.doorFields["hinge"].click()
            if door.swingsOutwards != outward:
                window.doorFields["swing"].click()
            assert door.hingeAtSecond == hingeAtSecond and door.swingsOutwards == outward
            image = viewport.grab().toImage()
            side = -1 if outward else 1
            hingeX = -550 if hingeAtSecond else -1450
            for sample in (point(hingeX, side * 570),
                           point(hingeX + (-1 if hingeAtSecond else 1) * 900 / math.sqrt(2), side * (120 + 900 / math.sqrt(2)))):
                pixel = viewport.WorldToViewport(sample).toPoint()
                colors = [image.pixelColor(pixel.x() + x, pixel.y() + y) for x in (-1, 0, 1) for y in (-1, 0, 1)]
                assert any(color.blue() > 180 and color.blue() > color.red() + 50 for color in colors)
            gap = viewport.WorldToViewport(point(-1000, 65)).toPoint()
            assert image.pixelColor(gap) == gridImage.pixelColor(gap)
    viewport.Undo()
    assert not door.swingsOutwards
    viewport.Redo()
    assert door.swingsOutwards

    # Shared collision rules reject all opening types; adjacent jambs can touch.
    other = viewport.PlaceWindow(viewport.WorldToViewport(point(600, 0)))
    assert isinstance(other, Window) and not isinstance(other, Door)
    viewport.selectedWall = door
    viewport.selectedVertex = None
    window.RefreshProperties()
    window.EditProperty("length", 2.0)
    assert QtCore.QLineF(door.secondVertex, other.firstVertex).length() < 0.001
    assert not viewport.OpeningsOverlap(door, other)
    viewport.Undo()
    assert door.secondVertex == point(-550, 0)
    window.snapButton.setChecked(False)
    start = viewport.WorldToViewport(point(-1000, 0)).toPoint()
    before = viewport.CaptureState()[3]
    Drag(viewport, start, start + QtCore.QPoint(320, 0))
    assert viewport.CaptureState()[3] == before  # Dropping the body over a window is ignored.
    viewport.selectedWall = other
    viewport.selectedVertex = 0
    endpoint = viewport.WorldToViewport(other.firstVertex).toPoint()
    Drag(viewport, endpoint, endpoint + QtCore.QPoint(-250, 0))
    assert QtCore.QLineF(other.firstVertex, door.secondVertex).length() < 0.001
    assert not viewport.OpeningsOverlap(door, other)
    viewport.Undo()

    # Crossing parents cannot create overlapping openings either.
    crossing = Wall(point(-1000, -1500), point(-1000, 1500))
    viewport.walls.append(crossing)
    assert viewport.PlaceWindow(viewport.WorldToViewport(point(-1000, 0))) is None
    viewport.walls.remove(crossing)
    # Moving or editing a parent cannot force its opening through another one.
    parallel = Wall(point(-2000, 1000), point(2000, 1000))
    viewport.walls.append(parallel)
    carried = viewport.PlaceWindow(viewport.WorldToViewport(point(-1000, 1000)))
    assert carried is not None
    beforeWalls = viewport.CaptureState()[0]
    start = viewport.WorldToViewport(point(1000, 1000)).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(0, 200))
    assert viewport.CaptureState()[0] == beforeWalls and viewport.OpeningsValid()
    viewport.selectedWall = parallel
    viewport.selectedVertex = 0
    window.EditProperty("y", 0)
    assert viewport.CaptureState()[0] == beforeWalls and viewport.OpeningsValid()
    viewport.windows.remove(carried)
    viewport.walls.remove(parallel)
    fixedLength = door.length
    parent.secondVertex = point(1000, 1500)
    parent.width = 120
    assert door.width == 120 and abs(QtCore.QLineF(door.firstVertex, door.secondVertex).length() - fixedLength) < 0.001
    viewport.selectedWall = door
    viewport.selectedVertex = None
    window.RefreshProperties()
    app.processEvents()
    window.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "doors-preview.png"))
    viewport.DeleteSelected()
    assert all(item is not door for item in viewport.windows)
    viewport.Undo()
    assert any(item is door for item in viewport.windows) and door.swingsOutwards and door.hingeAtSecond
    viewport.selectedWall = parent
    viewport.DeleteSelected()
    assert not viewport.windows
    viewport.Undo()
    assert len(viewport.windows) == 2
    window.close()
    print("PASS: door drag/drop, four swing combinations, wall constraints, opening collisions, editing and history.")


if __name__ == "__main__":
    Main()
