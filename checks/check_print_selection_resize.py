"""Paper and print-scale edits retain selected cells and their visual centre."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from planner_app.print_layout import SelectedPrintPages
from fixtures.parity_examples import ExampleWindow


def Main():
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        for columns, rows in ((1, 1), (3, 2)):
            for position in (None, "Right", "Bottom"):
                panel.SetOverride("titleBlock", dict(enabled = position is not None, position = position or "Right"))
                panel.SetScaleOption("pageSize", "A3")
                panel.SetScaleOption("pageOrientation", "Landscape")
                panel.SetScaleOption("architecturalScale", 100)
                panel.SetScaleOption("pageOrigin", [1200, -750])
                width, height = panel.PrintLayout()["paperTile"]
                left, bottom = 1200 - width * 2, -750 + height
                centre = QtCore.QPointF(left + width * columns / 2, bottom + height * rows / 2)
                # Asymmetric partial-page margins must not influence the centre.
                bounds = (left - width * .6, bottom - height * .1, width * (columns + .8), height * (rows + .7))
                v.exportOverlay.bounds = bounds
                panel.SetBounds(bounds)
                panel.ResetExportHistory()
                screenCentre = v.WorldToViewport(centre)
                for name, value in (("pageSize", "A4"), ("pageOrientation", "Portrait"), ("pageSize", "Legal"),
                                    ("architecturalScale", 50), ("architecturalScale", 200)):
                    previous = (dict(panel.overrides), v.exportOverlay.bounds, v.zoom, QtCore.QPointF(v.panOffset))
                    panel.SetScaleOption(name, value)
                    tile = panel.PrintLayout()["paperTile"]
                    origin = v.exportOverlay.pageOrigin
                    selected = SelectedPrintPages(v.exportOverlay.bounds, tile, origin)
                    assert len(selected) == columns * rows, (name, value, len(selected))
                    x, y, w, h = v.exportOverlay.bounds
                    assert abs(x + w / 2 - centre.x()) < 1e-7
                    assert abs(y + h / 2 - centre.y()) < 1e-7
                    assert abs(w - tile[0] * columns) < 1e-7 and abs(h - tile[1] * rows) < 1e-7
                    assert round((x - origin[0]) / tile[0]) == -2
                    assert round((y - origin[1]) / tile[1]) == 1
                    assert (v.WorldToViewport(centre) - screenCentre).manhattanLength() < 1e-7
                    if name != "architecturalScale":
                        assert v.zoom == previous[2] and v.panOffset == previous[3]
                    else:
                        assert abs(v.zoom * value - previous[2] * previous[0]["architecturalScale"]) < 1e-7
                    result = (dict(panel.overrides), v.exportOverlay.bounds, v.zoom, QtCore.QPointF(v.panOffset))
                    panel.UndoExport()
                    assert panel.overrides == previous[0] and v.exportOverlay.bounds == previous[1]
                    assert abs(v.zoom - previous[2]) < 1e-10 and (v.panOffset - previous[3]).manhattanLength() < 1e-7
                    panel.RedoExport()
                    assert panel.overrides == result[0] and v.exportOverlay.bounds == result[1]
                    assert abs(v.zoom - result[2]) < 1e-10 and (v.panOffset - result[3]).manhattanLength() < 1e-7
                panel.SetScaleOption("dpi", 600)
                assert len(SelectedPrintPages(v.exportOverlay.bounds, panel.PrintLayout()["paperTile"], v.exportOverlay.pageOrigin)) == columns * rows
    print("Print selection counts, centred paper resizing, scale anchoring and undo/redo passed")


if __name__ == "__main__":
    Main()
