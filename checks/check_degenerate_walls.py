"""Collapsed walls must not commit through dragging or property edits."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow, Wall


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.unitsMode = "Adaptive Metric"
    main.snapButton.setChecked(False)
    main.connectedOptions["vertices"].setChecked(False)
    main.connectedOptions["objects"].setChecked(False)
    point = QtCore.QPointF
    wall = Wall(point(-1000, 0), point(1000, 0), 120)
    v.walls = [wall]
    v.EnsureObjectIds()
    main.MarkProjectClean()
    original = v.CaptureState()[0]
    left = QtCore.Qt.MouseButton.LeftButton
    for index in (0, 1):
        first = v.WorldToViewport(wall.firstVertex if index == 0 else wall.secondVertex).toPoint()
        second = v.WorldToViewport(wall.secondVertex if index == 0 else wall.firstVertex).toPoint()
        QtTest.QTest.mousePress(v, left, pos = first)
        QtTest.QTest.mouseMove(v, (first + second) / 2)
        QtTest.QTest.mouseMove(v, second)
        QtTest.QTest.mouseRelease(v, left, pos = second)
        app.processEvents()
        assert v.CaptureState()[0] == original
        assert not v.undoHistory and not main.projectDirty
    # Editing endpoint coordinates through properties must reject the same case.
    v.SetSelection([(wall, 1)])
    main.propertyFields["x"].setValue(-1)
    app.processEvents()
    assert v.CaptureState()[0] == original
    assert not v.undoHistory and not main.projectDirty
    # Shared vertices can collapse another wall while the selected wall stays valid.
    neighbor = Wall(point(1000, 0), point(1000, 1000), 120)
    v.walls.append(neighbor)
    v.EnsureObjectIds()
    main.connectedOptions["vertices"].setChecked(True)
    main.MarkProjectClean()
    original = v.CaptureState()[0]
    first = v.WorldToViewport(wall.secondVertex).toPoint()
    second = v.WorldToViewport(neighbor.secondVertex).toPoint()
    QtTest.QTest.mousePress(v, left, pos = first)
    QtTest.QTest.mouseMove(v, second)
    QtTest.QTest.mouseRelease(v, left, pos = second)
    app.processEvents()
    assert v.CaptureState()[0] == original
    assert not v.undoHistory and not main.projectDirty
    # A valid edit after a rejected drag must still work normally.
    v.SetSelection([(wall, 0)])
    main.propertyFields["x"].setValue(-1.5)
    app.processEvents()
    assert wall.firstVertex == point(-1500, 0) and len(v.undoHistory) == 1 and main.projectDirty
    v.Undo()
    app.processEvents()
    assert not main.projectDirty
    main.close()
    print("PASS: collapsed endpoints and connected walls rejected without history or dirty changes; valid edits still commit.")


if __name__ == "__main__":
    Main()
