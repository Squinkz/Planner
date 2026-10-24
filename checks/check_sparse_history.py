"""Sparse history scaling, bounds, coalescing, branches, identity and validation."""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall
from planner_app.models import Door, Stair
from planner_app.project_codec import DecodeProject, EncodeScene
from planner_app.project_history import EncodeEdit


def Main():
    temporary = tempfile.TemporaryDirectory(dir = Path(__file__).parent)
    os.environ["PLANNER_SESSION_PATH"] = str(Path(temporary.name) / "session.json")
    os.environ["PLANNER_STARTUP_PATH"] = str(Path(temporary.name) / "startup.plan")
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.sessionTimer.stop()
    main.sessionPollTimer.stop()
    v = main.viewport
    point = QtCore.QPointF
    v.walls = [Wall(point(index * 4000, 0), point(index * 4000 + 3000, 0)) for index in range(1000)]
    v.EnsureObjectIds()
    original = EncodeScene(v)
    for index in range(200):
        before = v.CaptureState()
        v.walls[500].width += 1
        v.RecordEdit(before)
        assert len(v.undoHistory[-1].changes) == 1
    history = main.ProjectHistory()
    payload = len(json.dumps(history, separators = (",", ":")).encode())
    retained = sum(edit.byteSize for edit in v.undoHistory)
    assert payload < 150000 and retained < 1000000, (payload, retained)
    assert len(v.undoHistory) == 200
    saved = main.BuildProjectData()
    expected = EncodeScene(v)
    main.ApplyProject(DecodeProject(saved, v.furnishingDefinitions), None)
    assert len(v.undoHistory) == 200
    unchanged = v.walls[499]
    for index in range(200):
        v.Undo()
    assert EncodeScene(v) == original and v.walls[499] is unchanged
    redoSaved = main.BuildProjectData()
    main.ApplyProject(DecodeProject(redoSaved, v.furnishingDefinitions), None)
    assert len(v.redoHistory) == 200
    for index in range(200):
        v.Redo()
    assert EncodeScene(v) == expected

    # An edit after undo starts a new branch; count and payload limits are strict.
    v.Undo()
    before = v.CaptureState()
    v.walls[501].width += 5
    v.RecordEdit(before)
    assert not v.redoHistory
    v.historyLimit = 3
    before = v.CaptureState()
    v.walls[501].width += 5
    v.RecordEdit(before)
    assert len(v.undoHistory) == 3
    v.historyByteBudget = v.undoHistory[-1].byteSize * 2
    before = v.CaptureState()
    v.walls[501].width += 5
    v.RecordEdit(before)
    assert sum(edit.byteSize for edit in v.undoHistory) <= v.historyByteBudget
    v.historyByteBudget = 1
    before = v.CaptureState()
    v.walls[501].width += 5
    v.RecordEdit(before)
    assert not v.undoHistory, "Oversized individual edit bypassed the memory bound"
    v.historyByteBudget = 16 * 1024 * 1024
    v.historyLimit = 200

    # Coalescing keeps the original value, including returning exactly to it.
    originalWidth = v.walls[501].width
    for delta in (5, 10, 0):
        before = v.CaptureState()
        v.walls[501].width = originalWidth + delta
        v.RecordEdit(before, coalesceKey = "width")
    assert not v.undoHistory, "A coalesced no-op retained history"

    # Deleting a wall and its opening restores their original identities.
    v.walls = v.walls[:2]
    v.windows = [Door(v.walls[0], .2, .5)]
    wall, opening = v.walls[0], v.windows[0]
    before = v.CaptureState()
    v.walls.pop(0)
    v.windows.clear()
    v.RecordEdit(before)
    v.Undo()
    assert v.walls[0] is wall and v.windows[0] is opening and opening.parentWall is wall
    v.Redo()
    deleted = main.BuildProjectData()
    main.ApplyProject(DecodeProject(deleted, v.furnishingDefinitions), None)
    assert v.undoHistory
    v.Undo()
    assert len(v.walls) == 2 and len(v.windows) == 1 and v.windows[0].parentWall is v.walls[0]
    v.Redo()
    assert len(v.walls) == 1 and not v.windows
    retiredId = v.undoHistory[-1].changes[0][3][0].objectId
    newWall = Wall(point(12000, 0), point(15000, 0))
    before = v.CaptureState()
    v.walls.append(newWall)
    with patch("planner_app.viewport.scene.objectIdCounter", iter((retiredId, 99999999))):
        v.RecordEdit(before)
    assert newWall.objectId == 99999999, "An object awaiting undo had its ID reused"
    before = v.CaptureState()
    v.objectGroups = [(v.walls[1], v.walls[0])]
    v.RecordEdit(before)
    grouped = main.BuildProjectData()
    main.ApplyProject(DecodeProject(grouped, v.furnishingDefinitions), None)
    assert len(v.undoHistory) == len(grouped["history"]["undo"]), "Sorted project groups broke history matching"
    v.Undo()
    assert not v.objectGroups
    v.Redo()
    assert len(v.objectGroups) == 1

    # Incompatible or tampered undo data does not change or block the valid scene.
    valid = main.BuildProjectData()
    corruptions = [{"undo": [[{}, {}]], "redo": []}, {**valid["history"], "version": 99}]
    mismatch = copy.deepcopy(valid["history"])
    mismatch["undo"][-2]["changes"][0]["after"][1]["width"] = "invalid"
    corruptions.append(mismatch)
    brokenChain = copy.deepcopy(valid["history"])
    brokenChain["undo"][-2]["changes"][0]["after"][0] = 999
    corruptions.append(brokenChain)
    for history in corruptions:
        data = {**valid, "history": history}
        decoded = DecodeProject(data, v.furnishingDefinitions)
        assert decoded[5]["history"] == {"undo": [], "redo": []}
        assert decoded[0][0].objectId == v.walls[0].objectId
    # A deleted stair must not keep every other stair alive through layout links.
    v.undoHistory.clear()
    v.redoHistory.clear()
    v.objectGroups, v.hiddenObjects = [], []
    v.walls = [Stair(point(index * 4000, 0), point(index * 4000 + 3000, 0)) for index in range(10)]
    v.EnsureObjectIds()
    stair = v.walls[0]
    assert len(stair.sceneStairs) == 10
    before = v.CaptureState()
    v.walls.pop(0)
    v.RecordEdit(before)
    assert not stair.sceneStairs
    v.Undo()
    assert len(stair.sceneStairs) == 10
    v.Redo()
    assert not stair.sceneStairs
    main.projectDirty = False
    main.close()
    temporary.cleanup()
    report = {"sceneObjects": 1000, "edits": 200, "savedHistoryBytes": payload,
              "estimatedRetainedBytes": retained, "historyByteBudget": v.historyByteBudget}
    (Path(__file__).resolve().parent.parent / "diagnostics" / "sparse-history-check.json").write_text(
        json.dumps(report, indent = 2), encoding = "utf-8")
    print(f"PASS: 200 edits in a 1000-object scene: {payload} saved bytes, {retained} estimated retained bytes; undo/redo, bounds, branches, coalescing, deleted parents and corrupt history")


if __name__ == "__main__":
    Main()
