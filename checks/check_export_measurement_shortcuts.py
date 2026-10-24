"""Grid and measurement shortcuts edit export overrides from the first visit."""
import copy
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtTest
from fixtures.parity_examples import ExampleWindow
from planner_app.project_codec import DecodeProject


def Main():
    with ExampleWindow() as (main, folder):
        v, panel = main.viewport, main.exportPanel
        v.showGrid = True
        v.showMeasurements = True
        v.measurementVisibility = {key: key == "walls" for key in v.measurementVisibility}
        original = copy.deepcopy(v.measurementVisibility)
        assert not panel.overrides and panel.projectView is None
        main.sidebarTabs.setCurrentWidget(panel)
        v.setFocus()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_G)
        assert not v.showGrid and panel.overrides["showGrid"] is False
        assert not panel.showGridField.isChecked() and panel.projectView["showGrid"]
        main.ShowViewMenu()
        assert main.viewOptions["showGrid"].iconLabel.pixmap().isNull(), "View menu used the editor grid setting"
        main.viewMenu.hide()
        saved = main.BuildProjectData()
        assert saved["settings"]["showGrid"] and saved["settings"]["exportSettings"]["showGrid"] is False
        v.Undo()
        assert v.showGrid and "showGrid" not in panel.overrides
        v.Redo()
        assert not v.showGrid
        main.viewOptions["showGrid"].click()
        assert v.showGrid and panel.showGridField.isChecked()
        main.ShowViewMenu()
        assert not main.viewOptions["showGrid"].iconLabel.pixmap().isNull()
        main.viewMenu.hide()
        panel.showGridField.setChecked(False)
        assert not v.showGrid and panel.overrides["showGrid"] is False
        v.Undo()
        assert v.showGrid
        v.Undo()
        assert not v.showGrid
        v.Undo()
        assert v.showGrid and "showGrid" not in panel.overrides
        for option in ("showTips", "showFpsCounter"):
            before = getattr(v, option)
            overrides = copy.deepcopy(panel.overrides)
            main.SetViewOption(option)
            assert getattr(v, option) != before and main.appPreferences[option] != before
            assert panel.overrides == overrides and option not in panel.projectView
            main.SetViewOption(option)
            assert getattr(v, option) == before
        v.setFocus()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_M)
        assert not v.showMeasurements and not any(v.measurementVisibility.values())
        assert panel.overrides["measurementVisibility"] == dict.fromkeys(original, False)
        assert panel.projectView["showMeasurements"] and panel.projectView["measurementVisibility"] == original
        assert len(panel.exportUndoHistory) == 1
        saved = main.BuildProjectData()
        assert saved["settings"]["showMeasurements"] and saved["settings"]["measurementVisibility"] == original
        assert DecodeProject(saved, v.furnishingDefinitions)[5]["exportSettings"]["measurementVisibility"] == dict.fromkeys(original, False)
        main.sidebarTabs.setCurrentIndex(0)
        assert v.showMeasurements and v.measurementVisibility == original
        main.sidebarTabs.setCurrentWidget(panel)
        assert not v.showMeasurements
        v.Undo()
        assert v.showMeasurements and v.measurementVisibility == original
        v.Redo()
        assert not v.showMeasurements
        v.setFocus()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_M)
        assert v.showMeasurements and all(v.measurementVisibility.values())
        main.SetViewOption("walls")
        assert not v.measurementVisibility["walls"] and v.showMeasurements
        main.ShowViewMenu()
        main.viewMenu.hide()
        # The export GUI uses the same override values and leaves the editor alone.
        panel.measurementVisibilityItems["all"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        assert not v.showMeasurements and not any(v.measurementVisibility.values())
        main.SetViewOption("walls")
        assert v.measurementVisibility == original and v.showMeasurements
        main.sidebarTabs.setCurrentIndex(0)
        assert v.showMeasurements and v.measurementVisibility == original
        main.SetViewOption("showMeasurements")
        assert not v.showMeasurements and v.measurementVisibility == original
        assert panel.overrides["measurementVisibility"] == original
        v.setFocus()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_G)
        assert not v.showGrid and "showGrid" not in panel.overrides
    print("Export grid/measurement shortcuts: first visit, resolved menu states, saved overrides, editor isolation, GUI agreement and undo/redo passed")


if __name__ == "__main__":
    Main()
