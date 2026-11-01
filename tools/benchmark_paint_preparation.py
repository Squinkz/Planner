"""Alternating frozen/current paint preparation and rendered-frame measurements."""
import gc
import json
import os
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.models import Furnishing, Label, Wall
from planner_app.viewport.widget import DrawingViewport
from fixtures.paint_preparation_reference_20261031 import ReferenceViewport


def CreateViewport(cls, count, near):
    view = cls()
    point = QtCore.QPointF
    view.resize(1200, 800)
    view.performanceTimer.stop()
    view.showTips = view.showMeasurements = False
    view.walls = [Wall(point(index * 6000, 0), point(index * 6000 + 4000, 0), 200) for index in range(count)]
    view.furnishings = [Furnishing(view.furnishingDefinitions["desk"], point(index * 6000 + 2000, 10000)) for index in range(count)]
    view.labels = [Label(point(index * 6000, 15000), "Label") for index in range(count)]
    if near:
        view.furnishings[0].firstVertex.setY(-400)
        view.furnishings[0].secondVertex.setY(400)
    view.snapEnabled = view.connectedEnabled = False
    view.dragStart = point(400, 300)
    view.isDragging = True
    view.selectedWall = view.furnishings[0]
    return view


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyle("Fusion")
    LoadApplicationFonts(app)
    collected = gc.isenabled()
    gc.disable()
    results = []
    try:
        for count, near in ((128, False), (1024, False), (4096, False), (1024, True)):
            caseId = f"{count}-{'near' if near else 'distant'}"
            if os.environ.get("PLANNER_PAINT_BENCH_CASE", caseId) != caseId:
                continue
            views = [CreateViewport(cls, count, near) for cls in (ReferenceViewport, DrawingViewport)]
            images = [QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied) for view in views]
            for workload in ("furnishing-validation", "label-validation", "coincident", "combined-preparation", "rendered-frame", "preparation-miss", "wall-validation"):
                if workload == "rendered-frame" and count == 4096:
                    continue
                if workload == "wall-validation" and (count != 1024 or near):
                    continue
                samples = [[], []]
                frameCount = 1 if count >= 4096 or workload in ("preparation-miss", "rendered-frame") else 3
                for iteration in range(11):
                    for variant in ((0, 1) if iteration % 2 == 0 else (1, 0)):
                        view = views[variant]
                        obj = (view.labels[0] if workload == "label-validation" else view.walls[0]
                               if workload == "wall-validation" else view.furnishings[0])
                        if workload == "preparation-miss":
                            view.__dict__.pop("architecturalValidation", None)
                            view.renderChanges.placementChanges = None
                            for member in view.walls + view.windows + view.furnishings + view.labels:
                                member.__dict__.pop("_coincidentRecordCache", None)
                        started = perf_counter()
                        for frame in range(frameCount):
                            step = 1 if iteration % 2 == 0 else -1
                            obj.firstVertex.setX(obj.firstVertex.x() + step)
                            obj.secondVertex.setX(obj.secondVertex.x() + step)
                            if workload in ("furnishing-validation", "label-validation", "combined-preparation", "preparation-miss", "wall-validation"):
                                view.InvalidArchitecturalObjects()
                            if workload in ("coincident", "combined-preparation", "preparation-miss"):
                                view.CoincidentObjectGroups()
                            if workload == "rendered-frame":
                                view.render(images[variant])
                        duration = (perf_counter() - started) * 1000 / frameCount
                        if iteration >= 2:
                            samples[variant].append(duration)
                results.append(dict(countPerCategory = count, nearCollision = near, workload = workload,
                                    beforeMs = median(samples[0]), afterMs = median(samples[1]),
                                    beforeSamplesMs = samples[0], afterSamplesMs = samples[1]))
            for view in views:
                view.close()
        output = dict(python = platform.python_version(), qt = QtCore.qVersion(), platform = platform.platform(),
                      methodology = "Frozen/current independent offscreen 1200x800 viewports, each with N walls, N furnishings, N labels; measurements, snapping and connections disabled. "
                                    "Two warmup rounds, nine alternating sample rounds, three explicit model updates per sample except one update for preparation misses/rendered frames and the N=4096 fixture. "
                                    "Misses clear preparation and coincident keys outside the timer but retain ordinary geometry caches. Rendered frames include movement plus synchronous QWidget.render only, "
                                    "without input dispatch, sidebar signals or display latency. GC disabled equally for both. No simultaneous benchmark processes.", cases = results)
        suffix = "-" + os.environ["PLANNER_PAINT_BENCH_CASE"] if "PLANNER_PAINT_BENCH_CASE" in os.environ else ""
        destination = root / f"diagnostics/performance-paint-preparation-20261031/benchmark{suffix}.json"
        destination.write_text(json.dumps(output, indent = 2), encoding = "utf-8")
        print(json.dumps([{key: value for key, value in result.items() if not key.endswith("SamplesMs")} for result in results], indent = 2))
    finally:
        if collected:
            gc.enable()


if __name__ == "__main__":
    Main()
