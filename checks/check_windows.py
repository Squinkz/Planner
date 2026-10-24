"""Verify wall-bound windows, drag/drop, editing, rendering and history."""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from check_history import Drag
from planner import MainWindow, Wall, Window
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    if os.path.exists("C:/Windows/Fonts/segoeui.ttf"):
        QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas")
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.unitsMode = "Adaptive Metric"
    viewport.unitsMode = "Adaptive Metric"  # Opening length edits below use meters.
    point = QtCore.QPointF
    source = Wall(point(-2000, 0), point(2000, 0))
    viewport.walls = [source]
    position = viewport.WorldToViewport(point(0, 80))
    center = viewport.WorldToViewport(point())
    assert viewport.PlaceWindow(center + point(0, 180)) is None
    assert not viewport.windows and not viewport.undoHistory

    # Exercise the viewport's native MIME drag/drop events and valid preview.
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-window", b"window")
    enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                  QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, enter)
    assert enter.isAccepted()
    move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, move)
    assert move.isAccepted() and viewport.windowDropPreview is not None
    drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
                            QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, drop)
    assert drop.isAccepted() and viewport.windowDropPreview is None
    opening = viewport.windows[0]
    assert isinstance(opening, Window) and opening.parentWall is source
    assert opening.firstVertex == point(-600, 0) and opening.secondVertex == point(600, 0)
    assert window.selectionLabel.text() == f"Standard Window (#{opening.objectId:04d})" and window.propertyFields["width"].isReadOnly()
    assert not window.wallProperties.layout().isRowVisible(window.sizeRow)
    viewport.selectedWall = source
    window.RefreshProperties()
    assert window.wallProperties.layout().isRowVisible(window.sizeRow)
    viewport.selectedWall = opening
    window.RefreshProperties()
    viewport.Undo()
    assert not viewport.windows
    viewport.Redo()
    assert viewport.windows[0] is opening

    # A window's opening is clear, with seams and a bar toward its facing side.
    image = viewport.grab().toImage()
    blank = viewport.WorldToViewport(point(0, 65)).toPoint()
    assert image.pixelColor(blank).name() == "#0e0e0e"
    crossbar = viewport.WorldToViewport(point(0, -source.width * .175 + 20)).toPoint()
    assert image.pixelColor(crossbar).blue() > 160
    seam = viewport.WorldToViewport(point(-600, 65)).toPoint()
    assert image.pixelColor(seam).blue() > 160

    # Body movement is collinear, preserves length, and clamps at wall bounds.
    Drag(viewport, center.toPoint(), center.toPoint() + QtCore.QPoint(350, -20))
    assert opening.secondVertex == source.secondVertex
    assert abs(QtCore.QLineF(opening.firstVertex, opening.secondVertex).length() - 1200) < 0.001
    assert opening.firstVertex.y() == opening.secondVertex.y() == 0
    viewport.Undo()
    assert opening.firstVertex == point(-600, 0)
    endpoint = viewport.WorldToViewport(opening.secondVertex).toPoint()
    Drag(viewport, endpoint, endpoint + QtCore.QPoint(350, -70))
    assert opening.secondVertex == source.secondVertex and opening.firstVertex == point(-600, 0)
    viewport.Undo()
    viewport.selectedWall = opening
    viewport.selectedVertex = None
    window.EditProperty("length", 0.8)
    assert opening.secondVertex == point(200, 0)
    viewport.Undo()
    before = viewport.CaptureState()
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = center.toPoint())
    viewport.UpdateInteraction(center + point(60, 5), QtCore.Qt.KeyboardModifier.NoModifier)
    viewport.CancelInteraction()
    assert viewport.CaptureState()[3] == before[3]

    # Windows follow wall translation, rotation, length and inherited width,
    # regardless of Connected options. Normalized positions cannot overrun it.
    fixedLength = opening.length
    window.snapButton.setChecked(False)
    window.connectedOptions["vertices"].setChecked(False)
    window.connectedOptions["objects"].setChecked(False)
    wallBody = viewport.WorldToViewport(point(-1600, 0)).toPoint()
    Drag(viewport, wallBody, wallBody + QtCore.QPoint(40, -20))
    assert opening.firstVertex == point(-400, 100)
    viewport.Undo()
    source.secondVertex = point(1000, 1500)
    source.width = 120
    assert opening.width == 120 and abs(QtCore.QLineF(opening.firstVertex, opening.secondVertex).length() - fixedLength) < 0.001
    direction = source.secondVertex - source.firstVertex
    offset = opening.firstVertex - source.firstVertex
    assert abs(offset.x() * direction.y() - offset.y() * direction.x()) < 0.001
    assert 0 <= opening.firstFraction < opening.secondFraction <= 1

    # Short parents fit the opening; invalid placement does not add history.
    short = Wall(point(100, -1000), point(600, -1000), 120)
    viewport.walls.append(short)
    viewport.selectedWall = opening
    viewport.selectedVertex = None
    windowCenter = viewport.WorldToViewport((opening.firstVertex + opening.secondVertex) / 2).toPoint()
    shortCenter = viewport.WorldToViewport(point(350, -1000)).toPoint()
    Drag(viewport, windowCenter, shortCenter)
    assert opening.parentWall is short and abs(opening.length - 500) < 0.001
    assert opening.firstVertex == short.firstVertex and opening.secondVertex == short.secondVertex
    viewport.Undo()
    assert opening.parentWall is source and abs(opening.length - fixedLength) < 0.001
    viewport.Redo()
    assert opening.parentWall is short and abs(opening.length - 500) < 0.001
    viewport.Undo()
    small = viewport.PlaceWindow(viewport.WorldToViewport(point(350, -1000)))
    assert small.parentWall is short and small.firstFraction == 0 and small.secondFraction == 1
    historyCount = len(viewport.undoHistory)
    assert viewport.PlaceWindow(center + point(0, -250)) is None
    assert len(viewport.undoHistory) == historyCount
    viewport.DeleteSelected()
    assert all(item is not small for item in viewport.windows)
    viewport.Undo()
    assert any(item is small for item in viewport.windows)
    viewport.selectedWall = short
    viewport.DeleteSelected()
    assert all(item.parentWall is not short for item in viewport.windows)
    viewport.Undo()
    assert any(item is small for item in viewport.windows)

    # The button produces a native copy drag after the normal drag threshold.
    class DragRecorder(QtCore.QObject):
        def __init__(self, sourceWidget):
            super().__init__()
            self.source = sourceWidget

        def setMimeData(self, mimeData):
            self.mime = mimeData

        def setPixmap(self, pixmap):
            assert not pixmap.isNull()
            self.pixmap = pixmap

        def setHotSpot(self, hotSpot):
            pass

        def exec(self, action):
            assert self.source is window.windowButton
            assert self.mime.hasFormat("application/x-planner-window")
            assert action == QtCore.Qt.DropAction.CopyAction
            image = self.pixmap.toImage()
            assert image.size() == QtCore.QSize(1, 1) and image.pixelColor(0, 0).alpha() == 0
            return action

    button = window.windowButton
    QtTest.QTest.mousePress(button, QtCore.Qt.MouseButton.LeftButton, pos = button.rect().center())
    with patch("planner.QtGui.QDrag", DragRecorder):
        localPosition = point(button.rect().center() + QtCore.QPoint(30, 0))
        event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, localPosition, point(button.mapToGlobal(localPosition.toPoint())),
                                 QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.LeftButton,
                                 QtCore.Qt.KeyboardModifier.NoModifier)
        button.mouseMoveEvent(event)
    assert button.pressPosition is None
    viewport.selectedWall = opening
    viewport.selectedVertex = None
    window.RefreshProperties()
    app.processEvents()
    window.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "windows-preview.png"))
    window.close()
    print("PASS: native window drag/drop, invalid drops, bounds, H rendering, selection, movement, editing, parent changes, deletion and history.")


if __name__ == "__main__":
    Main()
