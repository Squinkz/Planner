"""Run portable JSON examples without Qt, then validate the reference project's scene."""
import json
import math
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

workspace = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace / "planner-main"))
qtModulesBefore = {name for name in sys.modules if name.startswith("PySide6")}
from planner_app.geometry.footprints import WallBody, RectangleFootprint, ColumnContains
from planner_app.geometry.snapping import GridIntervals


def Main():
    directory = workspace / "docs" / "parity"
    fixture = json.loads((directory / "numeric-examples.json").read_text(encoding = "utf-8"))
    operations = {"WallBody": WallBody, "RectangleFootprint": RectangleFootprint,
                  "ColumnContains": ColumnContains, "GridIntervals": GridIntervals}

    def Compare(actual, expected, location):
        if isinstance(expected, list):
            assert len(actual) == len(expected), location
            for index, (value, target) in enumerate(zip(actual, expected)):
                Compare(value, target, f"{location}[{index}]")
        elif type(expected) is bool:
            assert actual is expected, (location, actual, expected)
        else:
            assert math.isclose(actual, expected, rel_tol = fixture["relativeTolerance"],
                                abs_tol = fixture["absoluteTolerance"]), (location, actual, expected)

    for case in fixture["cases"]:
        arguments = json.loads(json.dumps(case["arguments"]))
        result = operations[case["operation"]](*arguments)
        Compare(result, case["expected"], case["id"])
        assert arguments == case["arguments"], case["id"] + " mutated its input"
    assert {name for name in sys.modules if name.startswith("PySide6")} == qtModulesBefore, "Numeric examples loaded Qt"
    print(f"PASS: {len(fixture['cases'])} portable numeric examples without Qt")
    if "--numeric-only" in sys.argv:
        return

    scenarios = json.loads((directory / "cases.json").read_text(encoding = "utf-8"))["cases"]
    assert len({case["id"] for case in scenarios}) == len(scenarios)
    documentation = "\n".join(path.read_text(encoding = "utf-8") for path in directory.glob("*.md"))
    ruleIds = set(re.findall(r"^#{1,3} ([A-Z]+(?:-[A-Z]+)*-\d+):", documentation, flags = re.M))
    requiredRules = {"GUIDE-01", "GUIDE-02", "ART-01", "EXPORT-03", "HELP-01", "SIZE-01", "NUM-01", "SETTINGS-01", "BUILD-01",
                     "EXPORT-UI-01", "PROPERTIES-01", "REFERENCE-01", "CALIBRATE-01", "EDIT-02", "EXPORT-04"}
    assert requiredRules <= {case["rule"] for case in scenarios}, "Current parity scenarios are missing"
    indexedChecks = {name for case in scenarios for name in case["checks"]}
    currentChecks = {"angle_guides", "guide_labels", "number_expressions", "linked_size", "optimized_png",
                     "large_export_preview", "furnishing_fixed", "compound_fixed_size", "reference_calibration",
                     "imperial_auto_sizes", "furnishing_sort", "recovery_locate", "errored_asset_clipboard",
                     "window_app_state", "close_project", "help_autoscroll", "session_guide_selection", "parity_layouts", "parity_panel_layouts",
                     "furnishing_asset_consistency", "duplicate_furnishing_export", "pan_preparation", "pan_wall_outline", "pan_wall_patches", "pan_frame_pacing", "render_diagnostics",
                     "drag_edge_pan", "drag_edge_pan_reference", "project_file_drop", "scene_problems", "potential_issues", "ignored_potential_issues"}
    assert {"checks/check_" + name + ".py" for name in currentChecks} <= indexedChecks, "Current behavior checks are unindexed"
    for case in scenarios:
        assert case["rule"] in ruleIds, (case["id"], "missing rule heading")
        assert all(case[key] for key in ("given", "when", "then", "checks")), case["id"]
        for name in case["checks"]:
            assert (workspace / name).is_file(), (case["id"], name)
    browserCases = json.loads((directory / "browser-cases.json").read_text(encoding = "utf-8"))["cases"]
    qtObservations = json.loads((directory / "reference" / "qt-widget-defaults.json").read_text(encoding = "utf-8"))["observations"]
    assert len({case["id"] for case in browserCases}) == len(browserCases)
    for case in browserCases:
        assert case["rule"] in ruleIds and case["status"] == "requires-browser-run", case["id"]
        assert all(case[key] for key in ("given", "when", "then")), case["id"]
        assert all(name in qtObservations for name in case["qtObservations"]), case["id"]
        for name in case["desktopChecks"]:
            assert (workspace / name).is_file(), (case["id"], name)
    manifest = json.loads((directory / "reference" / "manifest.json").read_text(encoding = "utf-8"))
    for capture in manifest["captures"]:
        for key in ("image", "metrics"):
            assert (directory / "reference" / capture[key]).is_file(), capture

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtWidgets
    from planner_app.catalog import LoadFurnishings
    from planner_app.project_codec import DecodeProject, EncodeScene
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    data = json.loads((directory / "reference" / "example.plan").read_text(encoding = "utf-8"))
    definitions = {item["key"]: item for item in LoadFurnishings()}
    decoded = DecodeProject(data, definitions)
    view = SimpleNamespace(walls = decoded[0], windows = decoded[1], furnishings = decoded[2],
                           objectGroups = decoded[3], hiddenObjects = decoded[4], labels = decoded[7])
    expectedScene = json.loads(json.dumps(data["scene"]))
    # This earlier reference predates optional flip fields. Loading omitted
    # flags must preserve the same unflipped geometry when saving explicitly.
    for record in expectedScene["objects"]:
        if record["type"] == "Furnishing":
            record.setdefault("flipHorizontal", False)
            record.setdefault("flipVertical", False)
    assert EncodeScene(view) == expectedScene, "Reference project scene changed on round-trip"
    print(f"PASS: {len(scenarios)} indexed scenarios, reference artifacts and project scene round-trip")
    print(f"PASS: {len(browserCases)} browser acceptance definitions indexed; browser execution not claimed")


if __name__ == "__main__":
    Main()
