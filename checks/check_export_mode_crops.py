"""Each export scale mode restores its own crop through history and project saves."""
import copy
import json
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner_app.models import Wall
from planner_app.print_layout import SelectedPrintPages
from planner_app.project_codec import DecodeProject
from fixtures.parity_examples import ExampleWindow, InstallScene


def Main():
    with ExampleWindow() as (main, folder):
        panel, view = main.exportPanel, main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(-2000, 0), QtCore.QPointF(3000, 0), 200)])
        panel.SetScaleOption("scaleMode", "Digital")
        main.sidebarTabs.setCurrentWidget(panel)
        overlay = view.exportOverlay
        automatic = overlay.autoBounds
        regions = {"Digital": (-4200, -1800, 14500, 7300), "Architectural": (-2300, -3300, 12000, 9000)}
        overlay.bounds = regions["Digital"]
        panel.SetBounds(overlay.bounds)
        panel.ResetExportHistory()
        panel.SetScaleOption("scaleMode", "Architectural")
        assert overlay.bounds == automatic, "An unused mode inherited another mode's crop"
        assert len(panel.exportUndoHistory) == 1
        panel.UndoExport()
        assert panel.scaleModeTabs.currentIndex() == 2 and overlay.bounds == regions["Digital"]
        panel.RedoExport()
        assert panel.scaleModeTabs.currentIndex() == 1 and overlay.bounds == automatic
        overlay.bounds = regions["Architectural"]
        panel.SetBounds(overlay.bounds)
        panel.SetScaleOption("scaleMode", "Print")
        assert SelectedPrintPages(overlay.bounds, panel.PrintLayout()["paperTile"], overlay.pageOrigin)
        panel.SetScaleOption("pageOrigin", [1234, -678])
        width, height = panel.PrintLayout()["paperTile"]
        # Preserve complete pages as well as the asymmetric unselected margins.
        overlay.bounds = (1234 - width * .1, -678 - height * .2, width * 2.3, height * 2.3)
        panel.SetBounds(overlay.bounds)
        panel.MovePrintPages([1555, -222])
        regions["Print"] = overlay.bounds
        pages = SelectedPrintPages(overlay.bounds, (width, height), overlay.pageOrigin)
        assert len(pages) == 4
        origin = overlay.pageOrigin
        panel.ResetExportHistory()
        for kind in ("PNG", "SVG"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
            for mode in ("Digital", "Architectural", "Print", "Architectural", "Digital", "Print"):
                before = panel.ExportHistoryState()
                beforeBounds = overlay.bounds
                count = len(panel.exportUndoHistory)
                panel.scaleModeTabs.setCurrentIndex(("Print", "Architectural", "Digital").index(mode))
                assert overlay.bounds == regions[mode], (mode, overlay.bounds, regions[mode])
                assert mode not in panel.overrides.get("cropRegions", {})
                assert len(panel.exportUndoHistory) == count + 1
                after = panel.ExportHistoryState()
                panel.UndoExport()
                assert panel.ExportHistoryState() == before and overlay.bounds == beforeBounds
                panel.RedoExport()
                assert panel.ExportHistoryState() == after and overlay.bounds == regions[mode]
                if mode == "Print":
                    assert overlay.pageOrigin == origin
                    assert SelectedPrintPages(overlay.bounds, (width, height), origin) == pages
                    assert len(panel.ExportJobs(folder / "pages.png", "png")) == 4
                else:
                    assert panel.RenderArguments(kind.lower())["bounds"] == regions[mode]
        # Real crop-handle changes update only the active mode.
        panel.SetScaleOption("scaleMode", "Digital")
        overlay.MoveEdge(1, regions["Digital"][0] + regions["Digital"][2] + 500,
                         modifiers = QtCore.Qt.KeyboardModifier.AltModifier)
        regions["Digital"] = overlay.bounds
        panel.SetScaleOption("scaleMode", "Architectural")
        assert overlay.bounds == regions["Architectural"]
        panel.SetScaleOption("architecturalScale", 50)
        regions["Architectural"] = overlay.bounds
        panel.SetScaleOption("architecturalScale", 100)
        regions["Architectural"] = overlay.bounds
        panel.SetScaleOption("scaleMode", "Print")
        assert overlay.bounds == regions["Print"]
        main.sidebarTabs.setCurrentIndex(0)
        main.sidebarTabs.setCurrentWidget(panel)
        assert overlay.bounds == regions["Print"]
        # JSON serialization and strict project decoding retain all three crops.
        data = json.loads(json.dumps(main.BuildProjectData(includeHistory = False)))
        settings = copy.deepcopy(panel.overrides)
        main.ApplyProject(DecodeProject(data, view.furnishingDefinitions), folder / "crops.plan")
        assert not overlay.active and panel.overrides == settings
        panel.SetScaleOption("scaleMode", "Digital")
        assert panel.overrides["bounds"] == list(regions["Digital"])
        main.sidebarTabs.setCurrentWidget(panel)
        for mode in ("Print", "Architectural", "Digital", "Print"):
            panel.scaleModeTabs.setCurrentIndex(("Print", "Architectural", "Digital").index(mode))
            assert overlay.bounds == regions[mode], ("Reload", mode, overlay.bounds)
        # Old projects have one bounds field. It belongs to their saved mode.
        legacy = copy.deepcopy(data)
        legacy["settings"]["exportSettings"] = dict(scaleMode = "Architectural", bounds = list(regions["Architectural"]))
        main.ApplyProject(DecodeProject(legacy, view.furnishingDefinitions), None)
        main.sidebarTabs.setCurrentWidget(panel)
        assert overlay.bounds == regions["Architectural"]
        panel.SetScaleOption("scaleMode", "Digital")
        assert overlay.bounds == overlay.autoBounds
        panel.SetScaleOption("scaleMode", "Architectural")
        assert overlay.bounds == regions["Architectural"]
        # Resetting a crop to automatic must not restore an older custom crop.
        overlay.bounds = overlay.autoBounds
        panel.SetBounds(overlay.bounds)
        panel.SetScaleOption("scaleMode", "Digital")
        panel.SetScaleOption("scaleMode", "Architectural")
        assert overlay.bounds == overlay.autoBounds
        # A later decoration minimum can enlarge the destination on entry,
        # without changing a parked crop or splitting the switch's history.
        panel.SetScaleOption("scaleMode", "Digital")
        small = (100, 200, 150, 100)
        overlay.bounds = small
        panel.SetBounds(small)
        panel.SetScaleOption("scaleMode", "Architectural")
        panel.SetTitleBlockOption("enabled", True)
        assert panel.overrides["cropRegions"]["Digital"] == list(small)
        previousBounds = overlay.bounds
        before = panel.ExportHistoryState()
        panel.ResetExportHistory()
        tabBar = panel.scaleModeTabs.tabBar()
        QtTest.QTest.mouseClick(tabBar, QtCore.Qt.MouseButton.LeftButton, pos = tabBar.tabRect(2).center())
        QtWidgets.QApplication.processEvents()
        assert len(panel.exportUndoHistory) == 1 and overlay.bounds != small
        minimumBounds = overlay.bounds
        assert minimumBounds == overlay.ConstrainTitleBlockBounds(minimumBounds)
        panel.UndoExport()
        assert panel.ExportHistoryState() == before and overlay.bounds == previousBounds
        panel.RedoExport()
        assert overlay.bounds == minimumBounds
        # New projects discard the previous project's archived crops.
        main.NewProject()
        assert not panel.overrides and not overlay.active
        main.sidebarTabs.setCurrentWidget(panel)
        assert panel.overrides["scaleMode"] == "Print"
        assert len(SelectedPrintPages(overlay.bounds, panel.PrintLayout()["paperTile"], overlay.pageOrigin)) == 1
    print("PASS: independent mode crops, crop/page edits, undo/redo, PNG/SVG, save/reopen, legacy and new projects")


if __name__ == "__main__":
    Main()
