"""Object angle locks, door midpoint snap priority and stable Shift selection."""
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Door
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    none = QtCore.Qt.KeyboardModifier.NoModifier
    left = QtCore.Qt.MouseButton.LeftButton
    first = Wall(point(-1500, 700), point(0, 700))
    second = Wall(point(-1500, -700), point(0, -700))
    viewport.walls = [first, second]
    window.connectedOptions["vertices"].setChecked(False)
    for group in (False, True):
        for snap in (False, True):
            viewport.snapEnabled = snap
            viewport.SetSelection([(first, None), (second, None)] if group else [(first, None)])
            original = point(first.firstVertex)
            originalSecond = point(second.firstVertex)
            start = viewport.WorldToViewport(point(-750, 700)).toPoint()
            Drag(viewport, start, start + QtCore.QPoint(87, -31), ctrl)
            delta = first.firstVertex - original
            angle = math.degrees(math.atan2(delta.y(), delta.x()))
            assert delta.y() == 0 and delta.x() > 0, delta
            assert first.secondVertex - first.firstVertex == point(1500, 0)
            if group:
                assert QtCore.QLineF(second.firstVertex - originalSecond, delta).length() < .001
            viewport.Undo()
    # Axis guides belong to a Ctrl-constrained translation and its fixed origin.
    viewport.snapEnabled = False
    viewport.SetSelection([(first, None)])
    start = viewport.WorldToViewport(point(-750, 700)).toPoint()
    QtTest.QTest.mousePress(viewport, left, pos = start)
    viewport.UpdateInteraction(point(start) + point(87, -31), ctrl)
    assert viewport.axisConstraintOrigin == viewport.ViewportToWorld(point(start))
    viewport.grab()
    viewport.UpdateInteraction(point(start) + point(87, -31), none)
    assert viewport.axisConstraintOrigin is None
    viewport.UpdateInteraction(point(start) + point(87, -31), ctrl)
    viewport.CancelInteraction()
    assert viewport.axisConstraintOrigin is None
    QtTest.QTest.mouseRelease(viewport, left, pos = start)
    # Right-click restores object/vertex drags and discards Shift duplicates.
    for group, index, modifiers in ((False, None, none), (False, None, shift),
                                    (False, 0, none), (False, 1, ctrl),
                                    (True, None, none), (True, None, shift), (True, 0, none)):
        entries = [(first, index), (second, index)] if group else [(first, index)]
        viewport.SetSelection(entries)
        before = viewport.CaptureState()
        history = len(viewport.undoHistory)
        anchor = ((first.firstVertex + first.secondVertex) / 2 if index is None else
                  first.firstVertex if index == 0 else first.secondVertex)
        start = viewport.WorldToViewport(anchor).toPoint()
        QtTest.QTest.mousePress(viewport, left, pos = start)
        viewport.UpdateInteraction(point(start) + point(87, -31), modifiers)
        assert viewport.isDragging
        if modifiers & shift:
            assert viewport.dragCopies
        viewport.grab()
        QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.RightButton, pos = start)
        assert viewport.dragStart is None and not viewport.dragCopies
        assert viewport.CaptureState() == before
        QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.RightButton, pos = start)
        QtTest.QTest.mouseRelease(viewport, left, pos = start + QtCore.QPoint(87, -31))
        assert len(viewport.undoHistory) == history
        assert not viewport.objectContextMenu.isVisible()
    # Nearby object targets take precedence over incidental grid crossings.
    # The three anchors still compete equally by distance to those targets.
    parent = Wall(point(), point(5000, 0))
    target = Wall(point(987, 0), point(987, 1000))
    door = Door(parent, .01, .19)
    viewport.walls = [parent, target]
    viewport.windows = [door]
    viewport.snapEnabled = True
    viewport.SetSelection([(door, None)])
    start = viewport.WorldToViewport(point(500, 0)).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(90, 0))
    assert abs(door.centerFraction * 5000 - 500) < .001
    viewport.gridSnapEnabled = False
    Drag(viewport, start, start + QtCore.QPoint(90, 0))
    assert abs(door.centerFraction * 5000 - 500) < .001
    viewport.windows = []
    placement = viewport.FindWindowPlacement(viewport.WorldToViewport(point(950, 0)), 900,
                                             preferredWall = parent, openingType = Door, modifiers = none)
    assert placement is None
    # Shift press leaves the existing panel intact; release updates it once.
    viewport.walls = [first, second]
    viewport.windows = []
    viewport.SetSelection([(first, None)])
    app.processEvents()
    changes = QtTest.QSignalSpy(viewport.selectionChanged)
    oldLabel = window.selectionLabel.text()
    oldGeometry = viewport.geometry()
    oldPosition = viewport.WorldToViewport(point())
    position = viewport.WorldToViewport(point(-750, -700)).toPoint()
    QtTest.QTest.mousePress(viewport, left, shift, position)
    app.processEvents()
    assert changes.count() == 0 and window.selectionLabel.text() == oldLabel
    QtTest.QTest.mouseRelease(viewport, left, shift, position)
    app.processEvents()
    assert changes.count() == 1 and len(viewport.SelectionEntries()) == 2
    assert viewport.geometry() == oldGeometry and viewport.WorldToViewport(point()) == oldPosition
    changes = QtTest.QSignalSpy(viewport.selectionChanged)
    empty = viewport.WorldToViewport(point(800, 1200)).toPoint()
    QtTest.QTest.mousePress(viewport, left, shift, empty)
    app.processEvents()
    assert changes.count() == 0 and len(viewport.SelectionEntries()) == 2
    QtTest.QTest.mouseRelease(viewport, left, shift, empty)
    QtTest.QTest.mouseDClick(viewport, left, shift, empty)
    QtTest.QTest.mouseRelease(viewport, left, shift, empty)
    app.processEvents()
    assert changes.count() == 0 and len(viewport.SelectionEntries()) == 2
    assert viewport.geometry() == oldGeometry and viewport.WorldToViewport(point()) == oldPosition
    # Ctrl is a held key during the gesture, including moves without modifier flags.
    for group in (False, True):
        viewport.snapEnabled = False
        viewport.SetSelection([(first, None), (second, None)] if group else [(first, None)])
        original = point(first.firstVertex)
        start = viewport.WorldToViewport((first.firstVertex + first.secondVertex) / 2).toPoint()
        QtTest.QTest.mousePress(viewport, left, none, start)
        QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_Control)
        assert viewport.controlHeld
        end = start + QtCore.QPoint(87, -31)
        move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, point(end),
                                point(viewport.mapToGlobal(end)), QtCore.Qt.MouseButton.NoButton, left, none)
        QtWidgets.QApplication.sendEvent(viewport, move)
        delta = first.firstVertex - original
        assert delta == point(435, 0), delta
        QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_Control)
        assert not viewport.controlHeld
        assert QtCore.QLineF(first.firstVertex - original, point(435, 155)).length() < .001
        QtTest.QTest.mouseRelease(viewport, left, none, end)
        viewport.Undo()
    window.close()
    print("PASS: Ctrl held-key/single/group constraints, closest opening anchors and stable Shift object/empty/double clicks.")


if __name__ == "__main__":
    Main()
