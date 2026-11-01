"""Frozen/current group updates, preview snapshots and asynchronous adoption."""
import argparse
import cProfile
import gc
import json
import os
from pathlib import Path
import pickle
import platform
import pstats
import statistics
import sys
from time import perf_counter

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow
from fixtures.group_restore_reference_20261031 import ReferenceViewport
from fixtures.preview_snapshot_reference_20261031 import ReferencePanelMixin
from fixtures.preview_adoption_reference_20261031 import ExportPreviewProcess as ReferenceProcess
from fixtures.svg_adoption_reference_20261031 import SvgPreviewRenderer as ReferenceSvgPreviewRenderer
from planner_app.viewport.widget import DrawingViewport
from planner_app.models import Wall, Furnishing, Label
from planner_app.export_preview import ExportPreviewProcess
from planner_app import export_preview
from planner_app.export_plan import RenderPlan
from planner_app.graphics.svg_preview import SvgPreviewRenderer


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--samples", type = int, default = 9)
    parser.add_argument("--adoption-only", action = "store_true")
    parser.add_argument("--output", type = Path, default = root / "diagnostics/performance-followups-20261031/benchmark-final.json")
    args = parser.parse_args()
    app = QtWidgets.QApplication([])
    gc.disable()
    point = QtCore.QPointF
    result = dict(python = platform.python_version(), qt = QtCore.qVersion(), samples = args.samples,
        methodology = "Alternate frozen/current variants, discard two warmup samples, medians. Automatic Python GC disabled. "
            "Group samples average five absolute UpdateInteraction calls; snapping/connections disabled unless stated. "
            "Rendered samples include synchronous QWidget rendering, not input-to-display latency. "
            "Snapshot samples include complete RenderArguments with the catalog, current settings and detached project data. "
            "Adoption timings exclude worker rendering and transport writes: synchronous read/SVG preparation before; "
            "background read/preparation plus GUI handoff after. GUI return measures the initiating callback, readiness includes wait. "
            "1ms GUI heartbeat maximum gaps include scheduling/GIL effects, not a frame-rate guarantee. Profiles are separate from timings.",
        groups = [], snapshots = [], adoption = [], profiles = [])
    with ExampleWindow() as (main, folder):
        definitions = main.viewport.furnishingDefinitions
        for count, selected in (() if args.adoption_only else ((128, 2), (1024, 2), (1024, 128), (4096, 2), (1024, 1024))):
            views = []
            for cls in (ReferenceViewport, DrawingViewport):
                view = cls(furnishingDefinitions = definitions)
                view.resize(1000, 750)
                view.showMeasurements = view.showTips = view.snapEnabled = view.connectedEnabled = False
                view.walls = [Wall(point(index * 6000, 0), point(index * 6000 + 4000, 0), 200) for index in range(count)]
                view.furnishings = [Furnishing(definitions["desk"], point(index * 6000, 10000)) for index in range(count)]
                view.labels = [Label(point(index * 6000, 15000), "Label") for index in range(count)]
                entries = [(obj, None) for obj in view.furnishings[:selected // 2] + view.labels[:selected - selected // 2]]
                view.SetSelection(entries, notify = False)
                view.interactionBefore = view.CaptureState()
                view.dragStart, view.isDragging = point(400, 300), True
                view.StartGroupDrag()
                views.append(view)
            for paint in ((False, True) if count == 1024 and selected in (2, 128) else (False,)):
                samples = [[], []]
                for repeat in range(args.samples + 2):
                    for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                        view = views[variant]
                        image = QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied) if paint else None
                        start = perf_counter()
                        for frame in range(5):
                            view.UpdateInteraction(view.dragStart + point(50 + repeat * 3 + frame, 50 + frame), QtCore.Qt.KeyboardModifier.NoModifier)
                            if paint:
                                view.render(image)
                        elapsed = (perf_counter() - start) * 200
                        if repeat >= 2:
                            samples[variant].append(elapsed)
                row = dict(objectsPerClass = count, selected = selected, paint = paint, beforeMs = statistics.median(samples[0]),
                           afterMs = statistics.median(samples[1]), samplesMs = samples)
                result["groups"].append(row)
                print("group", count, selected, paint, round(row["beforeMs"], 3), round(row["afterMs"], 3), flush = True)
            if count == 1024 and selected == 2:
                for variant, view in enumerate(views):
                    profile = cProfile.Profile()
                    profile.runcall(view.UpdateInteraction, view.dragStart + point(91, 67), QtCore.Qt.KeyboardModifier.NoModifier)
                    stats = pstats.Stats(profile)
                    rows = sorted(((key[2], values[0], values[3]) for key, values in stats.stats.items()), key = lambda row: row[2], reverse = True)
                    result["profiles"].append(dict(workload = "group update", variant = variant, topCumulative = rows[:15]))
            for view in views:
                view.CancelInteraction()
                view.close()
                view.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        v, panel = main.viewport, main.exportPanel
        for count in (() if args.adoption_only else (128, 1024, 4096)):
            v.walls = [Wall(point(index * 1000, 0), point(index * 1000, 500), 200) for index in range(count)]
            v.furnishings = [Furnishing(definitions["washer"], point(index * 1000, 2000)) for index in range(min(count // 4, 256))]
            v.EnsureObjectIds()
            for cold in (False, True):
                samples = [[], []]
                for repeat in range(args.samples + 2):
                    for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                        if cold:
                            main.__dict__.pop("previewSceneSnapshot", None)
                        start = perf_counter()
                        arguments = (ReferencePanelMixin.RenderArguments(panel, "png", preview = True) if variant == 0
                                     else panel.RenderArguments("png", preview = True))
                        elapsed = (perf_counter() - start) * 1000
                        if repeat >= 2:
                            samples[variant].append(elapsed)
                row = dict(walls = count, furnishings = len(v.furnishings), cold = cold,
                           beforeMs = statistics.median(samples[0]), afterMs = statistics.median(samples[1]), samplesMs = samples)
                result["snapshots"].append(row)
                print("snapshot", count, cold, round(row["beforeMs"], 3), round(row["afterMs"], 3), flush = True)
        # Hide unrelated window painting while measuring result readiness.
        main.hide()
        v.walls = [Wall(point(index % 16 * 2000, index // 16 * 2000), point(index % 16 * 2000 + 1500, index // 16 * 2000), 200)
                   for index in range(128)]
        v.furnishings = [Furnishing(definitions["washer"], point(index % 16 * 2000 + 500, index // 16 * 2000 + 800)) for index in range(128)]
        v.EnsureObjectIds()
        render = panel.RenderArguments("svg", preview = True)
        render.update(bounds = (-1000, -1000, 34000, 18000), scale = 20, border = "None", titleBlock = {}, previewDocument = True)
        vector = folder / "benchmark.vector"
        vector.write_bytes(pickle.dumps(RenderPlan(**render), protocol = pickle.HIGHEST_PROTOCOL))
        image = QtGui.QImage(2560, 1440, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor("#123456"))
        frame = folder / "benchmark.frame"
        with frame.open("wb") as output:
            output.write((json.dumps(dict(width = image.width(), height = image.height(), stride = image.bytesPerLine(),
                format = image.format().value, dpiX = image.dotsPerMeterX(), dpiY = image.dotsPerMeterY())) + "\n").encode())
            output.write(image.constBits())
        for kind, path in (("png", frame), ("svg", vector)):
            samples, callbackSamples, gaps = [[], []], [[], []], [[], []]
            for repeat in range(args.samples + 2):
                for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                    worker = (ReferenceProcess if variant == 0 else ExportPreviewProcess)(v.exportOverlay)
                    ticks = []
                    timer = QtCore.QTimer()
                    timer.setInterval(1)
                    timer.timeout.connect(lambda: ticks.append(perf_counter()))
                    timer.start()
                    warmupLoop = QtCore.QEventLoop()
                    QtCore.QTimer.singleShot(10, warmupLoop.quit)
                    warmupLoop.exec()
                    renderer = None
                    start = perf_counter()
                    if variant == 0:
                        worker.results["sample"] = (kind, path, None)
                        value = worker.Request("sample", kind, lambda: {}, kind)
                        if kind == "svg":
                            renderer = ReferenceSvgPreviewRenderer(value.root)
                        callback = (perf_counter() - start) * 1000
                    else:
                        originalLoad = export_preview.LoadPreviewResult
                        if repeat == 0 and kind == "svg":
                            def ProfileLoad(*values):
                                profile = cProfile.Profile()
                                value = profile.runcall(originalLoad, *values)
                                stats = pstats.Stats(profile)
                                rows = sorted(((key[2], values[0], values[3]) for key, values in stats.stats.items()), key = lambda row: row[2], reverse = True)
                                result["profiles"].append(dict(workload = "SVG adoption", variant = 1, topCumulative = rows[:25]))
                                return value
                            export_preview.LoadPreviewResult = ProfileLoad
                        worker.requests["sample"] = kind
                        worker.current = dict(id = 1, slot = "sample", key = kind, path = path, kind = kind)
                        worker.Complete()
                        callback = (perf_counter() - start) * 1000
                        waitLoop = QtCore.QEventLoop()
                        poll = QtCore.QTimer()
                        poll.setInterval(2)
                        poll.timeout.connect(lambda: waitLoop.quit() if worker.current is None else None)
                        poll.start()
                        waitLoop.exec()
                        poll.stop()
                        export_preview.LoadPreviewResult = originalLoad
                        value = worker.Request("sample", kind, lambda: {}, kind)
                        if kind == "svg":
                            renderer = SvgPreviewRenderer.FromDocument(value)
                    elapsed = (perf_counter() - start) * 1000
                    ticks.append(perf_counter())
                    finalLoop = QtCore.QEventLoop()
                    QtCore.QTimer.singleShot(10, finalLoop.quit)
                    finalLoop.exec()
                    timer.stop()
                    gap = max((second - first for first, second in zip(ticks, ticks[1:])), default = 0) * 1000
                    if repeat >= 2:
                        samples[variant].append(elapsed)
                        callbackSamples[variant].append(callback)
                        gaps[variant].append(gap)
                    if renderer is not None:
                        renderer.deleteLater()
                    worker.Close()
                    worker.deleteLater()
                    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
            row = dict(kind = kind, transportBytes = path.stat().st_size, beforeMs = statistics.median(samples[0]),
                afterMs = statistics.median(samples[1]), callbackMs = [statistics.median(values) for values in callbackSamples],
                maxHeartbeatGapMs = [statistics.median(values) for values in gaps], samplesMs = samples, callbackSamplesMs = callbackSamples,
                heartbeatGapSamplesMs = gaps)
            result["adoption"].append(row)
            print("adoption", kind, round(row["beforeMs"], 3), round(row["afterMs"], 3), "callback", row["callbackMs"], "gap", row["maxHeartbeatGapMs"], flush = True)
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(result, indent = 2) + "\n", encoding = "utf-8")


if __name__ == "__main__":
    Main()
