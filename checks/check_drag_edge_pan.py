"""Edge pan follows held object drags without changing anchors or edit history."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Furnishing, Wall
from planner_app.viewport.widget import DrawingViewport
from planner_app.viewport import interaction


def Mouse(v, eventType, position, modifiers = QtCore.Qt.KeyboardModifier.NoModifier,
          button = QtCore.Qt.MouseButton.LeftButton):
    buttons = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseButtonRelease else button
    button = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseMove else button
    event = QtGui.QMouseEvent(eventType, position, QtCore.QPointF(v.mapToGlobal(position.toPoint())), button, buttons, modifiers)
    QtWidgets.QApplication.sendEvent(v, event)


def Tick(v, modifiers = QtCore.Qt.KeyboardModifier.NoModifier):
    with patch.object(interaction, "perf_counter", return_value = v.dragPanLastTime + .02), \
            patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value = modifiers):
        v.AdvanceDragPan()


def Main():
    app = QtWidgets.QApplication([])
    v = DrawingViewport()
    v.performanceTimer.stop()
    v.resize(700, 500)
    v.snapEnabled = False
    v.show()
    app.processEvents()
    point, types = QtCore.QPointF, QtCore.QEvent.Type
    for position in (point(720, 250), point(-20, 250), point(350, -20), point(350, 520), point(720, 520)):
        v.panOffset = point()
        desk = Furnishing(v.furnishingDefinitions["desk"], point())
        v.walls, v.furnishings = [], [desk]
        v.SetSelection([(desk, None)])
        v.undoHistory.clear()
        original = point(desk.firstVertex), point(desk.secondVertex)
        start = v.WorldToViewport((desk.firstVertex + desk.secondVertex) / 2)
        Mouse(v, types.MouseButtonPress, start)
        Mouse(v, types.MouseMove, position)
        assert v.isDragging and v.dragPanTimer.isActive()
        for index in range(3):
            previous = point(v.panOffset)
            Tick(v)
            assert v.panOffset != previous
            center = v.WorldToViewport((desk.firstVertex + desk.secondVertex) / 2)
            assert QtCore.QLineF(center, position).length() < 1e-6, (center, position)
            assert not v.undoHistory, 'Timer ticks split a single edit into multiple undo steps'
        previous = point(v.panOffset)
        with patch.object(interaction, "perf_counter", return_value = v.dragPanLastTime + 5):
            v.AdvanceDragPan()
        assert QtCore.QLineF(previous, v.panOffset).length() <= 120 + 1e-9
        Mouse(v, types.MouseButtonRelease, position)
        assert not v.dragPanTimer.isActive() and v.dragPanPosition is None
        assert len(v.undoHistory) == 1
        v.Undo()
        assert (desk.firstVertex, desk.secondVertex) == original
    v.panOffset = point()
    wall = Wall(point(-400, 0), point(400, 0), 100)
    v.walls, v.furnishings = [wall], []
    v.SetSelection([(wall, 1)])
    fixed = point(wall.firstVertex)
    Mouse(v, types.MouseButtonPress, v.WorldToViewport(wall.secondVertex))
    position = point(720, 300)
    Mouse(v, types.MouseMove, position)
    Tick(v)
    assert wall.firstVertex == fixed
    assert QtCore.QLineF(v.WorldToViewport(wall.secondVertex), position).length() < 1e-6
    # Moving back to the interior stops the timer before release.
    Mouse(v, types.MouseMove, point(350, 250))
    assert not v.dragPanTimer.isActive()
    Mouse(v, types.MouseMove, position)
    assert v.dragPanTimer.isActive()
    v.CancelInteraction()
    assert not v.dragPanTimer.isActive()
    assert wall.firstVertex == fixed and wall.secondVertex == point(400, 0)
    # Compare axial and diagonal speed at both partial and full edge penetration.
    v.walls = []
    v.SetSelection([])
    for penetration in (12, 24, 44, 120, 600):
        distances = []
        rect = v.DrawingRect()
        for corner in (False, True):
            v.panOffset = point()
            Mouse(v, types.MouseButtonPress, rect.center())
            edge = point(rect.right() - 24 + penetration,
                         rect.bottom() - 24 + penetration if corner else rect.center().y())
            Mouse(v, types.MouseMove, edge)
            assert v.dragPanTimer.isActive()
            Tick(v)
            distances.append(QtCore.QLineF(point(), v.panOffset).length())
            v.CancelInteraction()
            assert not v.dragPanTimer.isActive() and v.boxStart is None
        assert abs(distances[0] - distances[1]) < 1e-6, distances
        speed = min(5, min(1, penetration / 24) + max(0, penetration - 24) / 96) * 480
        assert abs(distances[0] - speed * .02) < 1e-6
    # Box selection extends into newly revealed space, preserving add/remove rules.
    control = QtCore.Qt.KeyboardModifier.ControlModifier
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    for modifiers in (QtCore.Qt.KeyboardModifier.NoModifier, shift, control):
        v.panOffset = point()
        target = Wall(v.ViewportToWorld(point(760, 280)), v.ViewportToWorld(point(780, 300)), 10)
        retained = Wall(v.ViewportToWorld(point(100, 100)), v.ViewportToWorld(point(120, 120)), 10)
        v.walls = [target, retained]
        v.SetSelection([(retained, None)] + ([(target, None)] if modifiers == control else []))
        v.undoHistory.clear()
        start = point(350, 60)
        fixed = v.ViewportToWorld(start)
        position = point(720, 350)
        Mouse(v, types.MouseButtonPress, start, modifiers)
        Mouse(v, types.MouseMove, position, modifiers)
        assert v.boxStart is not None and v.dragPanTimer.isActive(), (modifiers, v.boxStart, v.dragStart, v.selectedWall)
        for index in range(20):
            Tick(v, modifiers)
            assert QtCore.QLineF(v.ViewportToWorld(v.boxStart), fixed).length() < 1e-6
            assert v.boxEnd == position
        Mouse(v, types.MouseButtonRelease, position, modifiers)
        selected = [obj for obj, vertexIndex in v.SelectionEntries()]
        assert (target in selected) == (modifiers != control), selected
        assert (retained in selected) == (modifiers in (shift, control)), selected
        assert not v.dragPanTimer.isActive() and v.boxStart is None
        assert not v.undoHistory, 'Box selection must not create geometry edits'
    v.walls = []
    v.SetSelection([])
    # A press without sufficient travel, or ordinary hover, cannot start panning.
    position = point(720, 300)
    Mouse(v, types.MouseButtonPress, position)
    Mouse(v, types.MouseMove, position + point(1, 0))
    assert not v.dragPanTimer.isActive()
    Mouse(v, types.MouseButtonRelease, position)
    v.UpdateDragPan(position, QtCore.Qt.MouseButton.NoButton)
    assert not v.dragPanTimer.isActive()
    v.panOffset = point()
    v.undoHistory.clear()
    right = QtCore.Qt.MouseButton.RightButton
    Mouse(v, types.MouseButtonPress, point(350, 250), button = right)
    Mouse(v, types.MouseMove, position, button = right)
    assert v.pendingWall is not None and v.dragPanTimer.isActive()
    fixed = point(v.pendingWall.firstVertex)
    Tick(v)
    assert v.pendingWall.firstVertex == fixed
    assert QtCore.QLineF(v.WorldToViewport(v.pendingWall.secondVertex), position).length() < 1e-6
    Mouse(v, types.MouseButtonRelease, position, button = right)
    assert len(v.walls) == 1 and len(v.undoHistory) == 1
    assert not v.dragPanTimer.isActive()
    v.panOffset = point()
    v.walls = []
    desk = Furnishing(v.furnishingDefinitions["desk"], point())
    v.furnishings = [desk]
    v.SetSelection([(desk, None)])
    start = v.WorldToViewport((desk.firstVertex + desk.secondVertex) / 2)
    control = QtCore.Qt.KeyboardModifier.ControlModifier
    Mouse(v, types.MouseButtonPress, start)
    Mouse(v, types.MouseMove, point(720, start.y() + 20), control)
    originalY = ((desk.firstVertex + desk.secondVertex) / 2).y()
    Tick(v, control)
    assert abs(((desk.firstVertex + desk.secondVertex) / 2).y() - originalY) < 1e-6
    v.CancelInteraction()
    v.panOffset = point()
    v.SetSelection([(desk, None)])
    handle = next(handle for handle in v.FurnishingHandles(desk) if handle[0] == "resize" and handle[1] == "width" and handle[2] == 1)
    center = (desk.firstVertex + desk.secondVertex) / 2
    anchor = center - point(desk.width / 2, 0)
    Mouse(v, types.MouseButtonPress, handle[3])
    Mouse(v, types.MouseMove, point(720, handle[3].y()))
    beforeWidth = desk.width
    Tick(v)
    assert desk.width > beforeWidth
    assert QtCore.QLineF((desk.firstVertex + desk.secondVertex) / 2 - point(desk.width / 2, 0), anchor).length() < 1e-6
    QtWidgets.QApplication.sendEvent(v, QtCore.QEvent(types.UngrabMouse))
    assert not v.dragPanTimer.isActive()
    Mouse(v, types.MouseMove, point(720, handle[3].y()))
    assert v.dragPanTimer.isActive()
    event = QtGui.QMouseEvent(types.MouseMove, point(720, 250), point(720, 250),
        QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(v, event)
    assert not v.dragPanTimer.isActive(), 'A lost button release left edge panning active'
    v.CancelInteraction()
    v.close()
    print("PASS: edge directions, normalized diagonal speed, box selection add/remove, world anchors, single undo and cancellation")


if __name__ == "__main__":
    Main()
