"""Compare this pass with frozen methods after the first drag/railing fixes."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall
from planner_app.viewport.widget import DrawingViewport
from fixtures.qt_containment_hover_reference_20261030 import ReferenceViewport
from check_numpy_containment import MakeWalls


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--output", type = Path, default = root / "diagnostics/performance-next-20261030/benchmark.json")
    args = parser.parse_args()
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    results = dict(python = platform.python_version(), qt = QtCore.qVersion(), platform = platform.platform(),
                   unit = "milliseconds", repeats = 5, baseline = "After first drag-validation/railing pass",
                   methodology = "Alternating frozen/current views; discard a warmup and median five samples. "
                       "1200x800 offscreen paints, no measurements/tips. Sparse walls mostly offscreen. "
                       "Warm hover averages ten distinct pointer queries per sample; warm containment averages 100 calls. "
                       "Synthetic workloads, not end-to-end input latency.", containment = [], hover = [], paint = [])
    point = QtCore.QPointF
    for count, scene in ((128, "grid"), (512, "grid"), (1024, "grid"), (2048, "grid"), (4096, "grid"),
                         (1024, "mixed"), (1024, "coincident")):
        views = []
        for cls in (ReferenceViewport, DrawingViewport):
            view = cls(furnishingDefinitions = {})
            view.resize(1200, 800)
            view.showMeasurements = view.showTips = False
            if scene == "mixed":
                view.walls = MakeWalls(count)
            else:
                view.walls = [Wall(point((index % 32) * 2000, (index // 32) * 2000),
                                   point((index % 32) * 2000 + 1000, (index // 32) * 2000), 200) for index in range(count)]
                if scene == "coincident":
                    for wall in view.walls:
                        wall.firstVertex, wall.secondVertex = point(), point(1000, 0)
            view.ContainedWalls()
            views.append(view)
        for mode in ("recompute", "warm"):
            samples = [[], []]
            for repeat in range(6):
                for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                    view = views[variant]
                    calls = 100 if mode == "warm" else 1
                    if mode == "recompute":
                        view.containedWallKey = None
                    start = perf_counter()
                    for index in range(calls):
                        view.ContainedWalls()
                    elapsed = (perf_counter() - start) * 1000 / calls
                    if repeat:
                        samples[variant].append(elapsed)
            record = dict(objects = count, scene = scene, mode = mode, beforeMs = statistics.median(samples[0]),
                          afterMs = statistics.median(samples[1]), samplesMs = samples)
            results["containment"].append(record)
            print("containment", count, scene, mode, round(record["beforeMs"], 3), round(record["afterMs"], 3), flush = True)
        if scene == "grid" and count in (512, 1024):
            for mode in ("empty", "interior-empty", "endpoint", "cold-empty", "cold-endpoint"):
                samples = [[], []]
                for view in views:
                    view.HitTest(point(-100000, -100000))
                for repeat in range(6):
                    for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                        view = views[variant]
                        calls = 1 if mode.startswith("cold-") else 10
                        if mode.startswith("cold-"):
                            view.hitTestScene = None
                        start = perf_counter()
                        for index in range(calls):
                            if mode == "interior-empty":
                                position = view.WorldToViewport(point(1500 + repeat * .01, 1000 + index * .01))
                            elif mode.endswith("empty"):
                                position = point(-100000 + repeat + index * .01, -100000)
                            else:
                                position = view.WorldToViewport(view.walls[-1].secondVertex) + point(index * .01, 0)
                            view.HitTest(position)
                        elapsed = (perf_counter() - start) * 1000 / calls
                        if repeat:
                            samples[variant].append(elapsed)
                record = dict(objects = count, mode = mode, beforeMs = statistics.median(samples[0]),
                              afterMs = statistics.median(samples[1]), samplesMs = samples)
                results["hover"].append(record)
                print("hover", count, mode, round(record["beforeMs"], 3), round(record["afterMs"], 3), flush = True)
            images = [QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied) for view in views]
            for mode in ("hover", "zoom", "drag"):
                for index, view in enumerate(views):
                    view.hoverPosition = point(60, 60)
                    if mode == "drag":
                        view.dragStart = point(400, 300)
                        view.isDragging = True
                        view.selectedWall = view.walls[0]
                        view.selectedVertex = None
                    view.render(images[index])
                samples = [[], []]
                for repeat in range(6):
                    for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                        view = views[variant]
                        if mode == "drag":
                            view.walls[0].secondVertex.setX(1001 + repeat)
                        if mode == "zoom":
                            view.hoverPosition = view.WorldToViewport(view.walls[0].firstVertex)
                            view.ZoomBy(1.05, view.hoverPosition)
                        else:
                            view.hoverPosition = point(60 + repeat, 60)
                        start = perf_counter()
                        view.render(images[variant])
                        elapsed = (perf_counter() - start) * 1000
                        if repeat:
                            samples[variant].append(elapsed)
                record = dict(objects = count, mode = mode, beforeMs = statistics.median(samples[0]),
                              afterMs = statistics.median(samples[1]), samplesMs = samples)
                results["paint"].append(record)
                print("paint", count, mode, round(record["beforeMs"], 3), round(record["afterMs"], 3), flush = True)
        for view in views:
            view.close()
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(results, indent = 2) + "\n", encoding = "utf-8")


if __name__ == "__main__":
    Main()
