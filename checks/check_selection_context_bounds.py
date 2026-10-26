"""Selection gaps act as group hit areas; clipboard validity controls Paste."""
import os
import sys
import json
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Stair
from planner_app.viewport.clipboard import clipboardMimeType
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    try:
        QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
        main = MainWindow()
        main.show()
        app.processEvents()
        v = main.viewport
        v.snapEnabled = False
        v.connectedEnabled = False
        v.measurementVisibility["stairs"] = True  # Both selected classes expose the measurement action.
        point = QtCore.QPointF
        first = Wall(point(-1000, -700), point(-1000, -100), 120)
        second = Wall(point(1000, -700), point(1000, -100), 120)
        v.walls = [first, second]
        v.SetSelection([(first, None), (second, None)])
        center = v.WorldToViewport(point(0, -400))
        assert v.HitTest(center) == (second, None)
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.RightButton, pos = center.toPoint())
        labels = [action.defaultWidget().accessibleName() for action in v.objectContextMenu.actions() if not action.isSeparator()]
        assert labels == ["Subdivide Wall", "Material", "Flip Horizontal", "Flip Vertical", "Hide dimensions", "Group selected", "Transform", "Cut", "Copy", "Delete"]
        assert len(v.SelectionEntries()) == 2
        v.objectContextMenu.hide()
        # The same gap allows moving the selected group without clearing selection.
        # The center contains the rotation pivot; grab an empty part of the bounds.
        dragStart = center.toPoint() + QtCore.QPoint(50, 0)
        assert v.HitFurnishingHandle(point(dragStart)) == (None, None)
        Drag(v, dragStart, dragStart + QtCore.QPoint(0, 100))
        assert len(v.SelectionEntries()) == 2
        assert first.firstVertex == point(-1000, -1200) and second.firstVertex == point(1000, -1200), (first.firstVertex, second.firstVertex)
        v.Undo()
        assert first.firstVertex == point(-1000, -700)
        # Mixed classes retain their selection inside their combined bounds.
        stair = Stair(point(1000, -700), point(1000, -100), 120)
        v.walls = [first, stair]
        v.SetSelection([(first, None), (stair, None)])
        assert v.HitTest(center) == (stair, None)
        v.ShowObjectContextMenu(center, v.mapToGlobal(center.toPoint()))
        labels = [action.defaultWidget().accessibleName() for action in v.objectContextMenu.actions() if not action.isSeparator()]
        assert labels == ["Flip Horizontal", "Flip Vertical", "Hide dimensions", "Group selected", "Transform", "Cut", "Copy", "Delete"] and len(v.SelectionEntries()) == 2, labels
        v.objectContextMenu.hide()
        outside = v.WorldToViewport(point(0, 900))
        assert v.HitTest(outside) == (None, None)
        # Clipboard inspection must not modify the scene or selection.
        for data in (None, b'not json', json.dumps({"version": 1, "center": [0, 0], "objects": [{"type": "Wall", "selected": True}]}).encode()):
            app.clipboard().clear()
            if data is not None:
                mime = QtCore.QMimeData()
                mime.setData(clipboardMimeType, data)
                app.clipboard().setMimeData(mime)
            before = v.CaptureState()
            v.ShowObjectContextMenu(outside, v.mapToGlobal(outside.toPoint()))
            button = v.objectContextMenu.actions()[0].defaultWidget()
            assert button.accessibleName() == "Paste" and not button.isEnabled()
            assert v.CaptureState() == before
            v.objectContextMenu.hide()
        app.clipboard().setText("ordinary text")
        assert v.ReadClipboardSelection() is None
        assert v.CopySelection() and v.ReadClipboardSelection() is not None
        v.ShowObjectContextMenu(outside, v.mapToGlobal(outside.toPoint()))
        assert v.objectContextMenu.actions()[0].defaultWidget().isEnabled()
        v.objectContextMenu.hide()
        main.ShowHeaderMenu("Edit")
        assert main.menuButtons["Paste"].isEnabled()
        main.editMenu.hide()
        app.clipboard().clear()
        main.ShowHeaderMenu("Edit")
        assert not main.menuButtons["Paste"].isEnabled()
        main.close()
        print("PASS: selection bbox gaps, group drag, mixed context, outside void and valid/invalid clipboard menu states.")
    finally:
        app.clipboard().clear()
        app.processEvents()


if __name__ == "__main__":
    Main()
