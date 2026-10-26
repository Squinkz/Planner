"""Check inactive opening previews, cleanup and door vertex properties."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Window, Door
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    noModifiers = QtCore.Qt.KeyboardModifier.NoModifier
    leftButton = QtCore.Qt.MouseButton.LeftButton
    parent = Wall(point(-2000, 0), point(2000, 0))
    viewport.walls = [parent]
    assert list(window.viewOptions) == ["showMeasurements", "showGrid", "referenceImage", "showTips", "showFpsCounter"]
    for openingType in (Window, Door):
        kind = "door" if openingType is Door else "window"
        mime = QtCore.QMimeData()
        mime.setData(f"application/x-planner-{kind}", kind.encode())
        invalid = viewport.WorldToViewport(point(0, 1200))
        valid = viewport.WorldToViewport(point())
        enter = QtGui.QDragEnterEvent(invalid.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, leftButton, noModifiers)
        QtWidgets.QApplication.sendEvent(viewport, enter)
        for position in (invalid, valid, invalid):
            move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, leftButton, noModifiers)
            QtWidgets.QApplication.sendEvent(viewport, move)
            assert move.isAccepted()
            if position == invalid:
                assert viewport.windowDropPreview is None
                preview = viewport.inactiveOpeningPreview
                assert isinstance(preview, openingType)
                assert (preview.firstVertex + preview.secondVertex) / 2 == point(0, 1200)
                image = viewport.grab().toImage()
                region = QtCore.QRect(valid.x() - 160, invalid.y() - 200, 320, 260)
                crop = image.copy(region)
                viewport.inactiveOpeningPreview = None
                baseline = viewport.grab().toImage().copy(region)
                viewport.inactiveOpeningPreview = preview
                changedPixels = sum(crop.pixelColor(x, y) != baseline.pixelColor(x, y)
                                    for x in range(crop.width()) for y in range(crop.height()))
                assert changedPixels > 50
                if openingType is Door:
                    window.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "opening-preview.png"))
            else:
                assert isinstance(viewport.windowDropPreview, openingType)
                assert viewport.inactiveOpeningPreview is None
        drop = QtGui.QDropEvent(invalid, QtCore.Qt.DropAction.CopyAction, mime, leftButton, noModifiers)
        QtWidgets.QApplication.sendEvent(viewport, drop)
        assert not drop.isAccepted() and not viewport.windows
        assert viewport.inactiveOpeningPreview is None and viewport.windowDropPreview is None

        opening = viewport.PlaceWindow(valid, openingType)
        QtTest.QTest.mousePress(viewport, leftButton, pos = valid.toPoint())
        viewport.UpdateInteraction(invalid, noModifiers)
        assert viewport.inactiveOpeningPreview is not None
        assert opening.parentWall is parent
        viewport.UpdateInteraction(valid + point(60, 0), noModifiers)
        assert viewport.inactiveOpeningPreview is None
        assert abs(opening.length - (900 if openingType is Door else 1200)) < 0.001
        viewport.UpdateInteraction(invalid, noModifiers)
        viewport.CancelInteraction()
        assert viewport.inactiveOpeningPreview is None
        assert abs((opening.firstVertex.x() + opening.secondVertex.x()) / 2) < 0.001
        if openingType is Door:
            viewport.selectedVertex = None
            window.RefreshProperties()
            assert window.doorProperties.isVisible()
            endpoint = viewport.WorldToViewport(opening.firstVertex).toPoint()
            QtTest.QTest.mouseClick(viewport, leftButton, pos = endpoint)
            assert viewport.selectedVertex == 0 and window.doorProperties.isVisible()
            assert window.vertexProperties.isVisible()
            QtTest.QTest.mouseClick(viewport, leftButton, pos = valid.toPoint())
            assert viewport.selectedVertex is None and window.doorProperties.isVisible()
        viewport.windows = []
        viewport.selectedWall = None
        viewport.undoHistory = []
    window.close()
    print("PASS: inactive symbols, wall attachment, invalid drops, cancellation, menu and door vertex properties.")


if __name__ == "__main__":
    Main()
