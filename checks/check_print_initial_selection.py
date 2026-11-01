"""An unused Print mode starts with one sheet centred on automatic model bounds."""
import copy
import json
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from planner_app.models import Wall
from planner_app.print_layout import PrintPaperGeometry, SelectedPrintPages
from planner_app.project_codec import DecodeProject
from fixtures.parity_examples import ExampleWindow, InstallScene


def Main():
    with ExampleWindow() as (main, folder):
        panel, view = main.exportPanel, main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(12000, 8000), QtCore.QPointF(18000, 8000), 200)])
        template = main.BuildProjectData(includeHistory = False)
        overlay = view.exportOverlay
        for entry, orientation, kind, scale, dpi, position in (
                ("Digital", "Landscape", "PNG", 100, 300, None),
                ("Architectural", "Portrait", "SVG", 50, 600, "Right"),
                ("Print", "Landscape", "PNG", 200, 96, "Bottom")):
            data = copy.deepcopy(template)
            data["settings"]["exportSettings"] = dict(scaleMode = entry, pageOrientation = orientation,
                fileType = kind, architecturalScale = scale, dpi = dpi,
                titleBlock = dict(enabled = position is not None, position = position or "Right"))
            if entry == "Architectural":
                # The requested Print setup belongs to Print, independently of
                # the active Architectural mode's scale and raster density.
                data["settings"]["exportSettings"]["modeScales"] = {
                    "Print": dict(architecturalScale = scale, dpi = dpi)}
            main.ApplyProject(DecodeProject(data, view.furnishingDefinitions), None)
            view.panOffset = QtCore.QPointF(-10000, 20000)
            view.zoom = .6
            main.sidebarTabs.setCurrentWidget(panel)
            panel.ResetExportHistory()
            if entry != "Print":
                panel.SetScaleOption("scaleMode", "Print")
                assert len(panel.exportUndoHistory) == 1
            else:
                assert not panel.exportUndoHistory, "Opening Export must not add an initialization undo step"
            paper = PrintPaperGeometry(panel.overrides)[0]
            x, y, width, height = overlay.autoBounds
            bounds, origin = overlay.bounds, overlay.pageOrigin
            assert bounds[2:] == paper
            assert abs(bounds[0] + paper[0] / 2 - x - width / 2) < 1e-7
            assert abs(bounds[1] + paper[1] / 2 - y - height / 2) < 1e-7
            assert origin == bounds[:2] and origin != (0, 0)
            assert SelectedPrintPages(bounds, paper, origin) == [bounds]
            assert len(panel.ExportJobs(folder / "initial.png", "png")) == 1
            assert "1 page selected" in panel.printNote.text()
            assert panel.overrides["architecturalScale"] == scale and panel.overrides["dpi"] == dpi
            if entry != "Print":
                panel.UndoExport()
                assert panel.overrides.get("scaleMode") == entry and "pageOrigin" not in panel.overrides
                panel.RedoExport()
                assert overlay.bounds == bounds and overlay.pageOrigin == origin
            # Returning to Export or Print restores the initialized sheet.
            main.sidebarTabs.setCurrentIndex(0)
            main.sidebarTabs.setCurrentWidget(panel)
            assert overlay.bounds == bounds and overlay.pageOrigin == origin
            panel.SetScaleOption("scaleMode", "Digital")
            panel.SetScaleOption("scaleMode", "Print")
            assert overlay.bounds == bounds and overlay.pageOrigin == origin
        # A user-moved page remains where it was after a real JSON round trip.
        panel.MovePrintPages([origin[0] + 1234, origin[1] - 678])
        moved = overlay.bounds, overlay.pageOrigin
        saved = json.loads(json.dumps(main.BuildProjectData(includeHistory = False)))
        main.ApplyProject(DecodeProject(saved, view.furnishingDefinitions), folder / "centred.plan")
        main.sidebarTabs.setCurrentWidget(panel)
        assert (overlay.bounds, overlay.pageOrigin) == moved
        # An explicit crop or any explicit page offset, including zero, takes precedence.
        for options in (dict(pageOrigin = [0, 0]), dict(pageOrigin = [3500, -1800]),
                        dict(bounds = [0, 0, 29700, 21000])):
            data = copy.deepcopy(template)
            data["settings"]["exportSettings"] = dict(scaleMode = "Print", **options)
            main.ApplyProject(DecodeProject(data, view.furnishingDefinitions), None)
            main.sidebarTabs.setCurrentWidget(panel)
            assert overlay.pageOrigin == tuple(options.get("pageOrigin", (0, 0)))
            if "bounds" in options:
                assert overlay.bounds == tuple(options["bounds"])
            assert SelectedPrintPages(overlay.bounds, PrintPaperGeometry(panel.overrides)[0], overlay.pageOrigin)
        # Empty projects use the existing origin-centred automatic fallback.
        main.NewProject()
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        x, y, width, height = overlay.bounds
        assert abs(x + width / 2) < 1e-7 and abs(y + height / 2) < 1e-7
        assert SelectedPrintPages(overlay.bounds, (width, height), overlay.pageOrigin) == [overlay.bounds]
    print("PASS: centred initial Print page, entry paths, orientation, scale/PPI, history and saved crop/offset precedence")


if __name__ == "__main__":
    Main()
