"""Right dragging draws walls with normal snapping, history and cancellation."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    right = QtCore.Qt.MouseButton.RightButton
    start = viewport.WorldToViewport(QtCore.QPointF()).toPoint()
    end = start + QtCore.QPoint(200, 0)
    QtTest.QTest.mousePress(viewport, right, pos = start)
    assert viewport.pendingWall is None and viewport.rightClickStart is not None
    assert not viewport.objectContextMenu.isVisible()
    QtTest.QTest.mouseMove(viewport, end)
    assert viewport.pendingWall is not None and viewport.mode == "Wall"
    # A different button's release must not complete right-button construction.
    QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.LeftButton, pos = end)
    assert viewport.pendingWall is not None and not viewport.walls
    QtTest.QTest.mouseRelease(viewport, right, pos = end)
    assert len(viewport.walls) == 1 and viewport.mode == "Select"
    wall = viewport.walls[0]
    assert wall.firstVertex == QtCore.QPointF() and wall.secondVertex == QtCore.QPointF(1000, 0)
    viewport.Undo()
    assert not viewport.walls
    viewport.Redo()
    assert viewport.walls == [wall]
    # Branch from an existing vertex and inherit its miter.
    wall.secondMiter = .4
    QtTest.QTest.mousePress(viewport, right, pos = end)
    QtTest.QTest.mouseMove(viewport, end + QtCore.QPoint(0, -50))
    assert viewport.pendingWall.firstVertex == wall.secondVertex
    assert viewport.pendingWall.firstMiter == .4
    QtTest.QTest.mouseRelease(viewport, right, pos = end + QtCore.QPoint(0, -100))
    assert len(viewport.walls) == 2
    QtTest.QTest.mousePress(viewport, right, pos = start)
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Escape)
    assert viewport.pendingWall is None and viewport.mode == "Select"
    QtTest.QTest.mouseRelease(viewport, right, pos = end)
    assert len(viewport.walls) == 2
    QtTest.QTest.mouseClick(viewport, right, pos = start)
    assert len(viewport.walls) == 2
    viewport.objectContextMenu.hide()
    # Left-click cancels every shape; subsequent motion and button releases
    # must neither place walls nor open a context menu nor add history.
    for shape in ("line", "square", "circle"):
        viewport.wallShape = shape
        history = len(viewport.undoHistory)
        QtTest.QTest.mousePress(viewport, right, pos = start)
        QtTest.QTest.mouseMove(viewport, end + QtCore.QPoint(0, -100))
        assert viewport.pendingWall is not None
        QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = end)
        assert viewport.pendingWall is None and not viewport.pendingShapeWalls
        assert viewport.rightClickStart is None and viewport.mode == "Select"
        QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.LeftButton, pos = end)
        QtTest.QTest.mouseMove(viewport, end + QtCore.QPoint(0, -150))
        QtTest.QTest.mouseRelease(viewport, right, pos = end)
        assert len(viewport.walls) == 2 and len(viewport.undoHistory) == history
        assert not viewport.objectContextMenu.isVisible()
    QtTest.QTest.mousePress(viewport, right, pos = start)
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    assert viewport.rightClickStart is None
    QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    QtTest.QTest.mouseRelease(viewport, right, pos = start)
    assert not viewport.objectContextMenu.isVisible()
    window.close()
    print("PASS: right-button walls, snapping, branches, history, matching release, cancellation and click rejection.")


if __name__ == "__main__":
    Main()
