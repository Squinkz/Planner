"""Alternate frozen/current GUI-thread preview preparation and private transport."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow
from fixtures.export_preview_reference_20261031 import ExportPreviewProcess as ReferenceProcess
from planner_app.export_preview import ExportPreviewProcess
from planner_app.models import Wall, Furnishing


def Submit(worker, panel, prepared, mode, optimized):
    count = 16 if mode == "coalesced burst" else 1
    calls = 0
    worker.current = dict(slot = "occupied", key = "seed") if count > 1 else None
    v = panel.mainWindow.viewport
    for index in range(count):
        background = ("benchmark", index)
        key = v.SceneRenderKey(background)
        def Build(bounds = (index, -1000, 6000, 4000)):
            nonlocal calls
            calls += 1
            render = prepared if mode == "prepared job dispatch" else panel.RenderArguments("png", preview = True)
            return dict(render, bounds = bounds)
        if optimized and count > 1:
            worker.Request("snapshot", key, Build, "png", isCurrent = lambda background = background, key = key: v.SceneRenderKey(background) == key)
        else:
            worker.Request("snapshot", key, Build, "png")
    if count > 1:
        worker.current = None
        worker.StartNext()
    worker.timeout.stop()
    worker.current = None
    return calls


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--samples", type = int, default = 9)
    parser.add_argument("--output", type = Path, default = root / "diagnostics/performance-preview-20261031/benchmark-final.json")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("Samples must be positive")
    results = dict(python = platform.python_version(), qt = QtCore.qVersion(), platform = platform.platform(), samples = args.samples,
        methodology = "Alternate frozen/current variants, discard one warmup, median samples. Real GUI RenderArguments and job-file writes; "
            "QProcess stdin writes/state are stubbed to exclude worker startup/rendering/adoption. Prepared dispatch excludes project encoding. "
            "Single snapshot includes project encoding. A burst replaces one pending raster slot 16 times behind a busy worker, then dispatches once. "
            "Real source-key creation/checks, native bytes/paths and the full built-in catalog are included. "
            "Offscreen Windows run; component costs, not input-to-display latency.", measurements = [])
    with ExampleWindow() as (main, folder):
        v, panel = main.viewport, main.exportPanel
        for count in (128, 1024, 4096):
            v.walls = [Wall(QtCore.QPointF(index * 1000, 0), QtCore.QPointF(index * 1000, 500), 200) for index in range(count)]
            v.furnishings = [Furnishing(v.furnishingDefinitions["washer"], QtCore.QPointF(index * 1000, 2000))
                             for index in range(min(count // 4, 256))]
            v.EnsureObjectIds()
            prepared = panel.RenderArguments("png", preview = True)
            for mode in ("prepared job dispatch", "single snapshot", "coalesced burst"):
                workers = [ReferenceProcess(v.exportOverlay), ExportPreviewProcess(v.exportOverlay)]
                samples, callCounts, sizes = [[], []], [[], []], [0, 0]
                try:
                    for repeat in range(args.samples + 1):
                        for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                            worker = workers[variant]
                            with patch.object(worker.process, "state", return_value = QtCore.QProcess.ProcessState.Running), \
                                    patch.object(worker.process, "write", return_value = 1):
                                start = perf_counter()
                                calls = Submit(worker, panel, prepared, mode, variant == 1)
                                elapsed = (perf_counter() - start) * 1000
                            jobPath = Path(worker.temporary.name) / ("job.pickle" if variant else "job.json")
                            sizes[variant] = jobPath.stat().st_size
                            if repeat:
                                samples[variant].append(elapsed)
                                callCounts[variant].append(calls)
                    row = dict(walls = count, furnishings = len(v.furnishings), catalogEntries = len(v.furnishingDefinitions),
                        mode = mode, requests = 16 if mode == "coalesced burst" else 1,
                        beforeMs = statistics.median(samples[0]), afterMs = statistics.median(samples[1]), samplesMs = samples,
                        factoryCalls = callCounts, jobBytes = sizes)
                    results["measurements"].append(row)
                    print(count, mode, round(row["beforeMs"], 3), round(row["afterMs"], 3), sizes, flush = True)
                finally:
                    for worker in workers:
                        worker.Close()
                        worker.deleteLater()
                    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(results, indent = 2) + "\n", encoding = "utf-8")


if __name__ == "__main__":
    Main()
