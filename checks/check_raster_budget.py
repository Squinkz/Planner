"""Aggregate surface admission, resize/mode turnover and low-budget fallbacks."""
import json
import math
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.viewport.widget import DrawingViewport
from check_scene_render_cache import CompareDirect


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.sessionTimer.stop()
    main.sessionPollTimer.stop()
    main.show()
    app.processEvents()
    v = main.viewport
    v.performanceTimer.stop()
    v.resize(1000, 700)
    v.walls = [Wall(QtCore.QPointF(-1500, 0), QtCore.QPointF(1500, 0), 240)]
    v.EnsureObjectIds()
    v.SetRenderDiagnosticsEnabled(True)
    v.show()
    app.processEvents()
    budget = v.rasterCacheBudget
    samples = []
    for width, height in ((1000, 700), (1800, 1100), (801, 603), (1200, 800)):
        v.resize(width, height)
        ratio = v.devicePixelRatioF()
        frameBytes = math.ceil(width * ratio) * math.ceil(height * ratio) * 4
        v.viewportRasterByteLimit = frameBytes
        v.grab()
        assert v.viewportScene is not None and v.viewportBackground is None, (v.width(), v.height(), frameBytes, budget.RetainedBytes())
        assert budget.RetainedBytes() == frameBytes
        with patch.object(v, "DrawScene", wraps = v.DrawScene) as draw:
            v.grab()
            assert draw.call_count == 0
        v.isPanning = True
        v.grab()
        for offset in (QtCore.QPointF(3, 1), QtCore.QPointF(.25, .3), QtCore.QPointF(4, 2)):
            v.panOffset += offset
            v.grab()
            assert budget.RetainedBytes() <= frameBytes
        v.isPanning = False
        CompareDirect(v)
        samples.append({"width": width, "height": height, "retainedBytes": budget.RetainedBytes(), "limitBytes": frameBytes})
    v.viewportRasterByteLimit = 0
    v.grab()
    assert budget.RetainedBytes() == 0
    assert v.viewportBackground is v.viewportScene is v.viewportPanRaster is None
    v.viewportRasterByteLimit = 128 * 1024 * 1024
    v.grab()
    assert v.viewportScene is not None
    # Exercise 4K/DPR-2 allocation without requiring a physical high-DPI monitor.
    large = DrawingViewport()
    large.performanceTimer.stop()
    large.resize(3840, 2160)
    large.walls = v.walls
    with patch.object(large, "devicePixelRatioF", return_value = 2.0):
        large.grab()
        assert large.viewportScene is not None and large.viewportBackground is None
        assert large.rasterCacheBudget.RetainedBytes() == 3840 * 2160 * 16
        assert large.rasterCacheBudget.peakBytes <= large.viewportRasterByteLimit
        with patch.object(large, "DrawScene", wraps = large.DrawScene) as draw:
            large.grab()
            assert draw.call_count == 0
    samples.append({"width": 3840, "height": 2160, "simulatedDpr": 2,
                    "retainedBytes": large.rasterCacheBudget.RetainedBytes(), "limitBytes": large.viewportRasterByteLimit})
    large.rasterCacheBudget.Clear("scene", "fixture-end")
    large.close()
    overlay = v.exportOverlay
    overlay.SetActive(True)
    assert budget.RetainedBytes() == 0
    overlay.scale = 200
    v.viewportRasterByteLimit = 2 * 1024 * 1024
    v.grab()
    assert overlay.snapshot is not None and not overlay.previewError
    assert budget.RetainedBytes() <= v.viewportRasterByteLimit
    # Tight native PNG crops fit even when expanded auto coverage does not.
    overlay.bounds = (-100, -100, 200, 200)
    overlay.snapshotKey = None
    v.viewportRasterByteLimit = 40000
    v.grab()
    assert overlay.snapshot is not None and overlay.snapshot.width() == 40
    assert overlay.snapshot.height() == 40 and not overlay.previewError
    # Reserve no room for strips: the ruler uses the direct path, keeping the snapshot.
    overlay.drawRuler = True
    v.viewportRasterByteLimit = overlay.snapshot.sizeInBytes()
    v.grab()
    assert overlay.snapshot is not None and overlay.rulerStrips == []
    assert budget.RetainedBytes() <= v.viewportRasterByteLimit
    v.viewportRasterByteLimit = 100
    v.grab()
    assert overlay.snapshot is None and overlay.previewError
    assert budget.RetainedBytes() <= 100
    # Build genuine SVG bytes, then force a budget smaller than the viewport image.
    overlay.bounds = (-2000, -1500, 4000, 3000)
    overlay.drawRuler = False
    overlay.outputFormat = "svg"
    from planner_app.export_plan import RenderPlan
    overlay.renderVector = lambda outputFormat: RenderPlan(Path("budget.plan"), overlay.scale, overlay.bounds,
                                                           outputFormat = outputFormat, projectData = main.BuildProjectData(), applyTheme = False)
    v.viewportRasterByteLimit = 1024 * 1024
    v.grab()
    assert overlay.svgNavigationImage is not None and overlay.svgViewImage is not None
    assert overlay.svgViewImage.devicePixelRatio() < v.devicePixelRatioF()
    assert budget.RetainedBytes() <= v.viewportRasterByteLimit
    svgData = overlay.svgData
    for index in range(12):
        v.resize(1000 + index * 7, 700 + index * 3)
        v.panOffset += QtCore.QPointF(13, -5)
        v.grab()
        assert overlay.svgData == svgData
        assert budget.RetainedBytes() <= v.viewportRasterByteLimit
    for index in range(3):
        overlay.outputFormat = "png"
        v.grab()
        assert overlay.svgNavigationImage is overlay.svgViewImage is None
        assert budget.RetainedBytes() <= v.viewportRasterByteLimit
        overlay.outputFormat = "svg"
        v.grab()
        assert overlay.snapshot is None
        assert budget.RetainedBytes() <= v.viewportRasterByteLimit
    overlay.SetActive(False)
    assert budget.RetainedBytes() == 0
    v.viewportRasterByteLimit = 128 * 1024 * 1024
    v.grab()
    report = v.renderDiagnostics.Report()
    assert report["rasterCache"]["retainedBytes"] <= report["rasterCache"]["limitBytes"]
    assert any(event["kind"] == "rasterCache" and event["action"] == "refused" for event in report["events"])
    (Path(__file__).resolve().parent.parent / "diagnostics/raster-budget-20261008.json").write_text(
        json.dumps({"resizeSamples": samples, "rasterCache": report["rasterCache"]}, indent = 2) + "\n", encoding = "utf-8")
    v.SetRenderDiagnosticsEnabled(False)
    main.close()


if __name__ == "__main__":
    Main()
