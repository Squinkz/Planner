"""Export dimension layout, sparse overrides and Options ownership agree."""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtWidgets, QtSvg
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from planner_app.models import Door
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan
from planner_app.viewport.rendering import RenderingMixin


def Main():
    with ExampleWindow() as (main, folder):
        v, export = main.viewport, main.exportPanel
        walls = Rectangle(-2000, -2000, 4000, 4000)
        InstallScene(main, walls + [Door(walls[0], .25, .5)])
        v.wallMeasurementMode = "All"
        v.wallMeasurementReference = "Wall faces"
        v.showMeasurements = True
        v.measurementVisibility = {key: key == "walls" for key in v.measurementVisibility}
        main.ShowSettings()
        settings = main.settingsWindow
        settings.hide()
        # Export inherits units without creating an override. Build defaults
        # stay in project units even with a different export override active.
        for projectUnits, exportUnits, suffix, values in (
                ("Inches", "Millimeters", " in", (8, 40, 48)),
                ("Centimeters", "Inches", " cm", (20, 90, 100))):
            settings.SetUnitsMode(projectUnits)
            main.sidebarTabs.setCurrentWidget(export)
            assert v.unitsMode == export.unitsField.currentText() == projectUnits
            assert "unitsMode" not in export.overrides
            export.unitsField.setCurrentText(exportUnits)
            overrides = copy.deepcopy(export.overrides)
            settings.RefreshSizeUnits()
            settings.RefreshStepSizing()
            assert all(field.suffix() == suffix for field in settings.sizeFields.values())
            assert all(field.suffix() == suffix for field in settings.stepSizingFields.values())
            assert all(field.suffix() == suffix for field in settings.railingSizingFields.values())
            for key, value in zip((0, "Door", "Stair"), values):
                settings.sizeFields[key].setValue(value)
                assert settings.sizeFields[key].value() == value
                assert settings.sizeFields[key].suffix() == suffix
                expected = round(value * (25.4 if projectUnits == "Inches" else 10), 6)
                if projectUnits == "Inches":
                    assert v.imperialDefaultSizes[str(key)] == expected
                else:
                    actual = (v.wallPresetWidths[key] if isinstance(key, int) else
                              v.miscDefaultSizes[key] if key == "Stair" else v.openingDefaultSizes[key])
                    assert actual * 10 == expected
            assert export.overrides == overrides and v.unitsMode == exportUnits
            settings.buildResetButtons["Door"].click()
            assert settings.sizeFields["Door"].value() == (36 if projectUnits == "Inches" else 90)
            assert settings.sizeFields["Door"].suffix() == suffix
            settings.sizeFields["Door"].setValue(values[1])
            assert export.overrides == overrides and v.unitsMode == exportUnits
            main.sidebarTabs.setCurrentIndex(0)
            assert v.unitsMode == projectUnits and v.DefaultPlacementSize("Door") == values[1] * (25.4 if projectUnits == "Inches" else 10)
            export.ResetOverride("unitsMode")
        settings.SetUnitsMode("Millimeters")
        main.sidebarTabs.setCurrentWidget(export)
        export.sectionButtons["Measurements"].setChecked(True)
        QtWidgets.QApplication.processEvents()
        tree = export.measurementVisibilityTree
        root = export.measurementVisibilityItems["all"]
        assert root.text(0) == "Draw dimensions" and root.isExpanded()
        assert [root.child(index).text(0) for index in range(root.childCount())] == ["Walls", "Stairs", "Counters", "Railings"]
        assert tree.indentation() == 24 and tree.selectionMode() == QtWidgets.QAbstractItemView.SelectionMode.NoSelection
        assert tree.height() == 160
        root.setExpanded(False)
        assert tree.height() == 32
        root.setExpanded(True)
        assert tree.height() == 160
        export.wallMeasurementModeField.setCurrentText("Exterior stacked")
        export.wallReferenceField.setCurrentText("Centerline")
        v.Undo()
        assert v.wallMeasurementReference == export.wallReferenceField.currentText() == "Wall faces"
        v.Redo()
        assert v.wallMeasurementReference == export.wallReferenceField.currentText() == "Centerline"
        export.unitsField.setCurrentText("Centimeters")
        export.measurementVisibilityItems["stairs"].setCheckState(0, QtCore.Qt.CheckState.Checked)
        assert export.wallReferenceField.isVisible()
        contents = export.sectionContents["Measurements"]
        headings = {label.text(): label for label in contents.findChildren(QtWidgets.QLabel)
                    if label.text() in ("Measure", "Walls")}
        assert set(headings) == {"Measure", "Walls"}
        ordered = [export.unitsField, export.precisionField, headings["Measure"], tree, headings["Walls"],
                   export.wallMeasurementModeField, export.wallReferenceField]
        QtWidgets.QApplication.processEvents()
        assert all(first.mapTo(contents, first.rect().bottomLeft()).y() < second.mapTo(contents, QtCore.QPoint()).y()
                   for first, second in zip(ordered, ordered[1:]))
        assert [export.measurementSplitTabs.tabText(index) for index in range(export.measurementSplitTabs.count())] == ["Doors", "Windows", "Stairs", "Counters"]
        assert not export.measurementSplitWidget.isVisible()
        contents.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/export-dimension-settings.png"))
        assert export.projectView["wallMeasurementMode"] == settings.wallMeasurementModeField.currentText() == "All"
        assert export.projectView["wallMeasurementReference"] == settings.wallReferenceField.currentText() == "Wall faces"
        assert not export.projectView["measurementVisibility"]["stairs"]
        overrides = copy.deepcopy(export.overrides)
        settings.SetWallMeasurementMode("Exterior")
        settings.SetWallReference("Wall faces")
        settings.SetMeasurementPrecision("High")
        settings.SetUnitsMode("Meters")
        settings.SetMeasurementMode("doors", 0)
        settings.showGridField.setChecked(False)
        assert export.overrides == overrides, (export.overrides, overrides)
        assert not export.projectView["showGrid"] and "showGrid" not in export.overrides
        export.SetOverride("showGrid", True)
        settings.showGridField.setChecked(True)
        settings.showGridField.setChecked(False)
        assert v.showGrid and not export.projectView["showGrid"] and not settings.showGridField.isChecked()
        assert all(not slider.isEnabled() for slider in settings.sliders.values())
        export.ResetOverride("showGrid")
        assert not v.showGrid and export.overrides == overrides
        assert export.projectView["measurementSettings"]["doors"] == 0
        assert v.wallMeasurementMode == export.wallMeasurementModeField.currentText() == "Exterior stacked"
        assert v.wallMeasurementReference == export.wallReferenceField.currentText() == "Centerline"
        assert v.unitsMode == "Centimeters" and settings.unitsField.currentText() == "Meters"
        assert v.measurementPrecision == "High"
        assert settings.wallMeasurementModeField.currentText() == "Exterior"
        # Non-overridden categories inherit, while explicitly overridden ones
        # keep their export value when Options changes the project choice.
        settings.SetMeasurementVisibility("counters", True)
        assert v.measurementVisibility["counters"]
        settings.SetMeasurementVisibility("stairs", False)
        assert v.measurementVisibility["stairs"] and not export.projectView["measurementVisibility"]["stairs"]
        settings.SetMeasurementVisibility("walls", False)
        assert not export.wallMeasurementModeField.isEnabled() and not export.wallReferenceField.isEnabled()
        settings.SetMeasurementVisibility("walls", True)
        assert export.wallMeasurementModeField.isEnabled() and export.wallReferenceField.isEnabled()
        # Clearing a single override restores its project value immediately.
        export.ResetOverride("wallMeasurementMode")
        assert v.wallMeasurementMode == "Exterior" and not export.wallReferenceField.isVisible()
        export.wallMeasurementModeField.setCurrentText("Exterior stacked")
        export.ResetOverride("wallMeasurementReference")
        assert v.wallMeasurementReference == "Wall faces"
        export.wallReferenceField.setCurrentText("Centerline")
        path = folder / "export-dimensions.plan"
        assert main.SaveProject(path)
        data = main.BuildProjectData()
        decoded = DecodeProject(data, v.furnishingDefinitions)[5]
        assert decoded["wallMeasurementMode"] == "Exterior"
        assert decoded["wallMeasurementReference"] == "Wall faces"
        assert decoded["measurementSettings"]["doors"] == 0
        assert decoded["exportSettings"]["wallMeasurementMode"] == "Exterior stacked"
        assert decoded["exportSettings"]["wallMeasurementReference"] == "Centerline"
        assert main.OpenProject(path)
        main.sidebarTabs.setCurrentWidget(export)
        assert v.wallMeasurementMode == "Exterior stacked" and v.wallMeasurementReference == "Centerline"
        observed = []
        draw = RenderingMixin.DrawSceneMeasurements

        def DrawSceneMeasurements(viewport, *args, **kwargs):
            observed.append((viewport.wallMeasurementMode, viewport.wallMeasurementReference))
            return draw(viewport, *args, **kwargs)

        with patch.object(RenderingMixin, "DrawSceneMeasurements", DrawSceneMeasurements):
            for format in ("png", "svg"):
                output = RenderPlan(path, 100, bounds = [-3000, -3000, 6000, 6000], projectData = data,
                                    outputFormat = format, applyTheme = False, useExportSettings = True)
                assert output if format == "png" else QtSvg.QSvgRenderer(output).isValid()
        assert observed and all(value == ("Exterior stacked", "Centerline") for value in observed), observed
        main.sidebarTabs.setCurrentIndex(0)
        assert v.wallMeasurementMode == "Exterior" and v.wallMeasurementReference == "Wall faces"
        assert v.unitsMode == "Meters" and not v.measurementVisibility["stairs"]
        assert not v.showGrid and v.measurementSettings["doors"] == 0
        for key, value in (("wallMeasurementMode", "Invalid"), ("wallMeasurementReference", "Invalid")):
            invalid = copy.deepcopy(data)
            invalid["settings"]["exportSettings"][key] = value
            try:
                DecodeProject(invalid, v.furnishingDefinitions)
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid export dimension setting accepted")
    print("PASS: export dimension tree, wall controls, Options ownership, inheritance, save/reopen and PNG/SVG")


if __name__ == "__main__":
    Main()
