"""Title-block body text stays 3.2 mm, with smaller headings and comments across export modes."""
import copy
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtWidgets
from planner_app.export_plan import RenderPlan
from planner_app.graphics import palette
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.title_block import DrawTitleBlockText, TitleBlockFont
from planner_app.graphics.text import TextPath


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    for name, theme in palette.themeDefinitions.items():
        if theme["type"] != "canvas":
            continue
        palette.SetThemes(canvasTheme = name)
        for field, heading, minimum in (("address", False, 10), ("date", True, 8),
                                        ("projectName", False, 10), ("sheetNumber", False, 10), ("comments", False, 7)):
            font = TitleBlockFont(field, heading)
            assert font.pixelSize() >= minimum, (name, field)
    palette.SetThemes(canvasTheme = "Light Canvas")
    data = json.loads((root / "planner-main" / "startup.plan").read_text(encoding = "utf-8-sig"))
    data.pop("history", None)
    data.pop("activityLog", None)
    data["settings"].update(showGrid = False, showMeasurements = False)
    options = dict(enabled = True, projectName = "H", drawingTitle = "H", address = "H",
                   preparedBy = "H", comments = "H", sheetNumber = "H")
    cases = [("png", dpi, None, 100) for dpi in (None, 150, 300, 600)]
    cases += [("svg", None, None, 100), ("svg", None, 100, 96 * 1000 / (25.4 * 100)),
              ("svg", None, 50, 96 * 1000 / (25.4 * 50))]
    for outputFormat, dpi, architecturalScale, scale in cases:
        fontSizes = []
        inkHeights = []
        def RecordText(painter, position, text):
            font = painter.font()
            fontSizes.append(font.pixelSize() * painter.worldTransform().m22())
            path, advance, height, ascent = TextPath(text, font.toString(), painter.device().logicalDpiY())
            inkHeights.append(painter.worldTransform().map(path).boundingRect().height())
            DrawTitleBlockText(painter, position, text)
        with patch("planner_app.graphics.title_block.DrawTitleBlockText", side_effect = RecordText):
            result = RenderPlan("print.plan", scale, (0, 0, 5000, 3000), outputFormat = outputFormat,
                                projectData = copy.deepcopy(data), applyTheme = False, border = "None",
                                titleBlock = options, dpi = dpi, architecturalScale = architecturalScale)
        if outputFormat == "png":
            actualPpi = result.dotsPerMeterY() * .0254
            assert abs(actualPpi - (300 if dpi is None else dpi)) < .02
            millimetersPerUnit = 25.4 / actualPpi
        else:
            svg = ElementTree.fromstring(result)
            assert svg.get("width").endswith("mm")
            millimetersPerUnit = float(svg.get("width")[:-2]) / float(svg.get("viewBox").split()[2])
            assert not any(element.tag.endswith("}text") for element in svg.iter())
        assert fontSizes and abs(min(fontSizes) * millimetersPerUnit - 2.24) < .001, (outputFormat, dpi, architecturalScale)
        assert any(abs(size * millimetersPerUnit - 2.56) < .001 for size in fontSizes), "Heading size changed"
        assert abs(max(fontSizes) * millimetersPerUnit - 3.2) < .001
        assert 0 < max(inkHeights) * millimetersPerUnit <= 3.2
        print(f"{outputFormat}, PPI {dpi or 300}, scale {architecturalScale}: "
              f"font {max(fontSizes) * millimetersPerUnit:.2f} mm, "
              f"visible ink up to {max(inkHeights) * millimetersPerUnit:.2f} mm")
    print("Title block physical text sizes verified across themes, 150/300/600 PPI and SVG modes")
    # An actual A4 landscape example catches proportions hidden by isolated
    # font checks: 3508 x 2480 pixels at 300 PPI, including border and title block.
    from planner_app.graphics.title_block import TitleBlockLayout
    palette.SetThemes(canvasTheme = "Deep Blueprint Canvas")
    sample = copy.deepcopy(data)
    sample["settings"].update(showGrid = True, showMeasurements = True)
    sample["settings"]["measurementVisibility"]["walls"] = True
    points = ((1000, 1000), (6000, 1000), (6000, 5000), (1000, 5000))
    objects = [dict(type = "Wall", id = index + 1, first = list(point), second = list(points[(index + 1) % 4]),
                    width = 200, material = "Generic", firstMiter = 0, secondMiter = 0)
               for index, point in enumerate(points)]
    objects.append(dict(type = "Label", id = 5, first = [3500, 3000], second = [3500, 3500],
                        width = 1000, text = "ROOM", intensity = 1.0))
    sample["scene"] = dict(objects = objects, groups = [], hidden = [])
    sampleOptions = dict(enabled = True, projectName = "New Project", sheetNumber = "0001")
    outputWidth, outputHeight, block = TitleBlockLayout(1, 1, sampleOptions, 300)
    drawingWidth = 3508 - block[2] - 112
    bounds = (-1000, -1000, drawingWidth * 1000 / 300, (2480 - 112) * 1000 / 300)
    image = RenderPlan("a4-example.plan", 300, bounds, projectData = sample, applyTheme = False,
                       border = "Ruler + Reference Zones", borderSize = 56, titleBlock = sampleOptions)
    assert (image.width(), image.height()) == (3508, 2480)
    diagnostics = root / "diagnostics" / "title-block"
    diagnostics.mkdir(parents = True, exist_ok = True)
    image.save(str(diagnostics / "a4-300ppi.png"))


if __name__ == "__main__":
    Main()
