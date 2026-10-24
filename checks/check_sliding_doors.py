"""Verify sliding door placement, linked sizes, orientation and history."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Window, Door, SlidingDoor, DrawOpeningSymbol
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas")
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.unitsMode = "Adaptive Metric"
    point = QtCore.QPointF
    wall = Wall(point(-3000, 0), point(3000, 0))
    viewport.walls = [wall]
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-sliding-door", b"sliding-door")
    center = viewport.WorldToViewport(point())
    left = QtCore.Qt.MouseButton.LeftButton
    none = QtCore.Qt.KeyboardModifier.NoModifier
    enter = QtGui.QDragEnterEvent(center.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, left, none)
    QtWidgets.QApplication.sendEvent(viewport, enter)
    move = QtGui.QDragMoveEvent(center.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, left, none)
    QtWidgets.QApplication.sendEvent(viewport, move)
    assert isinstance(viewport.windowDropPreview, SlidingDoor)
    drop = QtGui.QDropEvent(center, QtCore.Qt.DropAction.CopyAction, mime, left, none)
    QtWidgets.QApplication.sendEvent(viewport, drop)
    assert drop.isAccepted()
    door = viewport.windows[0]
    assert abs(door.length - 1800) < .01 and not hasattr(door, "swingsOutwards")
    assert window.selectionLabel.text().startswith("Sliding Door (#")
    assert window.propertyFields["doorSize"].value() == .9
    assert window.doorProperties.layout().isRowVisible(window.doorFields["swing"])
    assert window.doorProperties.layout().labelForField(window.doorFields["swing"]).text() == "Panel side"
    assert window.doorProperties.layout().labelForField(window.doorFields["hinge"]).text() == "Slide direction"
    window.propertyFields["doorSize"].setValue(.7)
    assert abs(door.length - 1400) < .01 and window.propertyFields["length"].value() == 1.4
    window.propertyFields["length"].setValue(1.6)
    assert abs(door.length - 1600) < .01 and window.propertyFields["doorSize"].value() == .8
    window.doorFields["hinge"].click()
    assert door.hingeAtSecond
    viewport.Undo()
    assert not door.hingeAtSecond
    viewport.Redo()
    assert door.hingeAtSecond
    window.doorFields["swing"].click()
    assert door.panelsFlipped
    viewport.Undo()
    assert not door.panelsFlipped
    viewport.Redo()
    assert door.panelsFlipped
    # Ctrl fixes the opening while choosing both independent orientation axes.
    center = viewport.WorldToViewport((door.firstVertex + door.secondVertex) / 2)
    original = (point(door.firstVertex), point(door.secondVertex))
    QtTest.QTest.mousePress(viewport, left, pos = center.toPoint())
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    for x, y in ((600, 600), (-600, 600), (-600, -600), (600, -600)):
        cursor = center + point(x * .2, -y * .2)
        viewport.UpdateInteraction(cursor, ctrl)
        assert (door.firstVertex, door.secondVertex) == original
        assert door.hingeAtSecond == (x < 0)
        assert door.panelsFlipped == (y < 0)
        orientationImage = QtGui.QImage(260, 200, QtGui.QImage.Format.Format_ARGB32)
        orientationImage.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(orientationImage)
        DrawOpeningSymbol(painter, point(20, 100), point(220, 100), 40, SlidingDoor,
                          door.hingeAtSecond, panelsFlipped = door.panelsFlipped)
        painter.end()
        firstPanelBelow = door.hingeAtSecond == door.panelsFlipped
        assert (orientationImage.pixelColor(60, 113).alpha() == 255) == firstPanelBelow
        # The arrow points opposite cursor east/west; north/south determines its gap.
        arrowY = 68 if y > 0 else 132
        tipX = 218 if x < 0 else 22
        assert orientationImage.pixelColor(tipX, arrowY).alpha() > 0
        tailRange = range(145, 195) if x < 0 else range(45, 95)
        tailPixels = [orientationImage.pixelColor(pixelX, arrowY).alpha() > 0 for pixelX in tailRange]
        assert all(tailPixels)
        travelY = 83 if y > 0 else 117
        travelPixels = [orientationImage.pixelColor(pixelX, travelY).alpha() > 0 for pixelX in tailRange]
        assert any(travelPixels) and not all(travelPixels)
    viewport.UpdateInteraction(cursor, none)
    assert (door.firstVertex, door.secondVertex) == original
    viewport.CancelInteraction()
    assert door.hingeAtSecond and door.panelsFlipped
    # Panels overlap by 10% of the opening and remain opaque, with inset edges.
    image = QtGui.QImage(260, 200, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    DrawOpeningSymbol(painter, point(20, 100), point(220, 100), 40, SlidingDoor)
    painter.end()
    assert image.pixelColor(125, 108).alpha() == 255
    assert image.pixelColor(115, 92).alpha() == 255
    assert image.pixelColor(50, 119).alpha() == 0
    assert image.pixelColor(22, 83).alpha() > 0
    assert image.pixelColor(125, 108).name() == "#0e0e0e"
    # Reversing travel mirrors the complete symbol along the wall.
    reversedImage = QtGui.QImage(260, 200, QtGui.QImage.Format.Format_ARGB32)
    reversedImage.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(reversedImage)
    DrawOpeningSymbol(painter, point(20, 100), point(220, 100), 40, SlidingDoor, True)
    painter.end()
    assert reversedImage.pixelColor(115, 108) == image.pixelColor(125, 108)
    assert reversedImage.pixelColor(125, 92) == image.pixelColor(115, 92)
    assert reversedImage.pixelColor(218, 83).alpha() > 0
    assert reversedImage.pixelColor(70, 92).alpha() == 255  # Mirrored panel, not the arrow.
    image.save(str(Path(__file__).resolve().parent.parent / "screenshots" / "sliding-door-symbol.png"))
    for openingType in (Window, Door, SlidingDoor):
        assert viewport.PlaceWindow(center, openingType) is None
    assert viewport.PlaceWindow(viewport.WorldToViewport(point(0, 1500)), SlidingDoor) is None
    app.processEvents()
    window.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "sliding-door-preview.png"))
    viewport.selectedVertex = 0
    window.RefreshProperties()
    assert window.vertexProperties.isVisible() and window.propertyFields["doorSize"].isVisible()
    originalLength = door.length
    before = viewport.CaptureState()
    wall.secondVertex += point(1000, 300)
    assert viewport.FitWallOpenings(before) and abs(door.length - originalLength) < .01
    viewport.DeleteSelected()
    assert not viewport.windows
    viewport.Undo()
    assert viewport.windows[0] is door and door.hingeAtSecond
    window.close()
    print("PASS: sliding drag/drop, linked dimensions, direction flip, collisions, vertex properties, fixed length and history.")


if __name__ == "__main__":
    Main()
