"""Editor master visibility preserves categories; export remains show/hide all."""
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
        v, export = main.viewport, main.exportPanel
        v.measurementVisibility = {key: key == "walls" for key in v.measurementVisibility}
        v.showMeasurements = True
        original = dict(v.measurementVisibility)
        main.ShowSettings()
        settings = main.settingsWindow
        settings.hide()
        v.setFocus()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_M, QtCore.Qt.KeyboardModifier.ControlModifier)
        assert v.showMeasurements and v.measurementVisibility == original
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_M)
        assert not v.showMeasurements and v.measurementVisibility == original
        assert settings.measurementVisibilityItems["walls"].checkState(0) == QtCore.Qt.CheckState.Checked
        assert settings.measurementVisibilityItems["all"].checkState(0) == QtCore.Qt.CheckState.Unchecked
        decoded = DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)[5]
        assert not decoded["showMeasurements"] and decoded["measurementVisibility"] == original
        main.ShowViewMenu()
        assert main.viewOptions["showMeasurements"].textLabel.text() == "Toggle measurements"
        assert main.viewOptions["showMeasurements"].shortcutLabel.text() == "M"
        assert main.viewOptions["showMeasurements"].iconLabel.pixmap().isNull()
        assert not main.viewOptions["walls"].iconLabel.pixmap().isNull()
        main.viewMenu.hide()
        main.viewOptions["showMeasurements"].click()
        assert v.showMeasurements and v.measurementVisibility == original
        settings.SetMeasurementVisibility("all", False)
        assert not v.showMeasurements and v.measurementVisibility == original
        settings.SetMeasurementVisibility("all", True)
        assert v.showMeasurements and v.measurementVisibility == original
        # Editing another preference while hidden does not erase the wall choice.
        settings.SetMeasurementVisibility("all", False)
        settings.SetMeasurementVisibility("stairs", True)
        assert v.showMeasurements and v.measurementVisibility["walls"] and v.measurementVisibility["stairs"]
        settings.SetMeasurementVisibility("stairs", False)
        settings.SetMeasurementVisibility("all", False)
        main.sidebarTabs.setCurrentWidget(export)
        assert not v.showMeasurements and export.projectView["measurementVisibility"] == original
        main.SetViewOption("showMeasurements")
        assert v.showMeasurements and all(v.measurementVisibility.values())
        main.ShowViewMenu()
        assert main.viewOptions["showMeasurements"].textLabel.text() == "Show all measurements"
        main.viewMenu.hide()
        export.measurementVisibilityItems["all"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        assert not v.showMeasurements and not any(v.measurementVisibility.values())
        export.measurementVisibilityItems["all"].setCheckState(0, QtCore.Qt.CheckState.Checked)
        assert v.showMeasurements and all(v.measurementVisibility.values())
        main.sidebarTabs.setCurrentIndex(0)
        assert not v.showMeasurements and v.measurementVisibility == original
        main.SetViewOption("showMeasurements")
        assert v.showMeasurements and v.measurementVisibility == original
    print("Editor measurement master preserves categories, settings/menu agreement, persistence and export show/hide-all passed")


if __name__ == "__main__":
    Main()
