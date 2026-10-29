"""Keep extracted core modules importable without Qt or site packages."""
import importlib
from pathlib import Path
import subprocess
import sys

portableModules = (
    "project_settings", "furnishing_records", "catalog_records", "recovery_records",
    "history_records", "activity_records", "property_edits", "dimension_actions", "units",
    "model_construction", "record_schema", "record_validation", "record_repairs",
    "export_settings", "export_crop", "selection_records", "selection_placement",
    "selection_copy", "selection_policy", "edit_transactions", "reference_state",
    "catalog_metadata", "furnishing_import_plan", "furnishing_assets", "furnishing_limits",
    "measurement_units", "geometry.group_movement", "geometry.endpoint_snapping",
    "geometry.opening_candidates", "geometry.selection_edits", "geometry.sizing",
    "geometry.resize_snapping", "geometry.movement_snapping", "geometry.room_regions",
    "geometry.wall_diagnostics", "geometry.dimension_chains", "geometry.measurement_stack_layout",
    "geometry.stair_annotation_plans", "geometry.compound_furnishings", "geometry.path_operations",
)


def CheckWithoutQt():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
    for name in portableModules:
        importlib.import_module("planner_app." + name)
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS:", len(portableModules), "core module import boundaries without Qt or site packages")


if __name__ == "__main__":
    if "--without-qt" in sys.argv:
        CheckWithoutQt()
    else:
        result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"], capture_output = True, text = True, timeout = 10)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout.strip())
