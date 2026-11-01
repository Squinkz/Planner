"""Alternate frozen/current drag paints, validation and railing rebuilds."""
import argparse
import json
import math
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
from planner_app.models import Wall, Railing, Counter
from planner_app.viewport.widget import DrawingViewport
from fixtures.qt_drag_railing_reference_20261030 import ReferenceViewport


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--output", type = Path, default = root / "diagnostics/performance-hotspots-20261030/benchmark.json")
    args = parser.parse_args()
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    results = dict(python = platform.python_version(), platform = platform.platform(), qt = QtCore.qVersion(),
                   viewport = [1200, 800], repeats = 5, unit = "milliseconds",
                   methodology = "Alternate frozen/current methods; discard one warmup, median of five. "
                       "Drag paints mutate one wall endpoint each frame; measurements/tips disabled, "
                       "most objects offscreen. Railing rebuilds vary run length, preserving post count. "
                       "Synthetic workloads, not end-to-end input latency or universal frame rates.",
                   validation = [], dragPaint = [], railing = [])
    point = QtCore.QPointF
    for count, mixed in ((128, False), (512, False), (1024, False), (512, True)):
        views, images = [], []
        for cls in (ReferenceViewport, DrawingViewport):
            view = cls(furnishingDefinitions = {})
            view.resize(1200, 800)
            view.showMeasurements = view.showTips = False
            view.walls = [Wall(point((index % 32) * 2000, (index // 32) * 2000),
                               point((index % 32) * 2000 + 1000, (index // 32) * 2000), 200) for index in range(count)]
            if mixed:
                view.walls.extend(Counter(point(index * 8000, 600), point(index * 8000 + 1200, 600), 600) for index in range(32))
            image = QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            view.render(image)
            view.selectedWall = view.walls[0]
            view.selectedVertex = None
            view.dragStart = point(400, 400)
            view.isDragging = True
            views.append(view)
            images.append(image)
        for mode in ("validation", "dragPaint"):
            samples = [[], []]
            for repeat in range(6):
                for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                    view = views[variant]
                    view.walls[0].secondVertex.setX(1001 + repeat)
                    started = perf_counter()
                    if mode == "validation":
                        view.InvalidArchitecturalObjects()
                    else:
                        view.render(images[variant])
                    elapsed = (perf_counter() - started) * 1000
                    if repeat:
                        samples[variant].append(elapsed)
            results[mode].append(dict(walls = count, counters = 32 if mixed else 0,
                beforeMs = statistics.median(samples[0]), afterMs = statistics.median(samples[1]), samplesMs = samples))
            print(mode, count, "mixed" if mixed else "walls", *(round(statistics.median(values), 3) for values in samples), flush = True)
        for view in views:
            view.close()
    for angle in (0, 37):
        direction = point(math.cos(math.radians(angle)), math.sin(math.radians(angle)))
        for count in (64, 256, 512):
            views = []
            for cls in (ReferenceViewport, DrawingViewport):
                view = cls(furnishingDefinitions = {})
                view.walls = [Railing(point(), direction * (count * 1000), 80, autosize = False, manualPostCount = count)]
                views.append(view)
            samples = [[], []]
            for repeat in range(6):
                for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                    view = views[variant]
                    view.walls[0].secondVertex = direction * (count * 1000 + repeat)
                    started = perf_counter()
                    view.ConnectedRailingPath(view.walls, includeMeasurements = False)
                    elapsed = (perf_counter() - started) * 1000
                    if repeat:
                        samples[variant].append(elapsed)
            results["railing"].append(dict(posts = count, angle = angle, beforeMs = statistics.median(samples[0]),
                                          afterMs = statistics.median(samples[1]), samplesMs = samples))
            print("railing", count, angle, *(round(statistics.median(values), 3) for values in samples), flush = True)
            for view in views:
                view.close()
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(results, indent = 2) + "\n", encoding = "utf-8")


if __name__ == "__main__":
    Main()
