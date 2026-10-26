"""Complete export dimension controls inherit, persist and remain editor-isolated."""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from planner_app.models import Door, Window
from planner_app.project_codec import DecodeProject
from planner_app.project_recovery import RecoverProject
from planner_app.export_plan import RenderPlan
from planner_app.viewport.rendering import RenderingMixin


def Main():
    with ExampleWindow() as (main, folder):
        v, export = main.viewport, main.exportPanel
        walls = Rectangle(-2000, -2000, 4000, 4000)
        InstallScene(main, walls + [Door(walls[0], .2, .4), Window(walls[2], .3, .6)])
        v.wallMeasurementMode, v.measurementPrecision = "All", "Low"
        v.measurementSettings.update(doors = 1, windows = 2)
        v.showMeasurements = v.measurementVisibility["walls"] = True
        projectSplits = dict(v.measurementSettings)
        main.sidebarTabs.setCurrentWidget(export)
        export.sectionButtons["Measurements"].setChecked(True)
        assert export.precisionField.currentText() == "Low" and not export.overrides
        assert export.measurementSliders["doors"].value() == 1
        export.precisionField.setCurrentText("High")
        assert v.measurementPrecision == "High" and export.projectView["measurementPrecision"] == "Low"
        export.wallMeasurementModeField.setCurrentText("Exterior")
        assert all(modes == (0, 2) for modes in export.measurementModes.values())
        export.measurementSliders["doors"].setValue(1)
        assert export.overrides["measurementSettings"] == {"doors": 2}
        assert v.measurementSettings["doors"] == 2 and export.projectView["measurementSettings"] == projectSplits
        # First opening of Options must exit Export before constructing controls.
        assert main.settingsWindow is None
        main.ShowSettings()
        settings = main.settingsWindow
        assert main.sidebarTabs.currentIndex() == 0 and export.projectView is None
        assert v.measurementPrecision == "Low" and v.measurementSettings == projectSplits
        assert not v.exportOverlay.active and v.wallMeasurementMode == "All"
        settings.hide()
        # Reopening an existing Options window has exactly the same ownership.
        main.sidebarTabs.setCurrentWidget(export)
        assert v.measurementPrecision == "High" and v.measurementSettings["doors"] == 2
        savedOverrides = copy.deepcopy(export.overrides)
        main.ShowSettings()
        assert main.settingsWindow is settings and main.sidebarTabs.currentIndex() == 0
        assert export.overrides == savedOverrides and v.measurementSettings == projectSplits
        settings.SetMeasurementPrecision("Medium")
        settings.hide()
        main.sidebarTabs.setCurrentWidget(export)
        assert v.measurementPrecision == "High" and export.projectView["measurementPrecision"] == "Medium"
        export.ResetOverride("measurementPrecision")
        assert export.precisionField.currentText() == v.measurementPrecision == "Medium"
        export.precisionField.setCurrentText("High")
        export.wallMeasurementModeField.setCurrentText("All")
        assert export.measurementModes["doors"] == (0, 1, 2)
        assert export.wallMeasurementHeading.iconLabel.pixmap().toImage() == settings.wallMeasurementHeading.iconLabel.pixmap().toImage()
        export.measurementSplitTabs.setCurrentIndex(0)
        QtWidgets.QApplication.processEvents()
        tallHeight = export.measurementSplitTabs.height()
        export.measurementSplitTabs.setCurrentIndex(2)
        QtWidgets.QApplication.processEvents()
        assert tallHeight - export.measurementSplitTabs.height() == 63
        export.measurementSplitTabs.setCurrentIndex(0)
        # Label drags use the shared selector interaction and one export undo.
        export.ResetExportHistory()
        slider = export.measurementSliders["doors"]
        slider.setSliderDown(True)
        slider.setValue(0)
        slider.setValue(1)
        slider.setSliderDown(False)
        assert len(export.exportUndoHistory) == 1 and v.measurementSettings["doors"] == 1
        export.UndoExport()
        assert v.measurementSettings["doors"] == 2
        export.RedoExport()
        assert v.measurementSettings["doors"] == 1
        export.measurementResetButtons["windows"].click()
        assert export.overrides["measurementSettings"]["windows"] == 1
        label = export.measurementLabels["doors"][0]
        position = QtCore.QPointF(label.rect().center())
        wheel = QtGui.QWheelEvent(position, QtCore.QPointF(label.mapToGlobal(position.toPoint())), QtCore.QPoint(),
            QtCore.QPoint(0, 120), QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier,
            QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        QtWidgets.QApplication.sendEvent(label, wheel)
        assert v.measurementSettings["doors"] == 0
        export.measurementVisibilityItems["walls"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        assert not export.measurementSplitTabs.isEnabled() and not export.wallMeasurementModeField.isEnabled()
        export.measurementVisibilityItems["walls"].setCheckState(0, QtCore.Qt.CheckState.Checked)
        export.wallMeasurementModeField.setCurrentText("Exterior stacked")
        assert export.measurementSplitWidget.isHidden() and not export.wallReferenceWidget.isHidden()
        export.wallMeasurementModeField.setCurrentText("Exterior")
        assert not export.measurementSplitWidget.isHidden() and export.wallReferenceWidget.isHidden()
        export.measurementSliders["windows"].setValue(1)
        path = folder / "export-controls.plan"
        assert main.SaveProject(path)
        data = main.BuildProjectData()
        decoded = DecodeProject(data, v.furnishingDefinitions)[5]
        assert decoded["measurementPrecision"] == "Medium" and decoded["measurementSettings"] == projectSplits
        assert decoded["exportSettings"]["measurementPrecision"] == "High"
        assert decoded["exportSettings"]["measurementSettings"] == {"doors": 0, "windows": 2}
        recovered, repairs = RecoverProject(data, v.furnishingDefinitions, main.defaultProjectData)
        assert not repairs and recovered[5]["exportSettings"] == decoded["exportSettings"]
        assert main.OpenProject(path)
        main.sidebarTabs.setCurrentWidget(export)
        assert export.precisionField.currentText() == "High" and v.measurementSettings["windows"] == 2
        observed = []
        draw = RenderingMixin.DrawSceneMeasurements

        def Capture(viewport, *args, **kwargs):
            observed.append((viewport.measurementPrecision, dict(viewport.measurementSettings)))
            return draw(viewport, *args, **kwargs)

        with patch.object(RenderingMixin, "DrawSceneMeasurements", Capture):
            for outputFormat in ("png", "svg"):
                assert RenderPlan(path, 100, [-3000, -3000, 6000, 6000], projectData = data,
                                  outputFormat = outputFormat, applyTheme = False, useExportSettings = True)
        assert observed and all(precision == "High" and splits["doors"] == 0 and splits["windows"] == 2
                                for precision, splits in observed)
        for name, value in (("measurementPrecision", "Invalid"), ("measurementSettings", {"stairs": 1}),
                            ("measurementSettings", {"doors": True}), ("measurementSettings", {"unknown": 0})):
            invalid = copy.deepcopy(data)
            invalid["settings"]["exportSettings"][name] = value
            try:
                DecodeProject(invalid, v.furnishingDefinitions)
            except ValueError:
                pass
            else:
                raise AssertionError((name, value))
    print("PASS: shared export controls, precision/split overrides, inheritance, undo, Options exit, persistence/recovery and file rendering")


if __name__ == "__main__":
    Main()
