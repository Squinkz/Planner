"""Physical modes own scale, density and crops across real tab/focus changes."""
import copy
import json
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall
from planner_app.print_layout import SelectedPrintPages
from planner_app.project_codec import DecodeProject
from planner_app.project_recovery import RecoverProject


def ClickMode(panel, name):
    tab = panel.scaleModeTabs.tabBar()
    index = ("Print", "Architectural", "Digital").index(name)
    QtTest.QTest.mouseClick(tab, QtCore.Qt.MouseButton.LeftButton, pos = tab.tabRect(index).center())
    QtWidgets.QApplication.processEvents()
    assert panel.overrides["scaleMode"] == name


def Main():
    with ExampleWindow() as (main, folder):
        panel, view = main.exportPanel, main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(-2000, 0), QtCore.QPointF(3000, 0), 200)])
        main.sidebarTabs.setCurrentWidget(panel)
        overlay = view.exportOverlay
        panel.SetScaleOption("architecturalScale", 200)
        panel.SetScaleOption("dpi", 96)
        panel.SetScaleOption("pageOverlap", [20000, 0])
        panel.SetScaleOption("pageOrigin", [1200, -500])
        width, height = panel.PrintLayout()["paperTile"]
        overlay.bounds = (1200 - width * .1, -500 - height * .2, width * 2.3, height * 2.3)
        panel.SetBounds(overlay.bounds)
        regions = {"Print": overlay.bounds}
        printOrigin = overlay.pageOrigin
        printOverlapOffset = copy.deepcopy(panel.overrides["pageOverlapOffset"])
        assert len(SelectedPrintPages(overlay.bounds, (width, height), printOrigin)) == 4

        panel.architecturalScaleField.lineEdit().setFocus()
        ClickMode(panel, "Architectural")
        assert panel.overrides["architecturalScale"] == 100 and panel.overrides["dpi"] == 300
        assert panel.architecturalScaleField.currentText() == "1:100"
        assert overlay.bounds == overlay.autoBounds
        panel.SetScaleOption("dpi", 150)
        overlay.bounds = (-4200, 1700, 14000, 10000)
        panel.SetBounds(overlay.bounds)
        # Commit an unfinished edit while moving the shared row to Print.
        editor = panel.architecturalScaleField.lineEdit()
        editor.setFocus()
        editor.selectAll()
        QtTest.QTest.keyClicks(editor, "1:50")
        assert editor.text() == "1:50", editor.text()
        ClickMode(panel, "Print")
        assert panel.overrides["architecturalScale"] == 200 and panel.overrides["dpi"] == 96
        assert overlay.bounds == regions["Print"] and overlay.pageOrigin == printOrigin
        assert panel.overrides["pageOverlap"] == [20000, 0]
        assert panel.overrides["pageOverlapOffset"] == printOverlapOffset
        assert panel.overrides["modeScales"]["Architectural"] == dict(architecturalScale = 50, dpi = 150)
        regions["Architectural"] = tuple(panel.overrides["cropRegions"]["Architectural"])
        assert regions["Architectural"] == (-700, 4200, 7000, 5000)
        ClickMode(panel, "Architectural")
        editor = panel.dpiField.lineEdit()
        editor.setFocus()
        editor.selectAll()
        QtTest.QTest.keyClicks(editor, "300")
        ClickMode(panel, "Print")
        assert panel.overrides["dpi"] == 96 and overlay.bounds == regions["Print"]
        assert panel.overrides["modeScales"]["Architectural"]["dpi"] == 300

        panel.ResetExportHistory()
        before = panel.ExportHistoryState()
        panel.SetScaleOption("architecturalScale", 125)
        regions["Print"] = overlay.bounds
        printOrigin = overlay.pageOrigin
        assert len(SelectedPrintPages(overlay.bounds, panel.PrintLayout()["paperTile"], printOrigin)) == 4
        after = panel.ExportHistoryState()
        panel.UndoExport()
        assert panel.ExportHistoryState() == before
        panel.RedoExport()
        assert panel.ExportHistoryState() == after
        assert panel.overrides["cropRegions"]["Architectural"] == list(regions["Architectural"])
        ClickMode(panel, "Digital")
        overlay.bounds = (-5300, -3700, 18200, 11100)
        panel.SetBounds(overlay.bounds)
        panel.SetScale(275)
        regions["Digital"] = overlay.bounds
        scales = {"Architectural": (50, 300), "Print": (125, 96)}
        for kind in ("PNG", "SVG"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
            for mode in ("Architectural", "Print", "Digital", "Print", "Architectural", "Print"):
                before = panel.ExportHistoryState()
                previous = overlay.bounds
                ClickMode(panel, mode)
                assert overlay.bounds == regions[mode], (mode, overlay.bounds, regions[mode])
                assert panel.overrides["pageOverlap"] == [20000, 0]
                assert panel.overrides["pageOverlapOffset"] == printOverlapOffset
                assert "modeScales" not in panel.ResolvedView()
                if mode in scales:
                    scale, dpi = scales[mode]
                    assert panel.overrides["architecturalScale"] == scale and panel.overrides["dpi"] == dpi
                    assert panel.architecturalScaleField.currentText() == f"1:{scale}"
                    assert panel.dpiField.currentText() == str(dpi)
                    assert panel.RenderArguments(kind.lower())["architecturalScale"] == scale
                    assert mode not in panel.overrides.get("modeScales", {})
                else:
                    assert panel.ScalePerMeter() == 275
                after = panel.ExportHistoryState()
                panel.UndoExport()
                assert panel.ExportHistoryState() == before and overlay.bounds == previous
                panel.RedoExport()
                assert panel.ExportHistoryState() == after and overlay.bounds == regions[mode]
                if mode == "Print":
                    assert overlay.pageOrigin == printOrigin
                    assert len(panel.ExportJobs(folder / "pages.png", "png")) == 4

        data = json.loads(json.dumps(main.BuildProjectData(includeHistory = False)))
        decoded = DecodeProject(data, view.furnishingDefinitions)
        recovered, repairs = RecoverProject(data, view.furnishingDefinitions, main.defaultProjectData)
        assert not repairs and recovered[5]["exportSettings"] == decoded[5]["exportSettings"]
        saved = copy.deepcopy(panel.overrides)
        main.ApplyProject(decoded, folder / "mode-scales.plan")
        assert not overlay.active and panel.overrides == saved
        main.sidebarTabs.setCurrentWidget(panel)
        for mode in ("Architectural", "Digital", "Print"):
            ClickMode(panel, mode)
            assert overlay.bounds == regions[mode]
            if mode in scales:
                assert (panel.overrides["architecturalScale"], panel.overrides["dpi"]) == scales[mode]
        for invalid in ({"Digital": {}}, {"Print": {"unknown": 1}}, {"Print": {"architecturalScale": True}},
                        {"Print": {"architecturalScale": float("nan")}}, {"Architectural": {"dpi": 0}},
                        {"Architectural": {"dpi": True}}, {"Print": []}):
            broken = copy.deepcopy(data)
            broken["settings"]["exportSettings"]["modeScales"] = invalid
            try:
                DecodeProject(broken, view.furnishingDefinitions)
            except ValueError:
                pass
            else:
                raise AssertionError(invalid)
        # A legacy shared value belongs to the saved physical mode. The other
        # mode starts at defaults and subsequent switches remain independent.
        legacy = copy.deepcopy(data)
        legacy["settings"]["exportSettings"].pop("modeScales", None)
        main.ApplyProject(DecodeProject(legacy, view.furnishingDefinitions), None)
        main.sidebarTabs.setCurrentWidget(panel)
        ClickMode(panel, "Architectural")
        assert (panel.overrides["architecturalScale"], panel.overrides["dpi"]) == (100, 300)
        ClickMode(panel, "Print")
        assert (panel.overrides["architecturalScale"], panel.overrides["dpi"]) == scales["Print"]
        main.NewProject()
        assert not panel.overrides
    print("PASS: independent physical scales/PPI/crops, pending edits and real tab clicks, PNG/SVG, page counts, history, persistence and validation")


if __name__ == "__main__":
    Main()
