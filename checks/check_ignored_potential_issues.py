"""Per-plan ignored suggestions survive loading and expire on relevant geometry changes."""
import copy
import json
import math
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtWidgets
from fixtures.parity_examples import ExampleWindow
from check_scene_problems import SelectIssue
from planner_app.models import Wall, Furnishing
from planner_app.scene_problems import FindSceneProblems
from planner_app.project_codec import DecodeProject
from planner_app.project_recovery import RecoverProject


def Main():
    with ExampleWindow() as (main, folder):
        v, point = main.viewport, QtCore.QPointF
        wall = Wall(point(), point(2000, 4), 100)
        missing = Furnishing(v.furnishingDefinitions["null"], point(-5000, 0))
        missing.definitionKey = "missing_ignore_control"
        v.walls, v.windows, v.furnishings, v.labels = [wall], [], [missing], []
        v.objectGroups, v.hiddenObjects, v.hiddenObjectIds = [], [], set()
        v.EnsureObjectIds()
        v.undoHistory.clear()
        main.MarkProjectClean()
        main.ShowProblems()
        window = main.problemsWindow
        SelectIssue(window, missing, "asset:missing_ignore_control")
        assert window.ignoreButton.isHidden() and not window.ignoreButton.isEnabled()
        window.IgnoreCurrent()
        assert not v.ignoredPotentialIssues
        SelectIssue(window, wall, "potential:axis")
        assert window.ignoreButton.isVisible() and window.ignoreButton.isEnabled()
        before = v.CaptureState()
        window.ignoreButton.click()
        assert len(v.ignoredPotentialIssues) == 1 and v.CaptureState() == before and not v.undoHistory
        assert not any(issue["code"] == "potential:axis" for issue in window.problems)
        assert any(issue["code"] == "asset:missing_ignore_control" for issue in window.problems)
        assert any(issue["code"].startswith("potential:grid:") for issue in window.problems)
        main.RefreshProjectDirty()
        assert main.projectDirty
        window.Recheck()
        assert not any(issue["code"] == "potential:axis" for issue in window.problems)
        window.close()
        main.ShowProblems()
        assert not any(issue["code"] == "potential:axis" for issue in main.problemsWindow.problems)
        main.problemsWindow.close()
        path = folder / "ignored.plan"
        assert main.SaveProject(path)
        tokens = list(v.ignoredPotentialIssues)
        assert json.loads(path.read_text())["settings"]["ignoredPotentialIssues"] == tokens
        assert main.OpenProject(path)
        if getattr(main, "recoveryWindow", None) is not None:
            main.recoveryWindow.close()
        assert v.ignoredPotentialIssues == tokens
        assert not any(issue["code"] == "potential:axis" for issue in FindSceneProblems(v))
        wall = v.walls[0]
        before = v.CaptureState()
        wall.secondVertex = point(2000, 3)
        v.RecordEdit(before)
        assert any(issue["code"] == "potential:axis" for issue in FindSceneProblems(v))
        v.Undo()
        assert not any(issue["code"] == "potential:axis" for issue in FindSceneProblems(v))
        main.ShowProblems()
        window = main.problemsWindow
        window.tabs.setCurrentIndex(1)
        assert window.restoreIgnoredButton.isVisible() and window.restoreIgnoredButton.isEnabled()
        window.restoreIgnoredButton.click()
        assert not v.ignoredPotentialIssues
        assert any(issue["code"] == "potential:axis" for issue in window.problems)
        # Ignore a complete category, but do not consume an obsolete proposal.
        SelectIssue(window, wall, "potential:axis")
        stale = v.CaptureState()
        wall.secondVertex = point(2000, 2)
        v.RecordEdit(stale)
        window.IgnoreCurrent()
        assert not v.ignoredPotentialIssues
        SelectIssue(window, wall, "potential:axis")
        window.tree.setCurrentItem(window.tree.currentItem().parent())
        window.IgnoreCurrent()
        assert len(v.ignoredPotentialIssues) == 1
        window.close()
        # All four kinds retain their identity across new model instances,
        # including pairs whose runtime issue codes contain Python object IDs.
        v.walls = [Wall(point(), point(2000, 4), 100),
                   Wall(point(6000, 0), point(7000, 0), 100),
                   Wall(point(7002, 0), point(8000, 0), 100)]
        for angle in (30, 120.3):
            radians = math.radians(angle)
            v.walls.append(Wall(point(12000, 0), point(12000 + 2000 * math.cos(radians), 2000 * math.sin(radians)), 100))
        v.windows, v.furnishings = [], []
        v.EnsureObjectIds()
        v.ignoredPotentialIssues = []
        v.zoom = 1
        original = FindSceneProblems(v)
        assert {issue["code"].split(":")[1] for issue in original} >= {"axis", "grid", "gap", "right-angle"}
        v.ignoredPotentialIssues = [issue["fingerprint"] for issue in original]
        data = main.BuildProjectData(includeHistory = False)
        main.ApplyProject(DecodeProject(data, v.furnishingDefinitions), None)
        assert not FindSceneProblems(v)
        assert len(FindSceneProblems(v, includeIgnored = True)) == len(original)
        # Ignores are project settings, included in session snapshots, and clear
        # when the project closes. Older files default to no ignores.
        main.MarkProjectClean()
        assert main.WriteSession(wait = True)
        session = json.loads(main.sessionPath.read_text())
        assert session["project"]["settings"]["ignoredPotentialIssues"] == v.ignoredPotentialIssues
        assert main.CloseProject() and not v.ignoredPotentialIssues
        legacy = copy.deepcopy(data)
        legacy["settings"].pop("ignoredPotentialIssues")
        assert DecodeProject(legacy, v.furnishingDefinitions)[5]["ignoredPotentialIssues"] == []
        for value in ("bad", ["not-a-fingerprint"], [None]):
            malformed = copy.deepcopy(data)
            malformed["settings"]["ignoredPotentialIssues"] = value
            try:
                DecodeProject(malformed, v.furnishingDefinitions)
            except ValueError:
                pass
            else:
                raise AssertionError(value)
            recovered, notices = RecoverProject(malformed, v.furnishingDefinitions, main.defaultProjectData)
            assert recovered[5]["ignoredPotentialIssues"] == [] and notices
    print("PASS: potential-only ignores, category/stale actions, dirty state, save/reopen/session persistence, geometry changes, restore and safe decoding")


if __name__ == "__main__":
    Main()
