"""Measure warmed viewport paints without input-rate limits or session writes.

Run with an optional JSON output path. Times exclude cProfile overhead; profiles
use a separate pass. QT_SCALE_FACTOR can be set to check high-DPI displays.
"""
import cProfile
import io
import json
import os
from pathlib import Path
import pstats
import statistics
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner_app.viewport.widget import DrawingViewport
from planner_app.models import Wall, Stair, Furnishing
from planner_app.project_codec import DecodeProject
from planner_app.graphics.theme import BuildStyle


def Measure(viewport, mode):
    point = QtCore.QPointF
    viewport.isPanning = mode == "pan"
    for frame in range(4):
        viewport.repaint()
    viewport.renderSamples.clear()
    for frame in range(40):
        if mode == "pan":
            viewport.panOffset = point(frame * .7, frame * .3)
        else:
            viewport.hoverPosition = point(100 + frame, 150)
        viewport.repaint()
    durations = [duration for timestamp, duration in viewport.renderSamples]
    profiler = cProfile.Profile()
    profiler.enable()
    for frame in range(12):
        if mode == "pan":
            viewport.panOffset = point(frame * .7, frame * .3)
        else:
            viewport.hoverPosition = point(100 + frame, 150)
        viewport.repaint()
    profiler.disable()
    viewport.isPanning = False
    stream = io.StringIO()
    pstats.Stats(profiler, stream = stream).strip_dirs().sort_stats("cumulative").print_stats(22)
    return {"medianMs": statistics.median(durations),
            "p95Ms": sorted(durations)[int(len(durations) * .95)], "profile": stream.getvalue()}


def Main():
    app = QtWidgets.QApplication([])
    app.setStyleSheet(BuildStyle())
    viewport = DrawingViewport()
    viewport.resize(1440, 900)
    viewport.performanceTimer.stop()
    viewport.show()
    app.processEvents()
    point = QtCore.QPointF
    results = {}
    for kind, count in (("blank", 0), ("furnishings", 50), ("furnishings", 200),
                        ("walls", 50), ("walls", 200), ("mixed", 200)):
        viewport.walls, viewport.furnishings = [], []
        columns = max(1, int(count ** .5))
        viewport.zoom = min(1, 600 / (max(1, count / columns) * 650))
        viewport.panOffset = point()
        for index in range(count):
            start = point((index % columns - columns / 2) * 3000,
                          (index // columns - count / columns / 2) * 3000)
            if kind in ("walls", "mixed"):
                viewport.walls.append(Wall(start, start + point(2200, 0)))
            if kind in ("furnishings", "mixed"):
                viewport.furnishings.append(Furnishing(viewport.furnishingDefinitions["desk"], start + point(1000, 1000)))
            if kind == "mixed" and index % 4 == 0:
                viewport.walls.append(Stair(start + point(1800, 1200), start + point(1800, 2700), 800))
        for mode in ("hover", "pan"):
            key = f"{kind}-{count}-{mode}"
            results[key] = Measure(viewport, mode)
            print(f"{key}: {results[key]['medianMs']:.2f} ms", flush = True)
    recovery = Path(os.environ["LOCALAPPDATA"]) / "Planner/session.json"
    if recovery.exists():
        project = json.loads(recovery.read_text(encoding = "utf-8"))["project"]
        project.pop("history", None)
        walls, windows, furnishings, groups, hidden, flags, view, labels = DecodeProject(project, viewport.furnishingDefinitions)
        viewport.walls, viewport.windows, viewport.furnishings, viewport.labels = walls, windows, furnishings, labels
        viewport.objectGroups, viewport.hiddenObjects = groups, hidden
        viewport.hiddenObjectIds = {id(obj) for obj in hidden}
        for name in ("visibility", "showMeasurements", "measurementVisibility", "measurementSettings", "unitsMode"):
            if name in flags:
                setattr(viewport, name, flags[name])
        viewport.zoom, viewport.panOffset = view["zoom"], view["pan"]
        results["sessionCounts"] = {"walls": len(walls), "openings": len(windows),
                                    "furnishings": len(furnishings), "labels": len(labels)}
        for mode in ("hover", "pan"):
            key = "session-" + mode
            results[key] = Measure(viewport, mode)
            print(f"{key}: {results[key]['medianMs']:.2f} ms", flush = True)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(results, indent = 2), encoding = "utf-8")
    viewport.close()


if __name__ == "__main__":
    Main()
