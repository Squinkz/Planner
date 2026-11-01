"""Architectural PPI changes pixel density, preserving physical layout and ink."""
import os
from pathlib import Path
import sys
from unittest.mock import patch
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from planner_app.models import Wall, Furnishing, Label
from planner_app.viewport.widget import DrawingViewport
from fixtures.parity_examples import ExampleWindow, InstallScene


def Main():
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(1000, 3000), QtCore.QPointF(9000, 3000), 200),
                            Furnishing(v.furnishingDefinitions["desk"], QtCore.QPointF(5000, 6000)),
                            Furnishing(v.furnishingDefinitions["washer"], QtCore.QPointF(8000, 6000)),
                            Label(QtCore.QPointF(4000, 8000), "Physical size")])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Architectural")
        panel.SetScaleOption("architecturalScale", 100)
        panel.SetOverride("canvasColor", "#ffffff")
        panel.SetOverride("linesColor", "#000000")
        panel.SetOverride("wallStyle", "Outline")
        grid = DrawingViewport.DrawGridBackground
        for position in (None, "Right", "Bottom"):
            panel.SetScaleOption("dpi", 300)
            panel.SetOverride("titleBlock", dict(enabled = position is not None, position = position or "Right",
                                               projectName = "Physical scale", comments = "Notes"))
            panel.SetBorder("Ruler + Reference Zones")
            v.exportOverlay.bounds = (-1234, -678, 12000, 11000)
            panel.SetBounds(v.exportOverlay.bounds)
            baseline = panel.Render("png")
            bounds, origin = v.exportOverlay.bounds, v.gridOrigin
            camera = (v.zoom, QtCore.QPointF(v.panOffset))
            baselineSvg = ElementTree.fromstring(panel.Render("svg"))
            for ppi in (96, 150, 300, 600):
                panel.SetScaleOption("dpi", ppi)
                scales = []
                def RecordGrid(source, painter, rect, origin, scale, **kwargs):
                    scales.append(scale)
                    return grid(source, painter, rect, origin, scale, **kwargs)
                with patch.object(DrawingViewport, "DrawGridBackground", RecordGrid):
                    image = panel.Render("png")
                assert image.width() == round(baseline.width() * ppi / 300)
                assert image.height() == round(baseline.height() * ppi / 300)
                assert abs(image.dotsPerMeterX() * .0254 - ppi) < .02
                assert panel.resolutionLabel.text() == f"Resolution: {image.width()} × {image.height()} pixels"
                assert scales and all(abs(value - panel.PreviewScalePerMeter() / 1000) < 1e-9 for value in scales)
                assert v.exportOverlay.bounds == bounds and v.gridOrigin == origin
                assert v.zoom == camera[0] and v.panOffset == camera[1]
                assert v.exportOverlay.scale == panel.PreviewScalePerMeter()
                svg = ElementTree.fromstring(panel.Render("svg"))
                assert svg.attrib == baselineSvg.attrib
                assert not svg.findall(".//{http://www.w3.org/2000/svg}text")
                v.grab()
                assert not v.exportOverlay.previewError, v.exportOverlay.previewError
                assert abs(v.exportOverlay.snapshotSampling - ppi / 300) < 1e-9
                # Capture the same world region at each density without changing
                # source grid steps or SVG furniture stroke widths.
                if position is None:
                    preview = v.exportOverlay.CaptureRaster(QtCore.QRectF(0, 0, 10000, 9000), ppi / 300, "detail")
                    assert preview.width() == int(1182 * ppi / 300)
        panel.SetOverride("titleBlock", dict(enabled = False))
        panel.SetBorder("None")
        panel.SetOverride("showGrid", False)
        panel.SetOverride("measurementVisibility", dict.fromkeys(v.measurementVisibility, False))
        panel.SetOverride("lineworkSettings", dict(baseWidth = 4))
        v.exportOverlay.bounds = (0, 0, 10000, 9000)
        panel.SetBounds(v.exportOverlay.bounds)
        panel.SetScaleOption("dpi", 300)
        baseline = panel.Render("png")
        strokeWidths, furnishingInk = [], [[] for obj in v.furnishings]
        scale = panel.PreviewScalePerMeter() / 1000
        for ppi in (150, 300, 600):
            panel.SetScaleOption("dpi", ppi)
            image = panel.Render("png")
            ratioX, ratioY = image.width() / baseline.width(), image.height() / baseline.height()
            x = round(5000 * scale * ratioX)
            centre = (baseline.height() - 3100 * scale) * ratioY
            radius = max(3, round(6 * ratioY))
            ink = sum(1 - image.pixelColor(x, y).redF() for y in range(round(centre) - radius, round(centre) + radius + 1))
            strokeWidths.append(ink * 25.4 / ppi)
            for obj, amounts in zip(v.furnishings, furnishingInk):
                rect = v.ObjectFootprint(obj)[0].adjusted(-100, -100, 100, 100)
                left, right = round(rect.left() * scale * ratioX), round(rect.right() * scale * ratioX)
                top = round((baseline.height() - rect.bottom() * scale) * ratioY)
                bottom = round((baseline.height() - rect.top() * scale) * ratioY)
                ink = sum(1 - image.pixelColor(x, y).redF() for y in range(top, bottom) for x in range(left, right))
                amounts.append(ink / (ratioX * ratioY))
        assert min(strokeWidths) > .1 and max(strokeWidths) / min(strokeWidths) < 1.08, strokeWidths
        assert all(min(amounts) > 0 and max(amounts) / min(amounts) < 1.12 for amounts in furnishingInk), furnishingInk
    print("Architectural layout, grid, preview density, physical strokes and SVG geometry verified at 96/150/300/600 PPI")


if __name__ == "__main__":
    Main()
