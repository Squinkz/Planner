"""Snapshot encoding matches the clone-based reference and shares unchanged records."""
import importlib.util
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow
from planner_app.models import Wall, Stair, Counter, Railing, Arrow, Pillar, Furnishing, Label
from planner_app.object_schema import openingClasses
from planner_app.project_history import EncodeHistoryState
from planner_app.history_edits import SceneEdit
from planner_app.project_codec import DecodeProject, EncodeScene
from planner_app.graphics.fonts import LoadApplicationFonts


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    spec = importlib.util.spec_from_file_location("planner_app.history_encoder_reference", root / "checks/fixtures/history_encoder_reference_20261008.py")
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    main = MainWindow()
    main.sessionPollTimer.stop()
    main.sessionTimer.stop()
    v = main.viewport
    point = QtCore.QPointF
    v.walls = [Wall(point(index * 4000, 0), point(index * 4000 + 3000, 0)) for index in range(len(openingClasses))]
    v.windows = [cls(wall, .2, .5) for cls, wall in zip(openingClasses.values(), v.walls)]
    v.walls += [cls(point(0, -3000 - index * 3000), point(2000, -3000 - index * 3000))
                for index, cls in enumerate((Stair, Counter, Railing, Arrow, Pillar))]
    v.furnishings = [Furnishing(v.furnishingDefinitions["desk"], point(0, -20000))]
    v.labels = [Label(point(0, -23000), 'History "測試"')]
    v.objectGroups = [(v.walls[0], v.furnishings[0])]
    v.hiddenObjects = [v.walls[1], v.labels[0]]
    v.EnsureObjectIds()
    first = v.CaptureState()
    for wall in v.walls:
        wall.firstVertex += point(13, 29)
        wall.width += 3
        if isinstance(wall, Arrow):
            wall.solidTip = not wall.solidTip
            wall.tipSize += 7
            wall.intensity = .65
        if isinstance(wall, Stair):
            wall.directionReversed = not wall.directionReversed
            wall.autosize = False
            wall.manualStepCount = 7
        if isinstance(wall, Railing):
            wall.autosize = False
            wall.manualPostCount = 5
    for opening in v.windows:
        for name in ("hingeAtSecond", "swingsOutwards", "panelsFlipped", "measurementFlipped"):
            if hasattr(opening, name):
                setattr(opening, name, not getattr(opening, name))
        if hasattr(opening, "sillDepth"):
            opening.sillDepth += 20
    v.furnishings[0].angle = 37
    v.furnishings[0].width += 21
    v.furnishings[0].definitionKey = "missing-definition"
    v.labels[0].text = "Changed"
    v.labels[0].intensity = .4
    second = v.CaptureState()
    # Parent indices change when object order changes, even if an opening does not.
    v.walls.reverse()
    v.objectGroups = [(v.furnishings[0], v.labels[0])]
    v.hiddenObjects = [v.windows[-1]]
    third = v.CaptureState()
    cache = {}
    for state in (first, second, third, first):
        assert EncodeHistoryState(state, cache) == reference.EncodeHistoryState(state)
    unchanged = EncodeHistoryState(third, cache)
    v.walls[0].width += 1
    changed = EncodeHistoryState(v.CaptureState(), cache)
    assert unchanged["objects"][0] is not changed["objects"][0]
    assert all(a is b for a, b in zip(unchanged["objects"][1:], changed["objects"][1:]))
    # Equal geometry does not make distinct IDs interchangeable in groups/hidden state.
    v.walls = [Wall(point(), point(1000, 0)) for index in range(3)]
    v.windows, v.furnishings, v.labels = [], [], []
    v.EnsureObjectIds()
    v.objectGroups, v.hiddenObjects = [(v.walls[0], v.walls[1])], [v.walls[0]]
    before = v.CaptureState()
    v.objectGroups, v.hiddenObjects = [(v.walls[0], v.walls[2])], [v.walls[1]]
    after = v.CaptureState()
    v.undoHistory, v.redoHistory = [SceneEdit.Between(before, after)], []
    v.sceneRevision += 1
    encoded = main.ProjectHistory()
    assert encoded["undo"][0]["changes"] == [], "Membership edits copied object geometry"
    assert encoded["undo"][0]["groups"] and encoded["undo"][0]["hidden"]
    # All historical fields and actual order changes survive the sparse codec.
    v.RestoreState(third)
    v.undoHistory = [SceneEdit.Between(first, second), SceneEdit.Between(second, third)]
    data = main.BuildProjectData(includeHistory = False)
    data["history"] = main.ProjectHistory()
    expected = EncodeScene(v)
    assert all(record.get("width", 1) > 0 for record in data["scene"]["objects"]), data["scene"]
    decoded = DecodeProject(data, v.furnishingDefinitions, validatePlacement = False)
    assert len(decoded[5]["history"]["undo"]) == 2
    main.ApplyProject(decoded, None)
    v.Undo()
    assert EncodeScene(v) == reference.EncodeHistoryState(second)
    v.Undo()
    assert EncodeScene(v) == reference.EncodeHistoryState(first)
    v.Redo()
    v.Redo()
    assert EncodeScene(v) == expected
    assert main.close()
    print("PASS: all object types match reference, historical geometry/flags survive, parent ordering stays correct, unchanged records are shared")


if __name__ == "__main__":
    Main()
