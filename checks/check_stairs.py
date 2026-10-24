"""Stair drag/drop, properties, collision constraints, joins, direction and history."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Stair, Wall, Window
from theme import BuildStyle
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas")  # Fixed palette for pixel assertions.
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.unitsMode = "Adaptive Metric"  # The UI assertions use meters and centimeters.
    point = QtCore.QPointF
    window.snapButton.setChecked(False)
    assert window.stairButton.toolTip() == "Stair" and not window.stairButton.icon().isNull()
    position = viewport.WorldToViewport(point())
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-stair", b"stair")
    enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                 QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, enter)
    assert enter.isAccepted()
    move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                               QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, move)
    assert isinstance(viewport.windowDropPreview, Stair)
    viewport.grab()
    drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
                           QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, drop)
    assert drop.isAccepted() and len(viewport.walls) == 1
    stair = viewport.walls[0]
    assert stair.width == 1000 and stair.stepCount == 4 and stair.stepSize == 250
    assert stair.firstVertex == point(-500, 0) and stair.secondVertex == point(500, 0)
    assert window.selectionLabel.text() == f"Stair (#{stair.objectId:04d})"
    assert isinstance(window.stepSizeLabel, QtWidgets.QLabel) and window.stepSizeLabel.text() == "25.00 cm"
    assert not window.wallProperties.layout().isRowVisible(window.materialField)
    assert isinstance(window.stepCountLabel, QtWidgets.QLabel) and window.stepCountLabel.text() == "4"
    window.propertyFields["length"].setValue(2)
    assert stair.stepCount == 7 and abs(stair.stepSize - 2000 / 7) < 1e-8
    viewport.Undo()
    assert stair.stepCount == 4 and stair.stepSize == 250
    window.propertyFields["width"].setValue(.8)
    assert stair.width == 800
    viewport.Undo()
    assert stair.width == 1000
    # Stair overlap is allowed; walls still block placement and movement.
    assert viewport.PlaceStair(position) is not None
    viewport.Undo()
    obstacle = Wall(point(-500, 1000), point(1500, 1000), 240)
    viewport.walls.append(obstacle)
    assert viewport.PlaceStair(viewport.WorldToViewport(point(0, 900))) is None
    before = viewport.CaptureState()
    Drag(viewport, position.toPoint(), position.toPoint() + QtCore.QPoint(0, -180))
    assert stair.firstVertex == point(-500, 0)
    assert viewport.CaptureState()[0] == before[0]
    # Existing walls also cannot move or be constructed through a stair.
    wallCenter = viewport.WorldToViewport(point(700, 1000)).toPoint()
    Drag(viewport, wallCenter, wallCenter + QtCore.QPoint(0, 200))
    assert obstacle.firstVertex == point(-500, 1000)
    count = len(viewport.walls)
    Drag(viewport, viewport.WorldToViewport(point(-1000, 0)).toPoint(),
         viewport.WorldToViewport(point(1000, 0)).toPoint(), button = QtCore.Qt.MouseButton.RightButton)
    assert len(viewport.walls) == count
    viewport.selectedWall, viewport.selectedVertex = stair, None
    window.RefreshProperties()
    window.propertyFields["width"].setValue(3)
    assert stair.width == 1000
    # Ctrl constrains translation without changing the arrow direction.
    start = viewport.WorldToViewport(point(0, 0)).toPoint()
    original = (point(stair.firstVertex), point(stair.secondVertex))
    Drag(viewport, start, start + QtCore.QPoint(-60, 0), QtCore.Qt.KeyboardModifier.ControlModifier)
    assert not stair.directionReversed and stair.firstVertex.x() < original[0].x()
    assert stair.firstVertex.y() == original[0].y()
    assert stair.secondVertex - stair.firstVertex == original[1] - original[0]
    viewport.Undo()
    assert not stair.directionReversed
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    viewport.UpdateInteraction(point(start + QtCore.QPoint(-60, 0)), QtCore.Qt.KeyboardModifier.ControlModifier)
    viewport.CancelInteraction()
    assert not stair.directionReversed
    # Stairs never act as host walls for windows or doors.
    viewport.walls.remove(obstacle)
    assert viewport.FindWindowPlacement(position, openingType = Window) is None
    joined = viewport.PlaceStair(viewport.WorldToViewport(point(1000, 0)))
    assert joined is not None and joined.firstVertex == stair.secondVertex
    path = viewport.ConnectedStairPath([stair, joined])
    assert path.contains(viewport.WorldToViewport(point(500, 0)))
    assert viewport.OpeningsValid()
    viewport.selectedWall, viewport.selectedVertex = stair, 0
    window.RefreshProperties()
    assert window.vertexProperties.isVisible() and not window.vertexProperties.layout().isRowVisible(window.propertyFields["miter"])
    window.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "stairs.png"))
    viewport.DeleteSelected()
    assert stair not in viewport.walls
    viewport.Undo()
    assert any(wall is stair for wall in viewport.walls)
    # Vertex movement changes the oriented run and recalculates tread depth.
    vertex = viewport.WorldToViewport(stair.firstVertex).toPoint()
    Drag(viewport, vertex, vertex + QtCore.QPoint(-100, 0))
    assert stair.firstVertex == point(-1000, 0) and stair.stepSize == 300 and stair.stepCount == 5
    viewport.Undo()
    assert stair.firstVertex == point(-500, 0)
    # Grid is masked inside the stair footprint between the treads.
    viewport.selectedWall, viewport.selectedVertex = None, None
    image = viewport.grab().toImage()
    sample = viewport.WorldToViewport(point(-400, 100)).toPoint()
    assert image.pixelColor(sample).name() == "#0e0e0e"
    # Shift copies a stair's steps and direction without moving its neighbors.
    start = viewport.WorldToViewport(point()).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(0, 200), QtCore.Qt.KeyboardModifier.ShiftModifier)
    copy = viewport.selectedWall
    assert isinstance(copy, Stair) and copy is not stair and copy.stepCount == stair.stepCount
    assert copy.directionReversed == stair.directionReversed and len(viewport.walls) == 3
    viewport.Undo()
    # Broad bounding rectangles may overlap without oriented footprints colliding.
    rotated = Stair(point(-500, -500), point(500, 500), 200)
    parallel = Stair(point(-1000, 0), point(0, 1000), 200)
    assert not viewport.ObjectsOverlap(rotated, parallel)
    assert viewport.ObjectsOverlap(rotated, Stair(point(-500, 500), point(500, -500), 200))
    # A corner join has a continuous outline and stable geometry during panning.
    corner = Stair(point(1500, 0), point(1500, -1000))
    viewport.walls.append(corner)
    assert viewport.OpeningsValid()
    viewport.grab()
    cacheKey = viewport.stairGeometryKey
    viewport.panOffset += point(12, 15)
    viewport.zoom = .8
    viewport.grab()
    assert viewport.stairGeometryKey == cacheKey
    viewport.selectedWall, viewport.selectedVertex = stair, 0
    window.RefreshProperties()
    app.processEvents()
    assert window.buildScrollArea.verticalScrollBar().maximum() > 0
    window.buildScrollArea.ensureWidgetVisible(window.vertexProperties)
    app.processEvents()
    assert window.propertyFields["width"].height() >= window.propertyFields["width"].minimumSizeHint().height()
    window.close()
    print("PASS: Stair native placement, properties, derived steps, OBB collisions, joined stairs, Ctrl direction, cancellation, deletion and history.")


if __name__ == "__main__":
    Main()
