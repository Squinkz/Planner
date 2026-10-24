"""Run deletion, edit history, and Shift-drag checks offscreen."""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from planner import MainWindow


def Drag(viewport, start, end, modifiers = QtCore.Qt.KeyboardModifier.NoModifier, button = QtCore.Qt.MouseButton.LeftButton):
    QtTest.QTest.mousePress(viewport, button, modifiers, start)
    move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(end),
                            QtCore.QPointF(viewport.mapToGlobal(end)), QtCore.Qt.MouseButton.NoButton,
                            button, modifiers)
    QtWidgets.QApplication.sendEvent(viewport, move)
    QtTest.QTest.mouseRelease(viewport, button, modifiers, end)


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.unitsMode = "Adaptive Metric"  # Width uses cm; position and length use m.
    leftButton = QtCore.Qt.MouseButton.LeftButton
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    window.snapButton.setChecked(False)
    window.connectedOptions["vertices"].setChecked(False)
    window.connectedOptions["objects"].setChecked(False)
    Drag(viewport, QtCore.QPoint(220, 300), QtCore.QPoint(520, 300), shift, button = QtCore.Qt.MouseButton.RightButton)
    assert len(viewport.undoHistory) == 1
    wall = viewport.walls[0]
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Z, ctrl)
    assert not viewport.walls
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Z, ctrl | shift)
    assert viewport.walls[0] is wall

    # Whole-wall movement, one history entry even with many move events.
    originalFirst = QtCore.QPointF(wall.firstVertex)
    originalSecond = QtCore.QPointF(wall.secondVertex)
    Drag(viewport, QtCore.QPoint(370, 300), QtCore.QPoint(410, 320))
    assert len(viewport.undoHistory) == 2
    assert wall.firstVertex == originalFirst + QtCore.QPointF(200, -100)
    viewport.Undo()
    assert wall.firstVertex == originalFirst and wall.secondVertex == originalSecond
    viewport.Redo()
    movedFirst = QtCore.QPointF(wall.firstVertex)
    movedSecond = QtCore.QPointF(wall.secondVertex)

    # Deleting a wall restores geometry and selection through undo/redo.
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Delete)
    assert not viewport.walls and viewport.selectedWall is None
    viewport.Undo()
    assert viewport.walls[0] is wall and viewport.selectedWall is wall
    viewport.Redo()
    assert not viewport.walls
    viewport.Undo()

    # Right-dragging either endpoint creates a wall rooted at that endpoint.
    for vertex in (wall.firstVertex, wall.secondVertex):
        endpoint = viewport.WorldToViewport(vertex).toPoint()
        Drag(viewport, endpoint, endpoint + QtCore.QPoint(0, -100), shift, button = QtCore.Qt.MouseButton.RightButton)
        assert len(viewport.walls) == 2
        branch = viewport.walls[-1]
        assert branch.firstVertex == vertex
        assert branch.secondVertex == vertex + QtCore.QPointF(0, 500)
        assert wall.firstVertex == movedFirst and wall.secondVertex == movedSecond
        viewport.Undo()
        assert len(viewport.walls) == 1
        viewport.Redo()
        assert viewport.walls[-1] is branch
        viewport.Undo()

    # Vertex translation and position properties both round-trip through history.
    endpoint = viewport.WorldToViewport(wall.secondVertex).toPoint()
    Drag(viewport, endpoint, endpoint + QtCore.QPoint(0, -60))
    assert wall.secondVertex == movedSecond + QtCore.QPointF(0, 300)
    viewport.Undo()
    assert wall.secondVertex == movedSecond
    viewport.Redo()
    window.propertyFields["y"].setValue(1.234)
    assert wall.secondVertex.y() == 1234
    viewport.Undo()
    assert wall.secondVertex.y() == movedSecond.y() + 300
    viewport.Redo()
    assert wall.secondVertex.y() == 1234

    viewport.selectedVertex = None
    window.RefreshProperties()
    widthBefore = wall.width
    window.propertyFields["width"].setValue(35)
    assert wall.width == 350
    # Property editors own their text undo; scene undo runs with viewport focus.
    field = window.propertyFields["width"].lineEdit()
    field.setFocus()
    viewport.setFocus()
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Z, ctrl)
    assert wall.width == widthBefore
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Z, ctrl | shift)
    assert wall.width == 350
    lengthBefore = QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
    window.propertyFields["length"].setValue(2.5)
    viewport.Undo()
    assert abs(QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() - lengthBefore) < 1e-8
    viewport.Redo()
    assert abs(QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() - 2500) < 1e-8

    # Cancelled drags and simple clicks do not create history; new edits clear redo.
    historyCount = len(viewport.undoHistory)
    midpoint = viewport.WorldToViewport((wall.firstVertex + wall.secondVertex) / 2).toPoint()
    QtTest.QTest.mouseClick(viewport, leftButton, pos = midpoint)
    QtTest.QTest.mousePress(viewport, leftButton, pos = midpoint)
    viewport.UpdateInteraction(QtCore.QPointF(midpoint + QtCore.QPoint(40, 40)), QtCore.Qt.KeyboardModifier.NoModifier)
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Escape)
    QtTest.QTest.mouseRelease(viewport, leftButton, pos = midpoint + QtCore.QPoint(40, 40))
    assert len(viewport.undoHistory) == historyCount and len(viewport.walls) == 1
    viewport.Undo()
    window.propertyFields["width"].setValue(40)
    assert not viewport.redoHistory
    finalState = viewport.CaptureState()[0]
    undoCount = len(viewport.undoHistory)
    for index in range(undoCount):
        viewport.Undo()
    assert not viewport.walls
    for index in range(undoCount):
        viewport.Redo()
    assert viewport.CaptureState()[0] == finalState
    window.close()
    print("PASS: creation/deletion, wall/vertex movement, all property edits, undo/redo shortcuts, right-button wall creation/branching, cancellation and redo branching.")


if __name__ == "__main__":
    Main()
