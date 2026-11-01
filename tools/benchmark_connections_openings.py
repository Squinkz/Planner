"""Alternate frozen/current connected discovery and opening-heavy drag paints."""
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
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Door, MeasurementGuide
from planner_app.viewport.widget import DrawingViewport
from planner_app.viewport import scene
from fixtures.qt_connections_openings_reference_20261030 import ReferenceViewport


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--output", type = Path, default = root / "diagnostics/performance-connections-openings-20261030/benchmark.json")
    args = parser.parse_args()
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    point = QtCore.QPointF
    results = dict(python = platform.python_version(), qt = QtCore.qVersion(), platform = platform.platform(), unit = "milliseconds",
                   repeats = 5, baseline = "After containment/hover optimization pass",
                   methodology = "Alternate frozen/current views; discard one warmup and median five samples. "
                       "Discovery uses connected straight chains, including exact shape paths. Paints use a 1200x800 offscreen viewport, "
                       "measurements/tips disabled, most objects offscreen, one changed wall endpoint per sample. "
                       "Synthetic workload timings, not end-to-end pointer latency.", discovery = [], contacts = [], paint = [])
    for kind in (Wall, MeasurementGuide):
        for count in (128, 512, 1024):
            views = []
            for cls in (ReferenceViewport, DrawingViewport):
                view = cls(furnishingDefinitions = {})
                view.walls = [kind(point(index * 1000, 0), point((index + 1) * 1000, 0), 200) for index in range(count)]
                view.selectedVertex = None
                view.connectedObjectsEnabled = True
                views.append(view)
            samples = [[], []]
            for repeat in range(6):
                for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                    view = views[variant]
                    start = perf_counter()
                    attached = view.AttachedVertices(view.walls[0], captureAll = True)
                    elapsed = (perf_counter() - start) * 1000
                    assert len(attached) == 2 * (count - 1)
                    if repeat:
                        samples[variant].append(elapsed)
            row = dict(objects = count, kind = kind.__name__, beforeMs = statistics.median(samples[0]), afterMs = statistics.median(samples[1]), samplesMs = samples)
            results["discovery"].append(row)
            print("discovery", kind.__name__, count, round(row["beforeMs"], 3), round(row["afterMs"], 3), flush = True)
            if kind is Wall and count == 512:
                counts = []
                for view in views:
                    with patch.object(scene.Paths, "Intersects", wraps = scene.Paths.Intersects) as contact:
                        view.AttachedVertices(view.walls[0], captureAll = True)
                        counts.append(contact.call_count)
                results["contacts"].append(dict(objects = count, before = counts[0], after = counts[1]))
            for view in views:
                view.close()
    for count, stride in ((512, 512), (512, 128), (128, 8), (512, 16), (512, 8), (1024, 16)):
        views, images = [], []
        for cls in (ReferenceViewport, DrawingViewport):
            view = cls(furnishingDefinitions = {})
            view.resize(1200, 800)
            view.showMeasurements = view.showTips = False
            view.walls = [Wall(point(index % 32 * 2000, index // 32 * 2000),
                               point(index % 32 * 2000 + 1400, index // 32 * 2000), 200) for index in range(count)]
            view.windows = [Door(wall, .2, .7) for wall in view.walls[::stride]]
            view.selectedWall, view.selectedVertex = view.walls[-1], None
            view.dragStart, view.isDragging = point(400, 300), True
            image = QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            view.render(image)
            views.append(view)
            images.append(image)
        samples = [[], []]
        for repeat in range(6):
            for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                view = views[variant]
                view.walls[-1].secondVertex.setX((count - 1) % 32 * 2000 + 1401 + repeat)
                start = perf_counter()
                view.render(images[variant])
                elapsed = (perf_counter() - start) * 1000
                if repeat:
                    samples[variant].append(elapsed)
        row = dict(walls = count, openings = len(views[0].windows), beforeMs = statistics.median(samples[0]),
                   afterMs = statistics.median(samples[1]), samplesMs = samples)
        results["paint"].append(row)
        print("drag paint", count, row["openings"], round(row["beforeMs"], 3), round(row["afterMs"], 3), flush = True)
        for view in views:
            view.close()
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(results, indent = 2) + "\n", encoding = "utf-8")


if __name__ == "__main__":
    Main()
