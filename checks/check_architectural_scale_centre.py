"""Architectural scale edits retain the crop footprint and its screen centre."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow


def Main():
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Architectural")
        for kind in ("PNG", "SVG"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
            for position in (None, "Right", "Bottom"):
                panel.SetScaleOption("architecturalScale", 100)
                panel.SetScaleOption("dpi", 600)
                panel.SetOverride("titleBlock", dict(enabled = position is not None, position = position or "Right"))
                v.exportOverlay.bounds = (-4500, 2700, 16000, 12000)
                panel.SetBounds(v.exportOverlay.bounds)
                panel.ResetExportHistory()
                x, y, width, height = v.exportOverlay.bounds
                centre = QtCore.QPointF(x + width / 2, y + height / 2)
                corners = (v.WorldToViewport(QtCore.QPointF(x, y)), v.WorldToViewport(QtCore.QPointF(x + width, y + height)))
                resolution = panel.resolutionLabel.text()
                for scale in (50, 200, 100):
                    previous = (dict(panel.overrides), v.exportOverlay.bounds, v.zoom, QtCore.QPointF(v.panOffset))
                    panel.SetScaleOption("architecturalScale", scale)
                    x, y, width, height = v.exportOverlay.bounds
                    assert (QtCore.QPointF(x + width / 2, y + height / 2) - centre).manhattanLength() < 1e-7
                    assert (v.WorldToViewport(QtCore.QPointF(x, y)) - corners[0]).manhattanLength() < 1e-7
                    assert (v.WorldToViewport(QtCore.QPointF(x + width, y + height)) - corners[1]).manhattanLength() < 1e-7
                    assert panel.resolutionLabel.text() == resolution
                    result = (dict(panel.overrides), v.exportOverlay.bounds, v.zoom, QtCore.QPointF(v.panOffset))
                    panel.UndoExport()
                    assert panel.overrides == previous[0] and v.exportOverlay.bounds == previous[1]
                    assert abs(v.zoom - previous[2]) < 1e-10 and (v.panOffset - previous[3]).manhattanLength() < 1e-7
                    panel.RedoExport()
                    assert panel.overrides == result[0] and v.exportOverlay.bounds == result[1]
                    assert abs(v.zoom - result[2]) < 1e-10 and (v.panOffset - result[3]).manhattanLength() < 1e-7
    print("Architectural centred scaling, fixed crop footprint, resolution and undo/redo passed")


if __name__ == "__main__":
    Main()
