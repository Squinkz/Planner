"""Reserved-door wall edits and real group-drag validation without an application."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from check_reserved_door_junctions import GeometryViewport
from PySide6 import QtCore, QtGui
from planner_app.models import Wall, BarnDoor, PocketDoor
from planner_app.viewport.scene import SceneEditingMixin
from planner_app.project_codec import EncodeScene, DecodeProject
from planner_app.history_edits import SceneEdit
from planner_app.project_history import EncodeEdit


class EditingViewport(GeometryViewport, SceneEditingMixin):
    def __init__(self, walls):
        super().__init__(walls)
        self.entries = []
        self.connectedVerticesEnabled = True
        self.controlHeld = self.groupDrag = False
        self.dragCopies = []
        self.selectionChanged = SimpleNamespace(emit = Mock())
        self.update = Mock()
        self.SnapObjectMovement = Mock(side_effect = lambda anchors, delta, *args, **kwargs: delta)
        self.snapApplied = False
        self.alignmentGuides = []

    def SelectionEntries(self):
        return self.entries


def Main():
    p = QtCore.QPointF
    none = QtCore.Qt.KeyboardModifier.NoModifier
    template = json.loads((Path(__file__).resolve().parents[1] / "docs/parity/reference/rendering/wall.plan").read_text(encoding = "utf-8"))
    with patch("planner_app.viewport.scene.QtWidgets.QApplication.startDragDistance", return_value = 1):
        for angle in (0, 37):
            for reverse in (False, True):
                for kind in (BarnDoor, PocketDoor):
                    transform = QtGui.QTransform().rotate(angle)
                    parent, support, branch = Wall(p(-2000, 0), p(), 200), Wall(p(), p(2000, 0), 200), Wall(p(), p(0, 2000), 150)
                    walls = [parent, support, branch]
                    for wall in walls:
                        wall.firstVertex, wall.secondVertex = transform.map(wall.firstVertex), transform.map(wall.secondVertex)
                        if reverse:
                            wall.firstVertex, wall.secondVertex = wall.secondVertex, wall.firstVertex
                    v = EditingViewport(walls)
                    door = kind(parent, -.4 if reverse else .5, .5 if reverse else 1.4, hingeAtSecond = reverse)
                    v.windows = [door]
                    for objectId, obj in enumerate(walls + [door], 1):
                        obj.objectId = objectId
                    originalFirst, originalSecond = p(door.firstVertex), p(door.secondVertex)
                    v.selectedWall, v.selectedVertex = parent, 0 if reverse else 1
                    v.entries = [(parent, 0 if reverse else 1), (support, 1 if reverse else 0), (branch, 1 if reverse else 0)]
                    v.interactionBefore = v.CaptureState()
                    v.dragStart = v.WorldToViewport(p())
                    v.isDragging = True
                    v.StartGroupDrag()
                    # Sliding a division must not slide or resize the door.
                    v.UpdateGroupDrag(v.WorldToViewport(transform.map(p(100, 0))), none)
                    joint = parent.firstVertex if reverse else parent.secondVertex
                    assert QtCore.QLineF(joint, transform.map(p(100, 0))).length() < .01
                    assert QtCore.QLineF(door.firstVertex, originalFirst).length() < .01
                    assert QtCore.QLineF(door.secondVertex, originalSecond).length() < .01
                    assert abs(door.length - 1800) < .01 and v.OpeningsValid(before = v.interactionBefore)
                    validFrame = v.CaptureState()
                    # A branch through the aperture stops at the preceding valid
                    # frame; release can commit it instead of cancelling the drag.
                    v.UpdateGroupDrag(v.WorldToViewport(transform.map(p(-200, 0))), none)
                    joint = parent.firstVertex if reverse else parent.secondVertex
                    assert QtCore.QLineF(joint, transform.map(p(100, 0))).length() < .01
                    assert v.CaptureState()[0] == validFrame[0] and v.CaptureState()[3] == validFrame[3]
                    assert v.OpeningsValid(before = v.interactionBefore)
                    v.UpdateGroupDrag(v.WorldToViewport(transform.map(p(50, 0))), none)
                    joint = parent.firstVertex if reverse else parent.secondVertex
                    assert QtCore.QLineF(joint, transform.map(p(50, 0))).length() < .01
                    assert QtCore.QLineF(door.firstVertex, originalFirst).length() < .01
                    # The same captured coordinates/fractions round-trip after editing.
                    data = dict(template, scene = EncodeScene(v))
                    edit = SceneEdit.Between(v.interactionBefore, v.CaptureState())
                    assert edit is not None
                    data["history"] = dict(format = "Planner Changes", version = 1, undo = [EncodeEdit(edit)], redo = [])
                    decoded = DecodeProject(data, {})
                    assert QtCore.QLineF(decoded[1][0].firstVertex, originalFirst).length() < .01
                    assert len(decoded[5]["history"]["undo"]) == 1
                    current = SimpleNamespace(walls = decoded[0], windows = decoded[1], furnishings = [], labels = [],
                        objectGroups = [], hiddenObjects = [], selectedWall = None, selectedVertex = None, SelectionEntries = lambda: [])
                    currentState = SceneEditingMixin.CaptureState(current)
                    loadedEdit = decoded[5]["history"]["undo"][0]
                    restored = loadedEdit.Apply(currentState, False, validate = True)
                    assert restored[0][0][1:5] == v.interactionBefore[0][0][1:5]
                    assert loadedEdit.Apply(restored, True, validate = True)[0][0][1:5] == currentState[0][0][1:5]
                    # The secondary wall can move independently while its face
                    # still supports the reserved span; opening a gap is blocked.
                    v.groupDrag = False
                    v.entries = [(support, None)]
                    v.selectedWall, v.selectedVertex = support, None
                    v.interactionBefore = v.CaptureState()
                    v.dragStart = v.WorldToViewport(p())
                    supportFirst, supportSecond = p(support.firstVertex), p(support.secondVertex)
                    v.StartGroupDrag()
                    delta = transform.map(p(-100, 0))
                    v.UpdateGroupDrag(v.WorldToViewport(delta), none)
                    assert QtCore.QLineF(support.firstVertex, supportFirst + delta).length() < .01
                    assert QtCore.QLineF(door.firstVertex, originalFirst).length() < .01
                    v.UpdateGroupDrag(v.WorldToViewport(transform.map(p(50, 0))), none)
                    assert QtCore.QLineF(support.firstVertex, supportFirst + delta).length() < .01
                    assert v.OpeningsValid(before = v.interactionBefore)
                    # Connected whole-wall translation carries both aperture and
                    # secondary support; disabling it preserves an on-axis door.
                    for follow in (True, False):
                        v.groupDrag = False
                        v.entries = [(wall, None) for wall in walls]
                        v.selectedVertex = None
                        v.connectedEnabled = follow
                        v.connectedObjectsEnabled = follow
                        v.interactionBefore = v.CaptureState()
                        oldFirst = p(door.firstVertex)
                        v.dragStart = v.WorldToViewport(p())
                        v.StartGroupDrag()
                        delta = transform.map(p(100, 80 if follow else 0))
                        v.UpdateGroupDrag(v.WorldToViewport(delta), none)
                        expected = oldFirst + delta if follow else oldFirst
                        assert QtCore.QLineF(door.firstVertex, expected).length() < .01
                        assert abs(door.length - 1800) < .01 and v.OpeningsValid(before = v.interactionBefore)
    print("PASS: pocket/barn shared-point sliding, unchanged spans, group last-valid/recovery, connected carrying, detached on-axis anchoring and save/load; no app/rendering")


if __name__ == "__main__":
    Main()
