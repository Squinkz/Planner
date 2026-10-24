"""Furnishing context menu, overlap picking, paint order and history."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow
from furnishings import Furnishing, LoadFurnishings
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
    definitions = {item["key"]: item for item in LoadFurnishings()}
    back = Furnishing(definitions["null"])
    front = Furnishing(definitions["desk"])
    viewport.furnishings = [back, front]
    viewport.SetSelection([(front, None)])
    center = viewport.WorldToViewport(QtCore.QPointF()).toPoint()
    originalImage = viewport.grab().toImage()
    assert viewport.HitTest(center)[0] is front
    QtTest.QTest.mouseClick(viewport, QtCore.Qt.MouseButton.RightButton,
                           QtCore.Qt.KeyboardModifier.NoModifier, center)
    app.processEvents()
    assert viewport.pendingWall is None
    menu = viewport.furnishingContextMenu
    assert menu.isVisible()
    buttons = [action.defaultWidget() for action in menu.actions() if not action.isSeparator()]
    assert [button.accessibleName() for button in buttons] == ["Bring to Front", "Move to Back", "Flip Horizontal", "Flip Vertical", "Transform", "Cut", "Copy", "Delete"]
    assert all(not button.iconLabel.pixmap().isNull() for button in buttons)
    QtTest.QTest.mouseClick(next(button for button in buttons if button.accessibleName() == "Move to Back"),
                           QtCore.Qt.MouseButton.LeftButton)
    app.processEvents()
    assert viewport.furnishings == [front, back]
    assert viewport.HitTest(center)[0] is front
    assert viewport.grab().toImage() != originalImage
    viewport.Undo()
    assert viewport.furnishings == [back, front]
    assert viewport.grab().toImage() == originalImage
    viewport.Redo()
    assert viewport.furnishings == [front, back]
    viewport.MoveFurnishingLayer(front, True)
    assert viewport.furnishings == [back, front]
    historyCount = len(viewport.undoHistory)
    viewport.MoveFurnishingLayer(front, True)
    assert len(viewport.undoHistory) == historyCount
    window.close()
    print("PASS: furnishing context actions reorder painting/picking, undo/redo and no-op history.")


if __name__ == "__main__":
    Main()
