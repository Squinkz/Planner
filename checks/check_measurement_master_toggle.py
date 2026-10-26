"""Editor master visibility preserves categories; export remains show/hide all."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
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
        assert "all" not in settings.measurementVisibilityItems
        decoded = DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)[5]
        assert not decoded["showMeasurements"] and decoded["measurementVisibility"] == original
        main.ShowViewMenu()
        assert main.viewOptions["showMeasurements"].textLabel.text() == "Toggle dimensions"
        assert main.viewOptions["showMeasurements"].shortcutLabel.text() == "M"
        assert main.viewOptions["showMeasurements"].iconLabel.pixmap().isNull()
        assert not set(v.measurementVisibility).intersection(main.viewOptions)
        main.viewMenu.hide()
        main.viewOptions["showMeasurements"].click()
        assert v.showMeasurements and v.measurementVisibility == original
        main.SetViewOption("showMeasurements")
        assert not v.showMeasurements and v.measurementVisibility == original
        main.SetViewOption("showMeasurements")
        assert v.showMeasurements and v.measurementVisibility == original
        # The Options master preserves choices, but becomes unavailable when
        # none remain. View/keyboard activation then seeds walls only.
        settings.measurementVisibilityTree.setCurrentItem(settings.drawDimensionsItem)
        QtTest.QTest.keyClick(settings.measurementVisibilityTree, QtCore.Qt.Key.Key_Space)
        assert not v.showMeasurements and v.measurementVisibility == original
        settings.measurementVisibilityTree.setCurrentItem(settings.drawDimensionsItem)
        QtTest.QTest.keyClick(settings.measurementVisibilityTree, QtCore.Qt.Key.Key_Space)
        assert v.showMeasurements and v.measurementVisibility == original
        for activate in (lambda: main.SetViewOption("showMeasurements"),
                         lambda: QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_M)):
            for key in v.measurementVisibility:
                settings.SetMeasurementVisibility(key, False)
            assert not v.showMeasurements and settings.drawDimensionsItem.checkState(0) == QtCore.Qt.CheckState.Unchecked
            assert not settings.drawDimensionsItem.flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable
            assert not settings.wallMeasurementModeField.isEnabled()
            assert not settings.wallMeasurementHeading.isEnabled()
            assert all(not slider.isEnabled() for slider in settings.measurementSliders.values())
            activate()
            assert v.showMeasurements and v.measurementVisibility == original
            assert settings.drawDimensionsItem.checkState(0) == QtCore.Qt.CheckState.Checked and settings.drawDimensionsItem.flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable
        for key in v.measurementVisibility:
            settings.SetMeasurementVisibility(key, False)
        tree = settings.measurementVisibilityTree
        root = settings.drawDimensionsItem
        option = QtWidgets.QStyleOptionViewItem()
        tree.itemDelegate().initStyleOption(option, tree.indexFromItem(root))
        assert not option.state & QtWidgets.QStyle.StateFlag.State_Enabled
        tree.setCurrentItem(root)
        QtTest.QTest.keyClick(tree, QtCore.Qt.Key.Key_Space)
        assert not v.showMeasurements
        assert all(item.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled for item in settings.measurementVisibilityItems.values())
        tree.setCurrentItem(settings.measurementVisibilityItems["walls"])
        QtTest.QTest.keyClick(tree, QtCore.Qt.Key.Key_Space)
        assert v.showMeasurements and v.measurementVisibility == original
        for key in v.measurementVisibility:
            settings.SetMeasurementVisibility(key, False)
        settings.SetMeasurementVisibility("all", True)
        assert v.showMeasurements and v.measurementVisibility == original
        # Editing another preference while hidden does not erase the wall choice.
        main.SetViewOption("showMeasurements")
        settings.SetMeasurementVisibility("stairs", True)
        assert v.showMeasurements and v.measurementVisibility["walls"] and v.measurementVisibility["stairs"]
        settings.SetMeasurementVisibility("stairs", False)
        main.SetViewOption("showMeasurements")
        main.sidebarTabs.setCurrentWidget(export)
        assert not v.showMeasurements and export.projectView["measurementVisibility"] == original
        main.SetViewOption("showMeasurements")
        assert v.showMeasurements and all(v.measurementVisibility.values())
        main.ShowViewMenu()
        assert main.viewOptions["showMeasurements"].textLabel.text() == "Toggle dimensions"
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
