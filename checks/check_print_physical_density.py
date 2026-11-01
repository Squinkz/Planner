"""Print density changes output resolution, preserving geometry and physical ink."""
import os
import re
from pathlib import Path
import sys
from unittest.mock import patch
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from planner_app.models import Wall, Furnishing, Label
from planner_app.export_plan import RenderPlan
from planner_app.viewport.widget import DrawingViewport
from fixtures.parity_examples import ExampleWindow, InstallScene


def Main():
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(1000, 3000), QtCore.QPointF(9000, 3000), 200),
                            Furnishing(v.furnishingDefinitions["desk"], QtCore.QPointF(5000, 6000)),
                            Furnishing(v.furnishingDefinitions["washer"], QtCore.QPointF(8000, 6000)),
                            Label(QtCore.QPointF(12000, 8000), "Physical size")])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetScaleOption("dpi", 300)
        panel.SetScaleOption("pageOrigin", [1234, -678])
        panel.SetOverride("canvasColor", "#ffffff")
        panel.SetOverride("linesColor", "#000000")
        panel.SetOverride("wallStyle", "Outline")
        grid = DrawingViewport.DrawGridBackground
        for position in ("Right", "Bottom"):
            panel.SetOverride("titleBlock", dict(enabled = True, position = position, logoMode = "Planner", projectName = "Physical scale"))
            layout = panel.PrintLayout()
            width, height = layout["paperTile"]
            v.exportOverlay.bounds = (1234, -678, width * 2, height)
            panel.SetBounds(v.exportOverlay.bounds)
            reference = panel.ExportJobs(folder / "reference.png", "png")
            origin, bounds = v.exportOverlay.pageOrigin, v.exportOverlay.bounds
            camera = (v.zoom, QtCore.QPointF(v.panOffset))
            referenceSvg = None
            for ppi in (150, 300, 600, 96, 300):
                panel.SetScaleOption("dpi", ppi)
                current = panel.PrintLayout()
                assert current["tile"] == layout["tile"] and current["paperTile"] == layout["paperTile"]
                assert current["drawingPixels"] == layout["drawingPixels"]
                assert v.exportOverlay.pageOrigin == origin and v.exportOverlay.bounds == bounds
                assert v.zoom == camera[0] and v.panOffset == camera[1]
                assert v.exportOverlay.scale == panel.PreviewScalePerMeter()
                jobs = panel.ExportJobs(folder / "density.png", "png")
                assert [job["bounds"] for path, job in jobs] == [job["bounds"] for path, job in reference]
                scales = []
                def RecordGrid(source, painter, rect, origin, scale, **kwargs):
                    scales.append(scale)
                    return grid(source, painter, rect, origin, scale, **kwargs)
                with patch.object(DrawingViewport, "DrawGridBackground", RecordGrid):
                    image = RenderPlan(**jobs[0][1])
                assert image.size() == QtCore.QSize(round(297 * ppi / 25.4), round(210 * ppi / 25.4))
                assert abs(image.dotsPerMeterX() * .0254 - ppi) < .02
                assert scales and all(abs(value - panel.PreviewScalePerMeter() / 1000) < 1e-9 for value in scales), "Grid algorithm changed with PPI"
                svg = RenderPlan(**panel.ExportJobs(folder / "density.svg", "svg")[0][1])
                if referenceSvg is None:
                    referenceSvg = svg
                expectedElements = list(ElementTree.fromstring(referenceSvg).iter())
                actualElements = list(ElementTree.fromstring(svg).iter())
                assert len(expectedElements) == len(actualElements)
                for expected, actual in zip(expectedElements, actualElements):
                    assert expected.tag == actual.tag and expected.text == actual.text
                    assert expected.attrib.keys() == actual.attrib.keys()
                    for name, value in expected.attrib.items():
                        if name != "d":
                            assert actual.get(name) == value, (position, ppi, name)
                            continue
                        # Qt's SVG font cache can move individual glyph points
                        # by 1/64 font unit. Layout, transforms and stroke widths
                        # must match exactly; tolerate only this tiny path jitter.
                        tokens = re.findall(r"[A-Za-z]|[+-]?(?:\d*\.\d+|\d+)(?:[eE][+-]?\d+)?", value)
                        current = re.findall(r"[A-Za-z]|[+-]?(?:\d*\.\d+|\d+)(?:[eE][+-]?\d+)?", actual.get(name))
                        assert len(tokens) == len(current)
                        for before, after in zip(tokens, current):
                            assert before == after if before.isalpha() else abs(float(before) - float(after)) <= .032, (position, ppi, before, after)
        # Isolate wall strokes and compare their integrated physical widths.
        panel.SetOverride("titleBlock", dict(enabled = False))
        panel.SetScaleOption("pageOrigin", [0, 0])
        panel.SetOverride("showGrid", False)
        panel.SetOverride("measurementVisibility", dict.fromkeys(v.measurementVisibility, False))
        panel.SetOverride("lineworkSettings", dict(baseWidth = 4))
        panel.SetBorder("None")
        layout = panel.PrintLayout()
        v.exportOverlay.bounds = (0, 0, *layout["paperTile"])
        panel.SetBounds(v.exportOverlay.bounds)
        strokes = []
        furnishingInk = [[] for obj in v.furnishings]
        for ppi in (150, 300, 600):
            panel.SetScaleOption("dpi", ppi)
            image = panel.Render("png")
            ratioX = image.width() / layout["baselinePixels"][0]
            ratioY = image.height() / layout["baselinePixels"][1]
            x = round(5000 * panel.PreviewScalePerMeter() / 1000 * ratioX)
            centre = (layout["drawingPixels"][1] - 3100 * panel.PreviewScalePerMeter() / 1000) * ratioY
            radius = max(3, round(6 * ratioY))
            ink = sum(1 - image.pixelColor(x, y).redF() for y in range(round(centre) - radius, round(centre) + radius + 1))
            strokes.append(ink * 25.4 / ppi)
            scale = panel.PreviewScalePerMeter() / 1000
            for obj, amounts in zip(v.furnishings, furnishingInk):
                furnishingBounds = v.ObjectFootprint(obj)[0].adjusted(-100, -100, 100, 100)
                left = round(furnishingBounds.left() * scale * ratioX)
                right = round(furnishingBounds.right() * scale * ratioX)
                top = round((layout["drawingPixels"][1] - furnishingBounds.bottom() * scale) * ratioY)
                bottom = round((layout["drawingPixels"][1] - furnishingBounds.top() * scale) * ratioY)
                amount = sum(1 - image.pixelColor(x, y).redF() for y in range(top, bottom) for x in range(left, right))
                amounts.append(amount / (ratioX * ratioY))
        assert min(strokes) > .1 and max(strokes) / min(strokes) < 1.08, strokes
        assert all(min(amounts) > 0 and max(amounts) / min(amounts) < 1.12 for amounts in furnishingInk), furnishingInk
    print("Print physical layout, offsets, grid, fonts and strokes verified at 96/150/300/600 PPI")


if __name__ == "__main__":
    Main()
