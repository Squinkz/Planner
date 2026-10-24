"""Coincident elevators warn even with collision enforcement disabled."""
import copy
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Elevator
from planner_app.scene_problems import FindSceneProblems
from planner_app.export_plan import RenderPlan
from check_architectural_error_highlights import WarningPixels
from check_scene_render_cache import CompareDirect


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        point = QtCore.QPointF
        v.showGrid = v.showMeasurements = False
        v.collisionSettings = dict.fromkeys(v.collisionSettings, False)
        first = Elevator(point(0, 0), point(0, 1219.2), 1219.2)
        second = Elevator(point(0, 0), point(0, 1219.2), 1219.2)
        InstallScene(main, [first, second])
        assert v.ArchitecturalPlacementFits(first) and v.ArchitecturalPlacementFits(second)
        assert v.ContainedWalls() == [second]
        assert any(issue["object"] is second and issue["code"] == "contained"
                   for issue in FindSceneProblems(v, includePotential = False))
        assert WarningPixels(v.grab().toImage()) > 0
        v.SetSelection([(second, None)])
        assert WarningPixels(v.grab().toImage()) > 0, "Selection replaced the elevator warning"
        v.SetSelection([])
        before = v.CaptureState()
        second.firstVertex += point(3000, 0)
        second.secondVertex += point(3000, 0)
        v.RecordEdit(before)
        CompareDirect(v)
        assert WarningPixels(v.grab().toImage()) == 0
        v.Undo()
        CompareDirect(v)
        assert WarningPixels(v.grab().toImage()) > 0
        data = main.BuildProjectData(includeHistory = False)
        single = copy.deepcopy(data)
        single["scene"]["objects"] = [record for record in single["scene"]["objects"] if record["id"] != second.objectId]
        for outputFormat in ("png", "svg"):
            options = dict(bounds = (-2000, -1000, 4000, 3500), outputFormat = outputFormat,
                           applyTheme = False, furnishingDefinitions = v.furnishingDefinitions)
            actual = RenderPlan("Elevator.plan", 100, projectData = data, **options)
            expected = RenderPlan("Elevator.plan", 100, projectData = single, **options)
            assert actual == expected, "Export retained the duplicate elevator or its warning"
    print("Duplicate elevators: advisory warning with collisions off, selection, movement, undo and single-object PNG/SVG export passed")


if __name__ == "__main__":
    Main()
