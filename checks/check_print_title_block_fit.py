"""Audit listed papers with default and populated title blocks, including borders."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtWidgets
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.print_layout import PrintPageLayout, printPaperSizes


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    cases = [dict(enabled = True), dict(enabled = True, logoMode = "Planner", projectName = "Riverside Residential Development",
             drawingTitle = "Ground Floor Plan", address = "123 Oak Avenue\nParkview\nJohannesburg",
             preparedBy = "Planner Design Studio", revision = "A2-B", sheetNumber = "A-0001",
             comments = "Verify dimensions on site.\nReport discrepancies before work.\nDo not scale from this drawing.\nAll dimensions in millimetres.")]
    checked = 0
    smallest = None
    for size in printPaperSizes:
        for orientation in ("Landscape", "Portrait"):
            options = dict(pageSize = size, pageOrientation = orientation, architecturalScale = 100, dpi = 300)
            for position in ("Right", "Bottom"):
                for content in cases:
                    for border in (56, 128):
                        for kind in ("png", "svg"):
                            layout = PrintPageLayout(options, border, dict(content, position = position), kind)
                            assert min(layout["drawingPixels"]) > 0, (size, orientation, position)
                            fraction = min(a / b for a, b in zip(layout["drawingPixels"], layout["baselinePixels"]))
                            if smallest is None or fraction < smallest[0]:
                                smallest = (fraction, size, orientation, position, border)
                            checked += 1
    print(f"All {len(printPaperSizes)} papers fit both title-block positions and orientations ({checked} cases). Smallest remaining drawing fraction: {smallest}")


if __name__ == "__main__":
    Main()
