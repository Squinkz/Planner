"""Live colors reuse SVG preparation, realize used art and leave scene-independent borders cached."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall
from planner_app.graphics import furnishings, palette
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.graphics.svg_preview import SvgPreviewRenderer


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.show()
    v, panel = main.viewport, main.exportPanel
    v.walls = [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), 240)]
    v.furnishings = []
    v.sceneRevision += 1
    main.sidebarTabs.setCurrentWidget(panel)
    panel.borderField.setCurrentText("Ruler")
    panel.scaleField.setValue(100)
    overlay = v.exportOverlay
    overlay.bounds = (-2000, -1500, 4000, 3000)
    v.zoom = .1 / v.basePixelsPerMillimeter
    v.panOffset = QtCore.QPointF()
    with patch.object(furnishings, "FurnishingRenderer", wraps = furnishings.FurnishingRenderer) as factory:
        main.RefreshFurnishingRenderers()
        v.grab()
        assert factory.call_count == 0, "An empty scene parsed catalog artwork"
        panel.PreviewColor("canvas", QtGui.QColor("#123456"))
        panel.PreviewColor("lines", QtGui.QColor("#abcdef"))
        v.grab()
        assert factory.call_count == 0, "Live color preview rebuilt the unused library"
        normal = v.furnishingRenderers["washer"]
        assert factory.call_count == 1 and len(v.furnishingRenderers) == 1
        assert v.furnishingRenderers["washer"] is normal
        assert v.furnishingRenderers.get("not-a-definition") is None
    # Recoloring the same source reuses parsed XML and theme-font measurements.
    with patch.object(furnishings.FurnishingSvgRenderer, "LetteringBounds", side_effect = AssertionError("Repeated font preparation")):
        with patch.object(furnishings.ElementTree, "fromstring", side_effect = AssertionError("Repeated XML parsing")):
            panel.PreviewColor("canvas", QtGui.QColor("#234567"))
            assert v.furnishingRenderers["washer"] is not normal
            v.selectedFurnishingRenderers["washer"]
    panel.colorPreviewTimer.stop()
    # Repeated changes keep the latest color but request one bounded-rate repaint.
    with patch.object(panel.colorPreviewTimer, "start", wraps = panel.colorPreviewTimer.start) as start:
        for index in range(30):
            panel.PreviewColor("lines", QtGui.QColor(index + 10, 100, 150))
        assert start.call_count == 1
        assert palette.themeColors["objectOutline"] == QtGui.QColor(39, 100, 150).name()
        for unused in range(20):
            QtTest.QTest.qWait(20)
            if not panel.colorPreviewTimer.isActive():
                break
        assert not panel.colorPreviewTimer.isActive()
        assert start.call_count == 1
    panel.ApplyView(panel.ResolvedView())
    for outputFormat in ("PNG", "SVG"):
        panel.typeField.setCurrentIndex(panel.typeField.findData(outputFormat))
        before = v.grab().toImage()
        source = overlay.snapshot if outputFormat == "PNG" else overlay.svgRenderer
        data = overlay.svgData
        first = v.WorldToViewport(QtCore.QPointF(overlay.bounds[0], overlay.bounds[1] + overlay.bounds[3]))
        sample = (first + QtCore.QPointF(80, -overlay.borderSize / 2)).toPoint()
        oldColor = before.pixelColor(sample)
        with patch.object(overlay, "BuildSnapshot", side_effect = AssertionError("Border rebuilt the PNG scene")):
            with patch.object(overlay, "renderVector", side_effect = AssertionError("Border regenerated the SVG")):
                panel.PreviewColor("border", QtGui.QColor("#b23d71"))
                after = v.grab().toImage()
                assert after.pixelColor(sample) == QtGui.QColor("#b23d71"), (outputFormat, sample, oldColor, after.pixelColor(sample))
                assert (overlay.snapshot if outputFormat == "PNG" else overlay.svgRenderer) is source
                assert overlay.svgData is data
                strips = list(overlay.rulerStrips)
                v.grab()
                assert all(first[2] is second[2] for first, second in zip(strips, overlay.rulerStrips))
                panel.SetOverride("borderColor", "#b23d71")
                v.grab()
        panel.ResetOverride("borderColor")
    # SVG palette changes update named paints in the retained vector scene.
    # Other roles may share the original RGB, so blanket color replacement
    # would incorrectly recolor labels and measurement text as well.
    with patch.object(overlay, "renderVector", side_effect = AssertionError("Color regenerated vector geometry")):
        with patch("planner_app.graphics.svg_preview.SvgClipPath", side_effect = AssertionError("Color reparsed vector clips")):
            for name, color in (("canvas", "#254768"), ("lines", "#b2c3d4"), ("grid", "#c35d72")):
                panel.PreviewColor(name, QtGui.QColor(color))
                v.grab()
                assert not overlay.previewError, overlay.previewError
                assert overlay.svgData == panel.Render("svg", preview = True, previewScene = True)
    # Named paint roles must produce the same interior as an ordinary saved SVG,
    # including text that originally shared an RGB value with the linework.
    exported = SvgPreviewRenderer(panel.Render("svg"))
    images = []
    for renderer in (overlay.svgRenderer, exported):
        image = QtGui.QImage(renderer.defaultSize(), QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        with QtGui.QPainter(image) as painter:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            renderer.render(painter)
        size = overlay.borderSize
        # The border separator is painted independently in the preview and can
        # cover the canvas's outermost pixel in the complete exported SVG.
        images.append(image.copy(size + 2, size + 2, image.width() - 2 * size - 4, image.height() - 2 * size - 4))
    assert images[0] == images[1], "Preview recoloring differs from the saved SVG"
    v.viewportRasterByteLimit = 1024 * 1024
    v.grab()
    assert overlay.svgNavigationImage is not None and overlay.svgViewImage is not None
    assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
    navigation = overlay.svgNavigationImage
    overlay.StartVectorNavigation()
    v.grab()
    assert overlay.svgNavigationImage is navigation, "Border strips displaced the navigation preview"
    main.MarkProjectClean()
    main.close()


if __name__ == "__main__":
    Main()
