"""Every architectural type shares duplicate warnings, labels and export filtering."""
import copy
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Pillar, Column, Counter, Stair, Railing, Elevator
from planner_app.object_schema import openingClasses
from planner_app.scene_problems import FindSceneProblems
from planner_app.export_plan import RenderPlan
from check_architectural_error_highlights import WarningPixels


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.showGrid = v.showMeasurements = False
        v.collisionSettings = dict.fromkeys(v.collisionSettings, False)
        point = QtCore.QPointF
        for cls in (Wall, Pillar, Column, Counter, Stair, Railing, Elevator, *openingClasses.values()):
            if cls in openingClasses.values():
                parent = Wall(point(-2500, 0), point(2500, 0), 240)
                first, second = cls(parent, .3, .6), cls(parent, .3, .6)
                objects = [parent, first, second]
            else:
                first, second = [cls(point(-1800, 0), point(1800, 0), 600) for repeat in range(2)]
                objects = [first, second]
            InstallScene(main, objects)
            assert [id(obj) for obj in v.DuplicateArchitecturalObjects()] == [id(second)], cls.__name__
            issues = FindSceneProblems(v, includePotential = False)
            issue = next(issue for issue in issues if issue["object"] is second and issue["label"].startswith("Coincident"))
            assert cls is Wall or "wall" not in issue["label"].lower(), issue["label"]
            assert WarningPixels(v.grab().toImage()) > 0, cls.__name__
            # An acknowledged coincident opening must retain the rear copy on
            # export after the front copy is removed.
            if cls in openingClasses.values():
                first.geometryIssues = second.geometryIssues = ("opening_overlap",)
            if cls in (Stair, Railing, Elevator) or cls.__name__ == "Window":
                data = main.BuildProjectData(includeHistory = False)
                single = copy.deepcopy(data)
                single["scene"]["objects"] = [record for record in single["scene"]["objects"] if record["id"] != second.objectId]
                for outputFormat in ("png", "svg"):
                    options = dict(bounds = (-3000, -1200, 6000, 3000), outputFormat = outputFormat,
                                   applyTheme = False, furnishingDefinitions = v.furnishingDefinitions)
                    assert RenderPlan("Duplicates.plan", 50, projectData = data, **options) == RenderPlan(
                        "Duplicates.plan", 50, projectData = single, **options), (cls.__name__, outputFormat)
            if cls in openingClasses.values():
                second.centerFraction += 2
            else:
                second.firstVertex += point(10000, 0)
                second.secondVertex += point(10000, 0)
            assert v.DuplicateArchitecturalObjects() == [], cls.__name__
        # End-to-end constructions remain valid, rather than becoming warnings.
        for cls in (Counter, Stair, Railing):
            InstallScene(main, [cls(point(-1800, 0), point(0, 0), 600), cls(point(0, 0), point(1800, 0), 600)])
            assert not v.DuplicateArchitecturalObjects()
            assert WarningPixels(v.grab().toImage()) == 0, cls.__name__
    print("Architectural duplicates: every type, actual names, disabled collisions, connected constructions and PNG/SVG filtering passed")


if __name__ == "__main__":
    Main()
