"""Conservative wall heuristics and transactional, junction-preserving repairs."""
import math
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow
from planner_app.models import Wall, Window, Furnishing
from planner_app.scene_problems import FindSceneProblems, RepairPotentialIssue
from check_scene_problems import SelectIssue


def Main():
    with ExampleWindow() as (main, folder):
        v, point = main.viewport, QtCore.QPointF
        v.walls, v.windows, v.furnishings, v.labels = [], [], [], []
        v.objectGroups, v.hiddenObjects, v.hiddenObjectIds = [], [], set()
        v.gridOrigin = (0, 0)
        v.unitsMode = "Millimeters"
        v.snapEnabled = False
        wall = Wall(point(), point(2000, 4), 100)
        v.walls = [wall]
        v.EnsureObjectIds()
        before = v.CaptureState()
        issues = FindSceneProblems(v, gridStep = 100)
        axis = next(issue for issue in issues if issue["code"] == "potential:axis")
        assert axis["potential"] and "horizontal" in axis["description"]
        assert v.CaptureState() == before and not v.undoHistory
        assert RepairPotentialIssue(v, axis)[0]
        assert wall.firstVertex == point() and wall.secondVertex == point(2000, 0)
        assert len(v.undoHistory) == 1
        v.Undo()
        assert wall.secondVertex == point(2000, 4)
        v.Redo()
        assert wall.secondVertex == point(2000, 0)
        # A grid repair moves the whole shared junction even with connected
        # movement disabled, and fits attached openings through normal rules.
        joint = point(2000.8, .6)
        wall = Wall(point(), joint, 100)
        neighbor = Wall(joint, point(2000.8, 1000), 100)
        opening = Window(wall, .3, .6)
        v.walls, v.windows = [wall, neighbor], [opening]
        v.connectedEnabled = False
        v.EnsureObjectIds()
        v.undoHistory.clear()
        before = v.CaptureState()
        grid = next(issue for issue in FindSceneProblems(v, gridStep = 100) if issue["object"] is wall and issue["code"] == "potential:grid:1")
        assert len(grid["repair"]) == 2
        assert RepairPotentialIssue(v, grid)[0]
        assert wall.secondVertex == neighbor.firstVertex == point(2000, 0)
        assert v.OpeningFits(opening) and not FindSceneProblems(v, includePotential = False)
        assert len(v.undoHistory) == 1
        v.Undo()
        assert wall.secondVertex == neighbor.firstVertex == joint
        assert opening.centerFraction == before[3][0][2] and opening.length == before[3][0][3]
        # Perpendicular repair works on oblique walls, retaining the junction
        # and reference wall rather than forcing either wall onto a world axis.
        first = Wall(point(), point(2000 * math.cos(math.radians(30)), 1000), 100)
        second = Wall(point(), point(2000 * math.cos(math.radians(120.3)), 2000 * math.sin(math.radians(120.3))), 100)
        v.walls, v.windows = [first, second], []
        v.EnsureObjectIds()
        originalFirst = point(first.secondVertex)
        angle = next(issue for issue in FindSceneProblems(v, gridStep = 100) if issue["code"].startswith("potential:right-angle:"))
        assert set(map(id, angle["objects"])) == {id(first), id(second)}
        assert RepairPotentialIssue(v, angle)[0]
        assert first.firstVertex == second.firstVertex == point()
        assert first.secondVertex == originalFirst
        assert abs(QtCore.QPointF.dotProduct(first.secondVertex, second.secondVertex)) < 1e-6
        # Nearby endpoints join at an existing endpoint, never a midpoint.
        first = Wall(point(0, 0), point(1000, 0), 100)
        second = Wall(point(1002, 0), point(2000, 0), 100)
        v.walls = [first, second]
        gap = next(issue for issue in FindSceneProblems(v, gridStep = 100) if issue["code"].startswith("potential:gap:"))
        assert RepairPotentialIssue(v, gap)[0]
        assert first.secondVertex == second.firstVertex == point(1000, 0)
        assert not any(issue["code"].startswith("potential:gap:") for issue in FindSceneProblems(v, gridStep = 100))
        # Exact/intentional geometry, distant endpoints and sub-tolerance
        # rounding do not produce gap, angle or grid warnings.
        v.walls = [Wall(point(), point(1000, 0), 100), Wall(point(1000.005, 0), point(2000, 0), 100)]
        assert not any(issue.get("potential") for issue in FindSceneProblems(v, gridStep = 100))
        v.walls = [Wall(point(6, 6), point(1006, 6), 100)]
        assert not any(issue.get("potential") for issue in FindSceneProblems(v, gridStep = 100))
        v.walls = [Wall(point(), point(1000, 1000), 100)]
        assert not any(issue.get("potential") for issue in FindSceneProblems(v, gridStep = 100))
        v.walls = [Wall(point(), point(1000, 1000 * math.tan(math.radians(.6))), 100)]
        assert not any(issue["code"] == "potential:axis" for issue in FindSceneProblems(v, gridStep = 100))
        v.walls = [Wall(point(), point(1000, 1000 * math.tan(math.radians(.5))), 100)]
        assert any(issue["code"] == "potential:axis" for issue in FindSceneProblems(v, gridStep = 100))
        v.walls = [Wall(point(0, 0), point(1000, 0), 100), Wall(point(1005, 0), point(2000, 0), 100)]
        assert any(issue["code"].startswith("potential:gap:") for issue in FindSceneProblems(v, gridStep = 100))
        # Grid offsets, negative coordinates and imperial spacing use real
        # world coordinates, independent of the camera's zoom and pan.
        v.gridOrigin = (-12, -8)
        v.unitsMode = "Inches"
        wall = Wall(point(-11.6, -7.7), point(-266, -8), 100)
        v.walls = [wall]
        grid = next(issue for issue in FindSceneProblems(v, gridStep = 25.4) if issue["code"] == "potential:grid:0")
        assert grid["repair"][0][2] == point(-12, -8)
        assert RepairPotentialIssue(v, grid)[0] and wall.firstVertex == point(-12, -8)
        v.unitsMode, v.gridOrigin = "Millimeters", (0, 0)
        # A nearly horizontal wall filled by an opening cannot be shortened.
        wall = Wall(point(), point(1000, 8), 100)
        opening = Window(wall, 0, 1)
        v.walls, v.windows = [wall], [opening]
        v.undoHistory.clear()
        before = v.CaptureState()
        axis = next(issue for issue in FindSceneProblems(v, gridStep = 100) if issue["code"] == "potential:axis")
        repaired, message = RepairPotentialIssue(v, axis)
        assert not repaired and message and v.CaptureState() == before and not v.undoHistory
        # The same rollback applies if the correction would create a collision.
        wall = Wall(point(), point(2000, 4), 100)
        desk = Furnishing(v.furnishingDefinitions["desk"], point(1500, -98.5))
        desk.width = 100
        desk.firstVertex, desk.secondVertex = point(1500, -148.5), point(1500, -48.5)
        v.walls, v.windows, v.furnishings = [wall], [], [desk]
        assert not FindSceneProblems(v, includePotential = False)
        before = v.CaptureState()
        axis = next(issue for issue in FindSceneProblems(v, gridStep = 100) if issue["code"] == "potential:axis")
        assert not RepairPotentialIssue(v, axis)[0]
        assert v.CaptureState() == before and not v.undoHistory
        # Existing recovery issues on unrelated walls are neither silently
        # repaired nor used to block a safe correction elsewhere.
        wall = Wall(point(), point(2000, 4), 100)
        unrelated = Wall(point(5000, 5000), point(7000, 5000), 100)
        existingOpening = Window(unrelated, .3, .6)
        existingOpening.geometryIssues = ("opening_bounds",)
        existingOpening.centerFraction = 1.05
        v.walls, v.windows, v.furnishings = [wall, unrelated], [existingOpening], []
        axis = next(issue for issue in FindSceneProblems(v, gridStep = 100) if issue["code"] == "potential:axis")
        assert RepairPotentialIssue(v, axis)[0]
        assert existingOpening.centerFraction == 1.05 and existingOpening.parentWall is unrelated
        # Both sections remain live and navigation cannot silently change the
        # grid used by a pending repair when it changes the camera zoom.
        v.walls, v.windows, v.furnishings = [Wall(point(), point(2000, 4), 100)], [], []
        v.zoom = 1
        v.EnsureObjectIds()
        main.ShowProblems()
        window = main.problemsWindow
        assert window.tabs.count() == 2
        assert window.tabs.tabText(0).startswith("Problems (")
        assert window.tabs.tabText(1).startswith("Potential issues (")
        assert window.trees[0].topLevelItemCount() == 0
        assert window.trees[1].topLevelItemCount() == 2
        wall = v.walls[0]
        assert v.potentialProblemObjects == (wall,) and not v.problemObjects
        step = window.gridStep
        SelectIssue(window, wall, "potential:axis")
        assert window.tabs.currentIndex() == 1 and window.repairButton.isEnabled()
        window.tabs.setCurrentIndex(0)
        assert not window.repairButton.isEnabled() and not window.deleteButton.isEnabled()
        window.tabs.setCurrentIndex(1)
        assert window.repairButton.isEnabled()
        window.RefreshObjects()
        assert window.tabs.currentIndex() == 1 and window.repairButton.isEnabled()
        window.activateWindow()
        window.tree.setFocus()
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.keyClick(window.tree, QtCore.Qt.Key.Key_P, QtCore.Qt.KeyboardModifier.AltModifier)
        assert main.problemsWindow is window and window.tabs.currentIndex() == 1
        window.JumpTo()
        assert window.gridStep == step
        v.undoHistory.clear()
        window.repairButton.click()
        assert wall.secondVertex.y() == wall.firstVertex.y()
        assert len(v.undoHistory) == 1
        v.Undo()
        QtTest.QTest.qWait(150)
        assert any(issue["code"] == "potential:axis" for issue in window.problems)
        SelectIssue(window, wall, "potential:axis")
        # A stale suggestion is re-evaluated against the user's latest edit.
        before = v.CaptureState()
        wall.secondVertex = point(2000, 200)
        v.RecordEdit(before)
        historySize = len(v.undoHistory)
        window.RepairCurrent()
        assert wall.secondVertex == point(2000, 200) and len(v.undoHistory) == historySize
        v.Undo()
        QtTest.QTest.qWait(150)
        SelectIssue(window, wall, "potential:axis")
        QtWidgets.QApplication.processEvents()
        capture = Path(__file__).resolve().parents[1] / "diagnostics" / "potential-issues-20261023.png"
        assert window.grab().save(str(capture))
        window.close()
        assert not v.problemObjects and not v.potentialProblemObjects
    print("PASS: four wall heuristics, boundaries, shared junctions, oblique joins, openings, safe rollback, grid context, modeless UI and undo")


if __name__ == "__main__":
    Main()
