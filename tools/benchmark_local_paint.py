"""Current/frozen validation A/B during real flat.plan endpoint dragging."""
import argparse
from contextlib import ExitStack, contextmanager
import gc
import json
import os
from pathlib import Path
import platform
from statistics import median
import sys
import subprocess
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks"), str(root / "tools")]
from PySide6 import QtCore
from benchmark_flat_interactions import PrepareCase
from profile_flat_interactions import BeginEndpoint, Step
from fixtures.parity_examples import ExampleWindow, InstallScene
from fixtures.local_paint_reference_20261101 import ReferencePlacement
from planner_app.viewport.placement import PlacementMixin
from check_drag_fitting_preparation import Snapshot


@contextmanager
def Baseline(enabled):
    with ExitStack() as stack:
        if enabled:
            for name in ("InvalidArchitecturalObjects", "RefreshArchitecturalValidation", "PlacementBlockers"):
                stack.enter_context(patch.object(PlacementMixin, name, getattr(ReferencePlacement, name)))
        yield


def RunTrial(args, run):
    gcEnabled = gc.isenabled()
    gc.disable()
    try:
        with ExitStack() as stack:
            creationOrder = (0, 1) if run % 2 == 0 else (1, 0)
            windows = [None, None]
            for variant in creationOrder:
                windows[variant] = stack.enter_context(ExampleWindow())[0]
            for main in windows:
                main.hide()
            views = [None, None]
            for variant in creationOrder:
                main = windows[variant]
                with Baseline(variant == 0):
                    view = PrepareCase(main, args.case, False)
                    if args.singleWall:
                        view.CancelInteraction()
                        wall = next(wall for wall in view.walls if wall.objectId == args.wallId)
                        InstallScene(main, [wall])
                        view.ClearGeometryCaches()
                        if args.case == "drag":
                            BeginEndpoint(view, wall, args.vertex)
                    elif args.case == "drag" and (args.wallId != 256 or args.vertex != 1):
                        BeginEndpoint(view, next(wall for wall in view.walls if wall.objectId == args.wallId), args.vertex)
                    views[variant] = view
            samples = [[], []]
            warmups = [[], []]
            case = "zoom-out" if args.case == "zoom-deep" else args.case
            for frame in range(17):
                for variant in ((0, 1) if (frame + run) % 2 == 0 else (1, 0)):
                    view = views[variant]
                    view.renderSamples.clear()
                    with Baseline(variant == 0):
                        row = Step(view, case, frame)
                    assert len(view.renderSamples) == 1
                    row["paintEventMs"] = view.renderSamples[-1][1]
                    (warmups if frame < 2 else samples)[variant].append(row)
                assert Snapshot(views[0]) == Snapshot(views[1]), ("model", run, frame)
                assert views[0].zoom == views[1].zoom and views[0].panOffset == views[1].panOffset
            images, counts = [], []
            for variant, view in enumerate(views):
                with Baseline(variant == 0):
                    images.append(view.grab().toImage())
                    with patch.object(view, "ArchitecturalPlacementFits", wraps = view.ArchitecturalPlacementFits) as fitting:
                        Step(view, case, 17)
                    counts.append(fitting.call_count)
                view.CancelInteraction()
            assert images[0] == images[1], ("pixels", run)
            result = dict(samples = samples, warmups = warmups, placementValidations = counts,
                medians = [{key: median(row[key] for row in rows) for key in rows[0]} for rows in samples],
                devicePixelRatio = views[0].devicePixelRatioF(), creationOrder = creationOrder)
            return result
    finally:
        if gcEnabled:
            gc.enable()


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--case", choices = ("drag", "zoom-in", "zoom-out", "zoom-deep"), default = "drag")
    parser.add_argument("--single-wall", dest = "singleWall", action = "store_true")
    parser.add_argument("--wall-id", dest = "wallId", type = int, default = 256)
    parser.add_argument("--vertex", type = int, choices = (0, 1), default = 1)
    parser.add_argument("--run-index", dest = "runIndex", type = int, choices = range(4), help = argparse.SUPPRESS)
    args = parser.parse_args()
    folder = root / "diagnostics/performance-local-paint-20261101"
    folder.mkdir(parents = True, exist_ok = True)
    suffix = "-single-wall" if args.singleWall else ""
    if args.wallId != 256 or args.vertex != 1:
        suffix += f"-wall-{args.wallId}-vertex-{args.vertex}"
    stem = f"benchmark-{args.case}{suffix}"
    if args.runIndex is not None:
        result = RunTrial(args, args.runIndex)
        (folder / f"{stem}-run{args.runIndex + 1}.json").write_text(json.dumps(result, indent = 2), encoding = "utf-8")
        print(json.dumps(dict(run = args.runIndex + 1, medians = result["medians"], validations = result["placementValidations"])), flush = True)
        return
    runs = []
    for run in range(4):
        arguments = [sys.executable, str(Path(__file__).resolve()), "--case", args.case,
                     "--wall-id", str(args.wallId), "--vertex", str(args.vertex), "--run-index", str(run)]
        if args.singleWall:
            arguments.append("--single-wall")
        subprocess.run(arguments, cwd = root, check = True)
        runs.append(json.loads((folder / f"{stem}-run{run + 1}.json").read_text(encoding = "utf-8")))
    rows = [[row for run in runs for row in run["samples"][variant]] for variant in range(2)]
    result = dict(case = args.case, singleWall = args.singleWall, wallId = args.wallId, vertex = args.vertex, viewport = [1500, 900],
        python = platform.python_version(), qt = QtCore.qVersion(), runs = runs,
        methodology = "Start-of-pass frozen validation methods versus current, shared current remaining code. "
            "Independent real hidden MainWindows with original flat.plan settings and the recorded wall/vertex. "
            "Four independent child processes, each with two windows, two warmups and fifteen alternating unprofiled UpdateInteraction/wheelEvent, processEvents, "
            "one synchronous grab samples: 60 per variant. Window creation/preparation order is reversed on alternate runs. "
            "Cyclic GC disabled equally. Actual paintEvent time from "
            "existing renderSamples; exactly one paint asserted. Model/gesture state and zoom/pan compared every step; "
            "exact final pixels each run. Extra placement counters untimed. Warmups are not isolated cold-start measurements. "
            "Single-wall option removes all other scene objects, retaining saved settings/camera. Not display latency.",
        medians = [{key: median(row[key] for row in samples) for key in samples[0]} for samples in rows])
    (folder / f"{stem}.json").write_text(json.dumps(result, indent = 2), encoding = "utf-8")
    print(json.dumps(result["medians"], indent = 2))


if __name__ == "__main__":
    Main()
