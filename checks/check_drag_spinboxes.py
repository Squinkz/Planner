"""Check property scrubbing, fine control, editing and grouped history."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    viewport = window.viewport
    viewport.unitsMode = "Adaptive Metric"
    wall = Wall(QtCore.QPointF(), QtCore.QPointF(2000, 0))
    viewport.walls = [wall]
    viewport.selectedWall = wall
    window.RefreshProperties()
    app.processEvents()
    spinBox = window.propertyFields["width"]
    editor = spinBox.lineEdit()
    left = QtCore.Qt.MouseButton.LeftButton
    none = QtCore.Qt.KeyboardModifier.NoModifier
    alt = QtCore.Qt.KeyboardModifier.AltModifier
    start = editor.rect().center()
    assert spinBox.buttonSymbols() == QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
    QtTest.QTest.mousePress(editor, left, pos = start)
    for offset, modifiers, expected in ((20, none, 26), (40, none, 28), (60, alt, 28.2), (40, alt, 28)):
        position = start + QtCore.QPoint(offset, 0)
        event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(position),
                                 QtCore.QPointF(editor.mapToGlobal(position)), QtCore.Qt.MouseButton.NoButton, left, modifiers)
        QtWidgets.QApplication.sendEvent(editor, event)
        assert abs(spinBox.value() - expected) < .001
        assert abs(wall.width - expected * 10) < .01
        assert not viewport.undoHistory
    QtTest.QTest.mouseRelease(editor, left, pos = position)
    assert len(viewport.undoHistory) == 1
    viewport.Undo()
    assert wall.width == 240
    viewport.Redo()
    assert wall.width == 280
    QtTest.QTest.mousePress(editor, left, pos = start)
    position = start + QtCore.QPoint(30, 0)
    event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(position),
                             QtCore.QPointF(editor.mapToGlobal(position)), QtCore.Qt.MouseButton.NoButton, left, none)
    QtWidgets.QApplication.sendEvent(editor, event)
    QtTest.QTest.keyClick(editor, QtCore.Qt.Key.Key_Escape)
    QtTest.QTest.mouseRelease(editor, left, pos = position)
    assert wall.width == 280 and len(viewport.undoHistory) == 1
    editor.selectAll()
    QtTest.QTest.keyClicks(editor, "30")
    QtTest.QTest.keyClick(editor, QtCore.Qt.Key.Key_Return)
    assert wall.width == 300
    viewport.selectedVertex = 0
    window.RefreshProperties()
    miter = window.propertyFields["miter"]
    assert miter.maximum() == 1 and miter.minimum() == 0
    window.close()
    print("PASS: arrowless scrubbing, live properties, Alt speed, grouped undo/redo, Escape and typing.")


if __name__ == "__main__":
    Main()
