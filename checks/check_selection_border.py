"""Multi-selection bounds and the window-wide deselect shortcut."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Label
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    wall = Wall(point(-1000, 500), point(800, 500))
    label = Label(point(1000, -800), "Room\nLabel")
    label.angle = 30
    v.walls, v.labels = [wall], [label]
    v.SetSelection([(wall, None), (label, None)])
    corners = [v.WorldToViewport(corner) for obj in (wall, label) for corner in v.ObjectCorners(obj)]
    expected = QtCore.QRectF(point(min(corner.x() for corner in corners), min(corner.y() for corner in corners)),
                            point(max(corner.x() for corner in corners), max(corner.y() for corner in corners)))
    rectangles = []

    class BorderPainter(QtGui.QPainter):
        def drawRect(self, *args):
            if self.pen().style() == QtCore.Qt.PenStyle.DashLine:
                rectangles.append(QtCore.QRectF(args[0]))
            super().drawRect(*args)

    with patch.object(QtGui, "QPainter", BorderPainter):
        image = v.grab()
    assert rectangles == [expected]
    image.save(str(Path(__file__).resolve().parent.parent / "screenshots" / "selection-border.png"))
    history = len(v.undoHistory)
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    v.setFocus()
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_A, ctrl | shift)
    assert not v.SelectionEntries() and v.selectedWall is None and main.selectionLabel.text() == "No selection"
    assert len(v.undoHistory) == history
    rectangles.clear()
    with patch.object(QtGui, "QPainter", BorderPainter):
        v.grab()
    assert not rectangles
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_A, ctrl)
    assert len(v.SelectionEntries()) == 2
    main.snapButton.setFocus()
    QtTest.QTest.keyClick(main.snapButton, QtCore.Qt.Key.Key_A, ctrl | shift)
    assert not v.SelectionEntries()
    v.SetSelection([(label, None)])
    main.labelTextField.setFocus()
    QtTest.QTest.keyClick(main.labelTextField, QtCore.Qt.Key.Key_A, ctrl | shift)
    assert v.SelectionEntries() == [(label, None)] and label.text == "Room\nLabel"
    # A stationary empty click must repaint after leaving selection-box mode.
    # Process the press separately so its paint really hides the idle tips.
    v.SetSelection([])
    empty = QtCore.QPoint(70, 70)
    assert v.HitTest(point(empty)) == (None, None)
    paints = []
    originalPaint = v.paintEvent

    def TrackPaint(event):
        paints.append(v.boxStart)
        originalPaint(event)

    with patch.object(v, "paintEvent", side_effect = TrackPaint):
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = empty)
        app.processEvents()
        assert paints and paints[-1] is not None
        paints.clear()
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = empty)
        app.processEvents()
        assert paints and all(state is None for state in paints)
    main.close()
    print("PASS: dashed bounds include mixed/rotated objects; Ctrl+Shift+A deselects from canvas, toolbar and properties.")


if __name__ == "__main__":
    Main()
