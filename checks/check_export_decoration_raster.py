"""PNG decorations stay rasterized, filtered and cached, including budget fallbacks."""
import math
import os
from pathlib import Path
import sys
import numpy as np
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow
from planner_app.graphics.scale_bar import DrawScaleBar
from planner_app.export_settings import scaleBarStyles


class DecorationPainter(QtGui.QPainter):
    def __init__(self, image):
        super().__init__(image)
        self.bitmaps = []
        self.vectorCalls = 0

    def drawImage(self, rect, image, *args):
        assert self.testRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        self.bitmaps.append(image.size())
        super().drawImage(rect, image, *args)

    def drawPicture(self, *args):
        self.vectorCalls += 1
        super().drawPicture(*args)

    def fillPath(self, *args):
        self.vectorCalls += 1
        super().fillPath(*args)

    def fillRect(self, *args):
        self.vectorCalls += 1
        super().fillRect(*args)


def AssertPixelsClose(first, second, context):
    # Qt quantizes clipped/translated raster paths and filtered image origins;
    # tolerate only a few 8-bit levels, not shifted geometry or sharp vectors.
    assert first.size() == second.size() and first.format() == second.format(), context
    firstPixels = np.frombuffer(first.constBits(), dtype = np.uint8).astype(np.int16)
    secondPixels = np.frombuffer(second.constBits(), dtype = np.uint8).astype(np.int16)
    difference = int(np.max(np.abs(firstPixels - secondPixels)))
    assert difference <= 6, (context, difference)


