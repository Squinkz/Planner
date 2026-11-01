"""Incremental flat.plan benchmarks against the start of this optimization pass."""
import argparse
from contextlib import ExitStack, contextmanager
import gc
import json
import os
from pathlib import Path
import platform
from statistics import median
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks"), str(root / "tools")]
from PySide6 import QtCore
from benchmark_flat_interactions import PrepareCase
from profile_flat_interactions import Step
from fixtures.parity_examples import ExampleWindow
from fixtures.flat_next_reference_20261031 import ReferenceGeometry, ReferenceSnapping, ReferencePlacement
from planner_app.viewport.geometry import GeometryMixin
from planner_app.viewport.snapping import SnappingMixin
from planner_app.viewport.placement import PlacementMixin
from check_drag_fitting_preparation import Snapshot

folder = root / "diagnostics/performance-flat-next-20261031"


@contextmanager
def Baseline(enabled):
    with ExitStack() as stack:
        if enabled:
            stack.enter_context(patch.object(GeometryMixin, "ConnectedWallPath", ReferenceGeometry.ConnectedWallPath))
            stack.enter_context(patch.object(SnappingMixin, "SnapStairVertex", ReferenceSnapping.SnapStairVertex))
            stack.enter_context(patch.object(PlacementMixin, "PlacementBlockers", ReferencePlacement.PlacementBlockers))
        yield


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--case", choices = ("drag", "zoom-in", "zoom-out", "zoom-deep"), required = True)
    args = parser.parse_args()
    gcEnabled = gc.isenabled()
    gc.disable()
    try:
        with ExitStack() as stack:
            windows = [stack.enter_context(ExampleWindow())[0] for variant in range(2)]
            for main in windows:
                main.hide()
            views = []
            for variant, main in enumerate(windows):
                with Baseline(variant == 0):
                    views.append(PrepareCase(main, args.case, False))
            samples = [[], []]
            cold = [None, None]
            case = "zoom-out" if args.case == "zoom-deep" else args.case
            for frame in range(17):
                for variant in ((0, 1) if frame % 2 == 0 else (1, 0)):
                    with Baseline(variant == 0):
                        row = Step(views[variant], case, frame)
                    if frame == 0:
                        cold[variant] = row
                    if frame >= 2:
                        samples[variant].append(row)
                assert Snapshot(views[0]) == Snapshot(views[1]), ("model state", frame)
                assert views[0].zoom == views[1].zoom and views[0].panOffset == views[1].panOffset
            images = []
            for variant, view in enumerate(views):
                with Baseline(variant == 0):
                    images.append(view.grab().toImage())
            assert images[0] == images[1], "Viewport pixels changed"
            probes = []
            for variant, view in enumerate(views):
                count = [0]
                original = view.SnapMidpoints
                fits = view.ArchitecturalPlacementFits

                def Midpoints():
                    count[0] += 1
                    yield from original()

                with Baseline(variant == 0), patch.object(view, "SnapMidpoints", Midpoints), \
                        patch.object(view, "ArchitecturalPlacementFits", wraps = fits) as validation:
                    Step(view, case, 17)
                budget = view.geometryCacheBudget
                assert budget.byteCount <= budget.byteLimit and budget.pointCount <= budget.pointLimit
                probes.append(dict(midpointCollections = count[0], estimatedGeometryBytes = budget.byteCount,
                    geometryPoints = budget.pointCount, assemblyEntries = len(view.__dict__.get("wallAssemblyCache", ())),
                    placementValidations = validation.call_count))
                view.CancelInteraction()
            result = dict(case = args.case, python = platform.python_version(), qt = QtCore.qVersion(),
                viewport = [1500, 900], devicePixelRatio = views[0].devicePixelRatioF(),
                methodology = "Original flat.plan saved settings in two hidden real MainWindows. Start-of-pass frozen "
                    "ConnectedWallPath, SnapStairVertex and PlacementBlockers versus current; both retain preceding renderer and collision fixes. "
                    "Two warmups and fifteen alternating unprofiled input/processEvents/one-grab samples, cyclic GC disabled equally. "
                    "Model/zoom/pan compared each step, exact final pixels. Cold first-step and extra untimed counters reported separately. "
                    "Deep zoom starts eight outward ticks below saved view. This is synchronous work, not display latency.",
                medians = [{key: median(row[key] for row in rows) for key in rows[0]} for rows in samples],
                cold = cold, probes = probes, samples = samples)
            folder.mkdir(exist_ok = True)
            (folder / f"benchmark-{args.case}.json").write_text(json.dumps(result, indent = 2), encoding = "utf-8")
            print(json.dumps({key: value for key, value in result.items() if key not in ("samples", "methodology")}, indent = 2))
    finally:
        if gcEnabled:
            gc.enable()


if __name__ == "__main__":
    Main()
