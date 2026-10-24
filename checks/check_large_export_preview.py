"""Oversized exports retain bounded previews and native visible detail."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall
from planner_app.export_plan import RenderPlan
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.graphics.palette import themeColors


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.show()
    v = main.viewport
    v.walls = [Wall(QtCore.QPointF(-2000, 0), QtCore.QPointF(2000, 0), 240)]
    v.EnsureObjectIds()
    v.sceneRevision += 1
    main.sidebarTabs.setCurrentWidget(main.exportPanel)
    overlay = v.exportOverlay
    overlay.bounds = (-6000, -6000, 12000, 12000)
    overlay.scale = 1000
    overlay.drawRuler = False
    overlay.vignetteStrength = 0
    v.viewportRasterByteLimit = 16 * 1024 * 1024
    v.zoom = .05 / v.basePixelsPerMillimeter
    v.panOffset = QtCore.QPointF()
    v.grab()
    assert overlay.snapshot is not None and not overlay.previewError
    assert 0 < overlay.snapshotSampling < 1
    assert overlay.snapshot.width() * overlay.snapshot.height() <= 4_000_000
    assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
    v.zoom = 1 / v.basePixelsPerMillimeter
    overlay.navigationTimer.stop()
    image = v.grab().toImage()
    assert overlay.detailImage is not None
    wallPoint = v.WorldToViewport(QtCore.QPointF(0, 0)).toPoint()
    assert image.pixelColor(wallPoint) == QtGui.QColor(themeColors["wallFill"])
    detail = overlay.detailImage
    v.grab()
    assert overlay.detailImage is detail
    oldBounds = QtCore.QRectF(overlay.detailBounds)
    v.panOffset += QtCore.QPointF(150, 75)
    overlay.StartVectorNavigation()
    v.grab()
    assert overlay.detailImage is detail
    QtTest.QTest.qWait(230)
    v.grab()
    assert overlay.detailBounds != oldBounds
    assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
    overlay.scale = 3000
    overlay.drawRuler = True
    overlay.borderStyle = "Ruler + Reference Zones"
    overlay.navigationTimer.stop()
    v.grab()
    assert overlay.snapshot is not None and not overlay.previewError
    assert overlay.snapshotSampling < 1 and not overlay.rulerStrips
    assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
    overlay.drawRuler = False
    data = main.BuildProjectData(includeHistory = False)
    data["settings"].update(main.exportPanel.CaptureView())
    for scale, outputFormat in ((1000, "png"), (3000, "svg")):
        try:
            RenderPlan("preview.plan", scale, overlay.bounds, outputFormat = outputFormat,
                       projectData = data, applyTheme = False)
        except ValueError as error:
            assert "32,767" in str(error)
        else:
            raise AssertionError("File export limits were bypassed")
    assert RenderPlan("preview.plan", 1000, overlay.bounds, outputFormat = "svg",
                      projectData = data, applyTheme = False).startswith(b"<?xml")
    overlay.outputFormat = "svg"
    overlay.renderVector = lambda outputFormat: RenderPlan(
        "preview.plan", overlay.scale, overlay.bounds, outputFormat = outputFormat,
        projectData = data, applyTheme = False, preview = True)
    v.zoom = .05 / v.basePixelsPerMillimeter
    v.panOffset = QtCore.QPointF()
    overlay.navigationTimer.stop()
    v.grab()
    assert not overlay.previewError, overlay.previewError
    assert overlay.svgRenderer.defaultSize().width() == 36000
    assert overlay.svgNavigationImage.width() <= 4096
    assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
    # Opaque PNG files omit alpha; transparent themes retain it.
    canvas = themeColors["canvas"]
    try:
        for color, colorType in (("#ffffff", 2), ("#80ffffff", 6)):
            themeColors["canvas"] = color
            image = RenderPlan("preview.plan", 100, (-100, -100, 200, 200),
                               projectData = data, applyTheme = False)
            buffer = QtCore.QBuffer()
            buffer.open(QtCore.QIODevice.OpenModeFlag.ReadWrite)
            assert image.save(buffer, "PNG")
            assert bytes(buffer.data())[25] == colorType
    finally:
        themeColors["canvas"] = canvas
    main.close()


if __name__ == "__main__":
    Main()