def Main():
    with ExampleWindow() as (main, folder):
        v, panel = main.viewport, main.exportPanel
        main.sidebarTabs.setCurrentWidget(panel)
        overlay = v.exportOverlay
        overlay.outputFormat = "png"
        for physical in (False, True):
            scale = 300 * 1000 / (25.4 * 100) if physical else 80
            overlay.scale = scale
            overlay.architecturalScale = 100 if physical else None
            plot = QtCore.QRectF(0, 0, 1600, 900)
            bounds = (137, -263, plot.width() * 1000 / scale, plot.height() * 1000 / scale)
            factor = 1.25
            size = QtCore.QSize(math.ceil(plot.width() * factor + 40), math.ceil(plot.height() * factor + 40))
            for density in (.5, 1, 2):
                overlay.rasterDensity = density
                for style in scaleBarStyles:
                    options = dict(enabled = True, divisionMode = "Subdivided", style = style)
                    overlay.scaleBar = options
                    native = QtGui.QImage(round(plot.width() * density), round(plot.height() * density), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                    native.fill(QtCore.Qt.GlobalColor.transparent)
                    with QtGui.QPainter(native) as painter:
                        painter.scale(density, density)
                        painter.setFont(v.font())
                        DrawScaleBar(painter, plot, options, scale, v.unitsMode, bounds, v.gridOrigin)
                    reference = QtGui.QImage(size, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                    reference.fill(QtCore.Qt.GlobalColor.transparent)
                    with QtGui.QPainter(reference) as painter:
                        painter.translate(9.25, 13.75)
                        painter.scale(factor, factor)
                        painter.setClipRect(plot)
                        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
                        painter.drawImage(plot, native)
                    for fallback in (False, True):
                        actual = QtGui.QImage(size, reference.format())
                        actual.fill(QtCore.Qt.GlobalColor.transparent)
                        if fallback:
                            v.rasterCacheBudget.Clear("scaleBar", "test-refusal")
                        prepare = v.rasterCacheBudget.Prepare
                        with patch.object(v.rasterCacheBudget, "Prepare", side_effect = (lambda *args, **kwargs: False) if fallback else prepare):
                            with DecorationPainter(actual) as painter:
                                painter.translate(9.25, 13.75)
                                painter.scale(factor, factor)
                                painter.setClipRect(plot)
                                painter.setFont(v.font())
                                overlay.DrawScaleBarDecoration(painter, plot, bounds)
                                assert painter.bitmaps and painter.vectorCalls == 0, (physical, density, style, fallback)
                                if fallback:
                                    assert all(size.width() <= 258 and size.height() <= 258 for size in painter.bitmaps)
                        AssertPixelsClose(actual, reference, ("Scale bar raster pixels differ", physical, density, style, fallback))
                        if not fallback:
                            image = overlay.scaleBarImage
                            with patch("planner_app.viewport.export_bounds.DrawScaleBar", side_effect = AssertionError("Pan rebuilt scale bar artwork")):
                                with QtGui.QPainter(actual) as painter:
                                    painter.setFont(v.font())
                                    painter.translate(31.5, 8.25)
                                    overlay.DrawScaleBarDecoration(painter, plot, bounds)
                            assert overlay.scaleBarImage is image
        overlay.architecturalScale = None
        overlay.scale = 80
        overlay.rasterDensity = 1
        overlay.bounds = (-1000, -1000, 5000, 3750)
        overlay.drawRuler = True
        v.zoom = .08 * 2.25 / v.basePixelsPerMillimeter
        v.panOffset += QtCore.QPointF(100.25, 85.75) - v.WorldToViewport(QtCore.QPointF(-1000, 2750))
        for style in ("Plain", "Frame", "Corner Marks", "Reference Zones", "Marked", "Ruler", "Ruler + Reference Zones"):
            overlay.borderStyle = style
            overlay.borderSize = 56
            for interaction in (False, True):
                overlay.dragEdge = 1 if interaction else None
                overlay.previewGesture = interaction
                for fallback in (False, True):
                    v.rasterCacheBudget.Clear("rulers", "test-refresh")
                    overlay.rulerKey = None
                    image = QtGui.QImage(v.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                    image.fill(QtCore.Qt.GlobalColor.transparent)
                    prepare = v.rasterCacheBudget.Prepare
                    with patch.object(v.rasterCacheBudget, "Prepare", side_effect = (lambda *args, **kwargs: False) if fallback else prepare):
                        with DecorationPainter(image) as painter:
                            overlay.DrawCropRulers(painter, v.DrawingRect())
                            assert painter.bitmaps and painter.vectorCalls == 0, (style, interaction, fallback)
                            if fallback:
                                assert all(size.width() <= 258 and size.height() <= 258 for size in painter.bitmaps)
                    if not fallback:
                        cached = image
                    else:
                        AssertPixelsClose(image, cached, ("Tiled border differs", style, interaction))
            overlay.outputFormat = "svg"
            with DecorationPainter(image) as painter:
                overlay.DrawCropRulers(painter, v.DrawingRect())
                assert not painter.bitmaps and painter.vectorCalls > 0, style
            overlay.outputFormat = "png"
        overlay.dragEdge = None
        overlay.previewGesture = False
        overlay.bounds = (-1000, -1000, 500000, 3750)
        overlay.borderStyle = "Frame"
        overlay.rulerKey = None
        with DecorationPainter(image) as painter:
            overlay.DrawCropRulers(painter, v.DrawingRect())
            assert painter.bitmaps and painter.vectorCalls == 0
            assert all(size.width() <= 258 and size.height() <= 258 for size in painter.bitmaps)
            assert len(painter.bitmaps) < 32, "Oversized border rasterized offscreen pixels"
        overlay.outputFormat = "svg"
        with DecorationPainter(image) as painter:
            overlay.DrawScaleBarDecoration(painter, plot, bounds)
            assert not painter.bitmaps and painter.vectorCalls > 0
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetScaleOption("dpi", 300)
        panel.SetScaleOption("pageOrigin", [0, 0])
        panel.SetOverride("texture", None)
        panel.SetOverride("vignetteEnabled", False)
        panel.SetOverride("scaleBar", dict(enabled = True, style = "Stepped"))
        panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "None"))
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        layout = overlay.PrintLayout()
        overlay.bounds = (0, 0, *layout["paperTile"])
        overlay.printRenderArguments = None
        with DecorationPainter(image) as painter:
            painter.setClipRect(v.DrawingRect())
            overlay.DrawPrintDrag(painter, v.DrawingRect(), [overlay.bounds], layout, ("raster-regression",))
            assert len(painter.bitmaps) >= 2 and painter.vectorCalls == 0, ("Print drag paints vector decorations", len(painter.bitmaps), painter.vectorCalls, overlay.outputFormat, overlay.scaleBar)
        assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
    print("Native raster scale-bar pixels, filtered cache reuse, all raster border styles, interactive/budget fallbacks and SVG vectors passed")


if __name__ == "__main__":
    Main()
