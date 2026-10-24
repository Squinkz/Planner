"""Verify pocket door footprint, controls, native placement and flipping."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Door, SlidingDoor, PocketDoor, Window, DrawOpeningSymbol
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas")  # Fixed palette for pixel assertions.
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.unitsMode = "Adaptive Metric"
    point = QtCore.QPointF
    wall = Wall(point(-3000, 0), point(3000, 0))
    viewport.walls = [wall]
    center = viewport.WorldToViewport(point())
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-pocket-door", b"pocket-door")
    left = QtCore.Qt.MouseButton.LeftButton
    none = QtCore.Qt.KeyboardModifier.NoModifier
    enter = QtGui.QDragEnterEvent(center.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, left, none)
    QtWidgets.QApplication.sendEvent(viewport, enter)
    move = QtGui.QDragMoveEvent(center.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, left, none)
    QtWidgets.QApplication.sendEvent(viewport, move)
    assert isinstance(viewport.windowDropPreview, PocketDoor)
    drop = QtGui.QDropEvent(center, QtCore.Qt.DropAction.CopyAction, mime, left, none)
    QtWidgets.QApplication.sendEvent(viewport, drop)
    assert drop.isAccepted()
    door = viewport.windows[0]
    assert abs(door.length - 1800) < .01 and window.propertyFields["doorSize"].value() == .9
    form = window.wallProperties.layout()
    assert form.isRowVisible(window.propertyFields["doorSize"])
    assert not form.isRowVisible(window.propertyFields["length"])
    assert not form.isRowVisible(window.propertyFields["width"])
    assert not window.doorProperties.layout().isRowVisible(window.doorFields["swing"])
    assert window.doorProperties.layout().labelForField(window.doorFields["hinge"]).text() == "Pocket side"
    window.propertyFields["doorSize"].setValue(.8)
    assert abs(door.length - 1600) < .01
    for openingType in (Window, Door, SlidingDoor, PocketDoor):
        assert viewport.PlaceWindow(center, openingType) is None
    window.doorFields["hinge"].click()
    assert door.hingeAtSecond
    viewport.Undo()
    assert not door.hingeAtSecond
    viewport.Redo()
    assert door.hingeAtSecond
    # Ctrl chooses only the longitudinal axis; north/south must not add a flip.
    midpoint = (door.firstVertex + door.secondVertex) / 2
    for x, y in ((-600, 600), (-600, -600), (600, 600), (600, -600)):
        viewport.OrientDoor(door, viewport.WorldToViewport(midpoint + point(x, y)))
        assert door.hingeAtSecond == (x > 0)
        assert not hasattr(door, "swingsOutwards") and not hasattr(door, "panelsFlipped")
    door.hingeAtSecond = False
    viewport.selectedVertex = 0
    window.RefreshProperties()
    assert window.vertexProperties.isVisible() and not window.propertyFields["length"].isVisible()
    app.processEvents()
    window.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "pocket-door-preview.png"))
    before = viewport.CaptureState()
    wall.secondVertex += point(1000, 300)
    assert viewport.FitWallOpenings(before) and abs(door.length - 1600) < .01
    viewport.DeleteSelected()
    assert not viewport.windows
    viewport.Undo()
    assert viewport.windows[0] is door
    # The 20 mm lip scales with zoom, and is independent of the door's length.
    for screenLength, scale in ((200, .2), (400, .2), (400, .4)):
        image = QtGui.QImage(500, 200, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        DrawOpeningSymbol(painter, point(20, 100), point(20 + screenLength, 100), 40,
                          PocketDoor, pixelsPerMillimeter = scale)
        painter.end()
        panelStart = 20 + screenLength / 2 - 20 * scale
        assert image.pixelColor(int(panelStart + 2), 103).name() == "#0e0e0e"
        assert image.pixelColor(int(panelStart - 2), 103).alpha() == 0
        assert image.pixelColor(int(panelStart + 20), 112).alpha() == 0
        cutX = int(20 + screenLength / 2)
        assert image.pixelColor(cutX, 86).alpha() > 0
        assert image.pixelColor(cutX, 114).alpha() > 0
    window.close()
    print("PASS: pocket drag/drop, double footprint, size editing, collision bounds, flip/history, Ctrl axis and parent movement.")


if __name__ == "__main__":
    Main()
