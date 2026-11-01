"""Reusable preview scene bytes invalidate exactly and remain caller-owned."""
import copy
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.ui import projects
from planner_app.models import Wall, Door, Furnishing, Label, MeasurementGuide, Railing
from planner_app.export_worker import ExportJobEncoder
from planner_app.project_codec import DecodeProject


def Main():
    point = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v, panel = main.viewport, main.exportPanel
        wall = Wall(point(0, 0), point(4000, 0), 200)
        definition = copy.deepcopy(v.furnishingDefinitions["washer"])
        furnishing = Furnishing(definition, point(1000, 2000))
        InstallScene(main, [wall, Door(wall, .2, .4), furnishing, Label(text = "Test"),
                            MeasurementGuide(point(0, 200), point(4000, 200)), Railing(point(0, 4000), point(4000, 4000), 100)])
        def Compare():
            expected = main.BuildProjectData(includeHistory = False, includeActivity = False)
            actual = main.BuildProjectData(includeHistory = False, includeActivity = False, reuseScene = True)
            assert json.dumps(actual, cls = ExportJobEncoder) == json.dumps(expected, cls = ExportJobEncoder)
            return actual
        Compare()
        with patch.object(projects, "EncodeScene", wraps = projects.EncodeScene) as encode:
            first = Compare()
            # Compare calls the uncached oracle once; warm reuse adds no call.
            assert encode.call_count == 1
            first["scene"]["objects"][0]["first"][0] = 999
            Compare()
            assert encode.call_count == 2, "Returned containers poisoned cached scene bytes"
        mutations = [lambda: wall.firstVertex.setX(17), lambda: setattr(wall, "firstVertex", point(-.0, 0)),
                     lambda: setattr(wall, "material", "Concrete"), lambda: setattr(wall, "objectId", "snapshot-wall"),
                     lambda: setattr(wall, "originalMaterial", "old"), lambda: setattr(wall, "geometryIssues", ["opening_overlap"]),
                     lambda: wall.geometryIssues.append("outside_parent"),
                     lambda: setattr(furnishing, "definitionKey", definition["key"]),
                     lambda: definition.update(width = definition["width"] + 17),
                     lambda: setattr(v.walls[-1], "manualPostCount", 19),
                     lambda: v.walls.append(Wall(point(0, -1000), point(4000, -1000), 200)),
                     lambda: v.objectGroups.append([wall, furnishing]), lambda: v.objectGroups[-1].append(v.labels[0]),
                     lambda: v.hiddenObjects.append(wall), lambda: v.walls.reverse()]
        for index, mutate in enumerate(mutations):
            mutate()
            Compare()
        # Source definitions can mutate deeply without scene notifications.
        v.furnishingDefinitions["washer"]["snapshotProbe"] = dict(values = [1])
        Compare()
        v.furnishingDefinitions["washer"]["snapshotProbe"]["values"].append(2)
        Compare()
        del v.furnishingDefinitions["washer"]["snapshotProbe"]
        definition["snapshotProbe"] = b"x" * (9 * 1024 * 1024)
        Compare()
        assert "previewSceneSnapshot" not in main.__dict__, "Oversized source data exceeded the snapshot byte limit"
        del definition["snapshotProbe"]
        Compare()
        v.__dict__["walls"] = list(v.walls)
        Compare()
        assert "previewSceneSnapshot" not in main.__dict__, "Untracked lists reused revision-keyed bytes"
        v.walls = list(v.walls)
        Compare()
        decoded = DecodeProject(main.defaultProjectData, v.furnishingDefinitions)
        main.ApplyProject(decoded, None)
        assert "previewSceneSnapshot" not in main.__dict__
    print("PASS: exact fresh/reused snapshots, detached containers, geometry/metadata/deep definitions/groups/hidden/order invalidation, adapter fallback and project cleanup.")


if __name__ == "__main__":
    Main()
