"""Exposed-strip culling preserves pixels and cached furnishing validation."""
import json
import os
from pathlib import Path
from statistics import median
import sys
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner_app.models import Wall, Door, Stair, Furnishing
from planner_app.viewport.widget import DrawingViewport
from planner_app.viewport import rendering
from check_pan_dpi import CompareDirect


def Main():
    app = QtWidgets.QApplication([])
    viewport = DrawingViewport()
    viewport.resize(1000, 700)
    viewport.performanceTimer.stop()
    viewport.zoom = .25
    point = QtCore.QPointF
    wall = Wall(point(-12000, 3000), point(12000, 3000))
    stair = Stair(point(-10000, 4000), point(-10000, -4000), 800)
    viewport.walls = [wall, stair]
    viewport.windows = [Door(wall, .3, .35), Door(wall, .7, .75)]
    viewport.furnishings = [Furnishing(viewport.furnishingDefinitions["desk"],
                                      point((column - 10) * 1400, (row - 5) * 1400))
                             for row in range(10) for column in range(20)]
    viewport.EnsureObjectIds()
    viewport.show()
    app.processEvents()
    viewport.performanceLabel.hide()
    viewport.isPanning = True
    drawScene = viewport.DrawScene
    results = {}
    for cull in (False, True):
        viewport.panOffset = point()
        viewport.viewportPanRaster = None
        viewport.grab()
        validationKeys = set(viewport.furnishingValidationCache)
        durations = []

        def DrawScene(*args, **kwargs):
            if not cull:
                kwargs.pop("dirtyRects", None)
            return drawScene(*args, **kwargs)

        with patch.object(viewport, "DrawScene", side_effect = DrawScene), \
             patch.object(rendering, "DrawFurnishing", wraps = rendering.DrawFurnishing) as furnishings, \
             patch.object(rendering, "DrawOpeningSymbol", wraps = rendering.DrawOpeningSymbol) as openings:
            for frame in range(20):
                viewport.panOffset += point(3, 1)
                started = perf_counter()
                viewport.grab()
                durations.append((perf_counter() - started) * 1000)
            results["culled" if cull else "unculled"] = {
                "medianMs": round(median(durations), 3),
                "furnishingCalls": furnishings.call_count,
                "openingCalls": openings.call_count,
                "frames": len(durations),
            }
        if cull:
            assert validationKeys <= set(viewport.furnishingValidationCache)
        CompareDirect(viewport)

    assert results["unculled"]["furnishingCalls"] >= 2000
    assert results["culled"]["furnishingCalls"] < results["unculled"]["furnishingCalls"] / 4
    assert results["culled"]["openingCalls"] < results["unculled"]["openingCalls"] / 4

    # Bring the objects across the viewport edge and back in narrow strips.
    # These comparisons exercise the bound padding, including door swings.
    for start in (point(400, 0), point(-400, 0), point(0, 250), point(0, -250)):
        viewport.panOffset = start
        viewport.viewportPanRaster = None
        viewport.grab()
        for delta in (point(9, 3), point(-17, -5), point(8, 2)):
            viewport.panOffset += delta
            CompareDirect(viewport)
    viewport.close()
    report = Path(__file__).resolve().parent.parent / "diagnostics" / "pan-performance-20261008.json"
    report.write_text(json.dumps(results, indent = 2) + "\n", encoding = "utf-8")
    print("PASS: strip culling reduces draw calls, retains validation and matches direct pixels.")
    print(json.dumps(results))


if __name__ == "__main__":
    Main()
