"""Paper-aware title-block dimensions, content proportions and output density."""
import os
from pathlib import Path
import sys
from unittest.mock import patch
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.export_plan import RenderPlan
from planner_app.export_settings import BorderSize
from planner_app.graphics.title_block import TitleBlockLayout, TitleBlockCells, TitleBlockUnitScale, DrawTitleBlockText
from planner_app.models import Wall
from planner_app.print_layout import PrintPageLayout, printPaperSizes


def Main():
    with ExampleWindow() as (main, folder):
        InstallScene(main, [Wall(QtCore.QPointF(1000, 1000), QtCore.QPointF(6000, 1000), 200)])
        data = main.BuildProjectData(includeHistory = False)
        data["settings"].update(showGrid = False, showMeasurements = False)
        anchorWidths = {"A4": 40, "A3": 50, "A0": 60, "ARCH E": 60}
        dimensions = {}
        scale = 300 * 1000 / (25.4 * 100)
        for size in printPaperSizes:
            for orientation in ("Landscape", "Portrait"):
                for position in ("Right", "Bottom"):
                    options = dict(enabled = True, position = position, projectName = "Paper scale", logoMode = "None")
                    for kind in ("png", "svg"):
                        for dpi in (150, 300, 600):
                            settings = dict(pageSize = size, pageOrientation = orientation, architecturalScale = 100, dpi = dpi)
                            layout = PrintPageLayout(settings, 56, options, kind)
                            width, height = (value + 112 for value in layout["drawingPixels"])
                            width, height, block = TitleBlockLayout(width, height, options, scale, 100, kind, 300,
                                                                   fitWidth = position == "Bottom", pageSize = layout["paper"])
                            assert (width, height) == layout["baselinePixels"], (size, orientation, position, kind, dpi)
                            thickness = block[2 if position == "Right" else 3] * 25.4 / 300
                            dimensions[size, position, orientation] = thickness
                            if size in anchorWidths:
                                expected = anchorWidths[size] if position == "Right" else 20.48 * anchorWidths[size] / 40
                                assert abs(thickness - expected) <= 25.4 / 300 + 1e-8, (size, position, thickness)
                            cells = TitleBlockCells(block, options, scale, 100, kind, 300,
                                                    fitWidth = position == "Bottom", pageSize = layout["paper"])
                            box = QtCore.QRectF(*block).adjusted(-.001, -.001, .001, .001)
                            assert all(box.contains(cell) for name, label, value, cell in cells), (size, position)
                            byName = {name: cell for name, label, value, cell in cells}
                            assert abs(byName["sheetNumber"].bottom() - box.bottom()) < .01
                            if position == "Bottom":
                                assert abs(byName["sheetNumber"].right() - box.right()) < .01
                            factor = TitleBlockUnitScale(scale, 100, kind, 300, layout["paper"], position)
                            assert abs(byName["address"].height() / factor) >= 3 * 10
                    assert dimensions[size, position, orientation] > 0
            for position in ("Right", "Bottom"):
                assert dimensions[size, position, "Landscape"] == dimensions[size, position, "Portrait"]
        ordered = sorted(printPaperSizes, key = lambda name: min(printPaperSizes[name]))
        for position in ("Right", "Bottom"):
            values = [dimensions[size, position, "Landscape"] for size in ordered]
            assert all(first <= second for first, second in zip(values, values[1:]))
            assert values[-1] <= (60 if position == "Right" else 30.72) + 25.4 / 300

        # Unknown paper retains the free-crop design dimensions.
        for position, expected in (("Right", 51.2), ("Bottom", 20.48)):
            block = TitleBlockLayout(5000, 4000, dict(enabled = True, position = position))[2]
            assert abs(block[2 if position == "Right" else 3] * 25.4 / 300 - expected) < 25.4 / 300

        # Exercise actual per-page PNG and outlined SVG output, including the
        # bitmap title-block painter's density transform and the larger papers.
        for size in ("A4", "A3", "A0"):
            for position in ("Right", "Bottom"):
                options = dict(enabled = True, position = position, projectName = "Paper scale", logoMode = "None")
                layout = PrintPageLayout(dict(pageSize = size, dpi = 72), BorderSize("Ruler + Reference Zones", 56), options)
                expectedBody = (anchorWidths[size] / 16 if position == "Right" else 3.2 * anchorWidths[size] / 40)
                for kind in ("png", "svg"):
                    fontSizes = []

                    def RecordText(painter, position, text):
                        if text == "Paper scale":
                            fontSizes.append(painter.font().pixelSize() * painter.worldTransform().m11())
                        DrawTitleBlockText(painter, position, text)

                    with patch("planner_app.graphics.title_block.DrawTitleBlockText", side_effect = RecordText):
                        result = RenderPlan(folder / "paper.plan", scale, (0, 0, *layout["tile"]), projectData = data,
                            applyTheme = False, outputFormat = kind, architecturalScale = 100, dpi = 72,
                            border = "Ruler + Reference Zones", borderSize = 56, titleBlock = options, pageSize = layout["paper"])
                    if kind == "png":
                        assert (result.width(), result.height()) == layout["pixels"]
                        millimetersPerUnit = 25.4 / 72
                    else:
                        root = ElementTree.fromstring(result)
                        assert b"<text" not in result
                        millimetersPerUnit = float(root.get("width")[:-2]) / float(root.get("viewBox").split()[2])
                    assert len(fontSizes) == 1 and abs(fontSizes[0] * millimetersPerUnit - expectedBody) < .05, (size, position, kind, fontSizes)
    print("PASS: all paper sizes/orientations/densities fit, 40/50/60 mm anchors, proportional fields, unchanged free crop and PNG/SVG output")


if __name__ == "__main__":
    Main()
