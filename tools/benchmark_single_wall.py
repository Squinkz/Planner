"""Compare current flat.plan endpoint dragging with the same wall in isolation."""
from contextlib import ExitStack
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
from statistics import median
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks"), str(root / "tools")]
from PySide6 import QtCore, QtWidgets
from benchmark_flat_interactions import PrepareCase
from profile_flat_interactions import BeginEndpoint, Step
from fixtures.parity_examples import ExampleWindow, InstallScene


def Main():
    folder = root / "diagnostics/performance-single-wall-20261101"
    folder.mkdir(exist_ok = True)
    protected = list((root / "planner-main/planner_app").rglob("*.py"))
    protected += [path for path in (root / "planner-main/help").rglob("*") if path.is_file()]
    protected.append(root / "plans/flat.plan")
    hashes = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
    runs = []
    gcEnabled = gc.isenabled()
    gc.disable()
    try:
        for run in range(3):
            with ExitStack() as stack:
                windows = [stack.enter_context(ExampleWindow())[0] for case in range(2)]
                for main in windows:
                    main.hide()
                views = []
                for index, main in enumerate(windows):
                    view = PrepareCase(main, "drag", False)
                    if index == 1:
                        view.CancelInteraction()
                        wall = next(wall for wall in view.walls if wall.objectId == 256)
                        InstallScene(main, [wall])
                        view.ClearGeometryCaches()
                        BeginEndpoint(view, wall, 1)
                        assert len(view.walls) == 1 and not (view.windows or view.furnishings or view.labels)
                    views.append(view)
                assert views[0].zoom == views[1].zoom and views[0].panOffset == views[1].panOffset
                assert views[0].basePixelsPerMillimeter == views[1].basePixelsPerMillimeter
                assert views[0].dragVertices == views[1].dragVertices
                settings = ("showGrid", "showMeasurements", "floors", "solidRooms", "snapEnabled", "vertexSnapEnabled",
                            "cornerSnapEnabled", "alignmentSnapEnabled", "midpointSnapEnabled", "gridSnapEnabled",
                            "collisionSettings", "visibility", "connectedEnabled")
                assert all(getattr(views[0], name) == getattr(views[1], name) for name in settings)
                counts = [dict(walls = len(view.walls), openings = len(view.windows),
                               furnishings = len(view.furnishings), labels = len(view.labels)) for view in views]
                samples = [[], []]
                warmups = [[], []]
                for frame in range(17):
                    for variant in ((0, 1) if (frame + run) % 2 == 0 else (1, 0)):
                        view = views[variant]
                        view.renderSamples.clear()
                        row = Step(view, "drag", frame)
                        assert len(view.renderSamples) == 1, ("Expected one viewport paint", variant, frame)
                        row["paintEventMs"] = view.renderSamples[-1][1]
                        (warmups if frame < 2 else samples)[variant].append(row)
                result = dict(samples = samples, warmups = warmups,
                    medians = [{key: median(row[key] for row in rows) for key in rows[0]} for rows in samples],
                    objects = counts, zoom = views[0].zoom,
                    pan = [views[0].panOffset.x(), views[0].panOffset.y()],
                    devicePixelRatio = views[0].devicePixelRatioF())
                runs.append(result)
                print(json.dumps(dict(run = run + 1, medians = result["medians"])), flush = True)
                for view in views:
                    view.CancelInteraction()
                    view.ClearGeometryCaches()
                QtWidgets.QApplication.processEvents()
        rows = [[row for run in runs for row in run["samples"][variant]] for variant in range(2)]
        result = dict(cases = ["flat.plan", "single wall"], viewport = [1500, 900],
            python = platform.python_version(), qt = QtCore.qVersion(),
            methodology = "Current code in real MainWindows, hidden/offscreen to avoid incidental double paints. "
                "Single-wall scene retains flat.plan wall 256 and removes every other scene object, keeping the same "
                "original endpoints, width, camera, saved settings and catalog. Snap targets, attached geometry and resulting "
                "wall positions naturally differ between scenes. UpdateInteraction, connected UI work, processEvents, one "
                "synchronous viewport grab. Three runs, two warmups then fifteen alternating samples per scene per run; "
                "45 timed samples per scene, cyclic GC disabled equally. Actual paintEvent time is read from existing "
                "renderSamples, with exactly one viewport paint asserted per step. Grab time also includes capture overhead. "
                "Warmups retained separately, not isolated cold-start measurements. Synchronous work, not display latency.",
            medians = [{key: median(row[key] for row in samples) for key in samples[0]} for samples in rows],
            runs = runs, protectedFilesSha256 = hashes)
        assert all(hashlib.sha256((root / name).read_bytes()).hexdigest() == value for name, value in hashes.items())
        result["protectedFilesUnchanged"] = True
        (folder / "benchmark.json").write_text(json.dumps(result, indent = 2), encoding = "utf-8")
        print(json.dumps(dict(medians = result["medians"], protectedFilesUnchanged = True), indent = 2))
    finally:
        if gcEnabled:
            gc.enable()


if __name__ == "__main__":
    Main()
