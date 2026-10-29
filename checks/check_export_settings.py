"""Export preview inheritance, sparse persistence and normal-setting isolation."""
import copy
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.graphics import palette
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.project_codec import DecodeProject
from planner_app.ui.settings import SettingsWindow
from planner_app.ui.color_picker import ColorPickerDialog


def Main():
    with tempfile.TemporaryDirectory(dir = Path(__file__).parent) as folder:
        os.environ["PLANNER_SESSION_PATH"] = str(Path(folder) / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(Path(folder) / "startup.plan")
        app = QtWidgets.QApplication([])
        ApplyApplicationTheme(app)
        main = MainWindow()
        main.SetThemes(canvasTheme = "Dark Canvas")  # This fixture explicitly exercises Dark Canvas export overrides.
        main.show()
        app.processEvents()
        panel = main.exportPanel
        heading = panel.sectionButtons["Measurements"]
        assert heading.text() == "Dimensions" and heading.accessibleName() == "Dimensions section"
        assert heading.toolTip() == "Expand Dimensions"
        heading.setChecked(True)
        assert heading.toolTip() == "Collapse Dimensions"
        heading.setChecked(False)
        assert panel.measurementVisibilityItems["all"].text(0) == "Draw dimensions"
        assert not any(button.isChecked() for button in panel.sectionButtons.values())
        assert [panel.typeField.itemText(index) for index in range(panel.typeField.count())] == ["PNG (raster)", "SVG (vector)", "Optimized PNG (raster)"]
        panel.fileNameField.setText("render.png")
        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value = str(Path(folder))):
            panel.browseButton.click()
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        assert panel.fileNameField.text() == "render" and panel.typeField.currentData() == "SVG"
        assert panel.browseButton.text() == "" and not panel.browseButton.icon().isNull()
        # Keep this inheritance fixture free of explicit export preferences.
        # File-type persistence has its own round-trip coverage.
        panel.overrides.pop("fileType", None)
        original = copy.deepcopy(main.ProjectSettings())
        # Destinations are now project settings. Establish the clean baseline
        # after the fixture has chosen its folder and filename.
        main.MarkProjectClean()
        view = panel.CaptureView()
        assert "exportSettings" not in original
        originalPan = QtCore.QPointF(147, -83)
        main.viewport.panOffset = QtCore.QPointF(originalPan)
        main.sidebarTabs.setCurrentWidget(panel)
        x, y, width, height = main.viewport.exportOverlay.bounds
        cropCenter = main.viewport.WorldToViewport(QtCore.QPointF(x + width / 2, y + height / 2))
        assert (cropCenter - main.viewport.DrawingRect().center()).manhattanLength() < .001
        # Keep Export's camera when the crop still spans the midpoint; recenter
        # only when the entire crop has crossed it in any of the four directions.
        v = main.viewport
        v.zoom = 1.25
        scale = v.basePixelsPerMillimeter * v.zoom
        centeredPan = QtCore.QPointF(-(x + width / 2) * scale, (y + height / 2) * scale)
        offsets = (QtCore.QPointF(width * scale / 4, height * scale / 4),
                   QtCore.QPointF(-width * scale, 0), QtCore.QPointF(width * scale, 0),
                   QtCore.QPointF(0, height * scale), QtCore.QPointF(0, -height * scale))
        for index, offset in enumerate(offsets):
            v.panOffset = centeredPan + offset
            main.sidebarTabs.setCurrentIndex(0)
            assert v.panOffset == originalPan
            main.sidebarTabs.setCurrentWidget(panel)
            assert v.zoom == 1.25
            assert v.panOffset == (centeredPan + offset if index == 0 else centeredPan)
        assert main.BuildProjectData()["view"]["pan"] == [originalPan.x(), originalPan.y()]
        assert panel.borderField.currentText() == "Ruler + Reference Zones"
        assert [panel.borderField.itemText(index) for index in range(panel.borderField.count())] == [
        "None", "Plain", "Frame", "Corner Marks", "Reference Zones", "Marked", "Ruler", "Ruler + Reference Zones"]
        normalColor = palette.themeColors["canvas"]
        with patch.object(ColorPickerDialog, "GetColor", return_value = QtGui.QColor(normalColor)):
            panel.canvasColorButton.click()
        assert "canvasColor" not in panel.overrides
        v.furnishingDefinitions["color-picker-check"] = {
            "key": "null", "name": "Color Picker Check", "width": 10, "length": 10,
            "graphicData": b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="white"/></svg>'}
        main.RefreshFurnishingRenderers()
        def FurnishingBackground():
            image = QtGui.QImage(10, 10, QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtCore.Qt.GlobalColor.transparent)
            painter = QtGui.QPainter(image)
            v.furnishingRenderers["color-picker-check"].render(painter, QtCore.QRectF(0, 0, 10, 10))
            painter.end()
            return image.pixelColor(5, 5).name()
        with patch.object(ColorPickerDialog, "GetColor", return_value = QtGui.QColor("#123456")):
            panel.canvasColorButton.click()
        assert palette.themeColors["canvas"] == "#123456"
        assert FurnishingBackground() == "#123456"
        with patch.object(ColorPickerDialog, "GetColor", return_value = QtGui.QColor(normalColor)):
            panel.canvasColorButton.click()
        assert "canvasColor" not in panel.overrides and palette.themeColors["canvas"] == normalColor
        panel.SetOverride("canvasColor", "#123456")
        colorData = main.BuildProjectData()
        assert DecodeProject(colorData, main.viewport.furnishingDefinitions)[5]["exportSettings"]["canvasColor"] == "#123456"
        main.sidebarTabs.setCurrentIndex(0)
        assert palette.themeColors["canvas"] == normalColor
        assert FurnishingBackground() == QtGui.QColor(normalColor).name()
        main.sidebarTabs.setCurrentWidget(panel)
        assert palette.themeColors["canvas"] == "#123456"
        panel.canvasColorReset.click()
        assert "canvasColor" not in panel.overrides and palette.themeColors["canvas"] == normalColor
        assert FurnishingBackground() == QtGui.QColor(normalColor).name()
        with patch.object(ColorPickerDialog, "GetColor", return_value = QtGui.QColor()):
            panel.canvasColorButton.click()
        assert "canvasColor" not in panel.overrides
        for outputFormat in ("PNG", "SVG"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(outputFormat))
            previousSettings = copy.deepcopy(main.ProjectSettings())
            def PreviewAndCancel():
                dialog = app.activeModalWidget()
                dialog.SetColor(QtGui.QColor("#abcdef"))
                assert palette.themeColors["canvas"] == "#abcdef"
                assert FurnishingBackground() == "#abcdef"
                assert main.ProjectSettings() == previousSettings, "Live preview persisted an unconfirmed color"
                main.viewport.grab()
                dialog.reject()
            QtCore.QTimer.singleShot(0, PreviewAndCancel)
            panel.canvasColorButton.click()
            assert palette.themeColors["canvas"] == normalColor
            assert FurnishingBackground() == QtGui.QColor(normalColor).name()
            assert main.ProjectSettings() == previousSettings
        def PreviewAndAccept():
            dialog = app.activeModalWidget()
            dialog.SetColor(QtGui.QColor("#fedcba"))
            dialog.accept()
        QtCore.QTimer.singleShot(0, PreviewAndAccept)
        panel.canvasColorButton.click()
        assert panel.overrides["canvasColor"] == "#fedcba" and palette.themeColors["canvas"] == "#fedcba"
        panel.canvasColorReset.click()
        del v.furnishingDefinitions["color-picker-check"]
        main.RefreshFurnishingRenderers()
        normalGridColor = palette.themeColors["grid"]
        panel.showGridField.setChecked(True)
        with patch.object(ColorPickerDialog, "GetColor", return_value = QtGui.QColor("#de2345")):
            panel.gridColorButton.click()
        assert palette.themeColors["grid"] == "#de2345"
        assert panel.overrides["gridColor"] == "#de2345"
        assert DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)[5]["exportSettings"]["gridColor"] == "#de2345"
        panel.showGridField.setChecked(False)
        assert not panel.gridColorLabel.isEnabled() and not panel.gridColorButton.isEnabled()
        assert not panel.gridColorReset.isEnabled()
        panel.showGridField.setChecked(True)
        assert panel.gridColorLabel.isEnabled() and panel.gridColorButton.isEnabled()
        assert panel.gridColorReset.isEnabled() and panel.overrides["gridColor"] == "#de2345"
        main.sidebarTabs.setCurrentIndex(0)
        assert palette.themeColors["grid"] == normalGridColor
        main.sidebarTabs.setCurrentWidget(panel)
        assert palette.themeColors["grid"] == "#de2345"
        panel.gridColorReset.click()
        assert "gridColor" not in panel.overrides and palette.themeColors["grid"] == normalGridColor
        assert panel.canvasColorLabel.text() == "Background" and panel.linesColorLabel.text() == "Lines"
        originalOutlines = {role: palette.themeColors[role] for role in ("objectOutline", "wallOutline")}
        previousRenderer = v.furnishingRenderers["desk"]
        panel.PreviewColor("lines", QtGui.QColor("#ab2345"))
        assert all(palette.themeColors[role] == "#ab2345" for role in originalOutlines)
        assert v.furnishingRenderers["desk"] is not previousRenderer
        panel.ApplyView(panel.ResolvedView())
        with patch.object(ColorPickerDialog, "GetColor", return_value = QtGui.QColor("#ab2345")):
            panel.linesColorButton.click()
        assert panel.overrides["linesColor"] == "#ab2345"
        assert all(palette.themeColors[role] == "#ab2345" for role in originalOutlines)
        assert DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)[5]["exportSettings"]["linesColor"] == "#ab2345"
        main.sidebarTabs.setCurrentIndex(0)
        assert all(palette.themeColors[role] == color for role, color in originalOutlines.items())
        main.sidebarTabs.setCurrentWidget(panel)
        assert all(palette.themeColors[role] == "#ab2345" for role in originalOutlines)
        panel.linesColorReset.click()
        assert "linesColor" not in panel.overrides
        assert all(palette.themeColors[role] == color for role, color in originalOutlines.items())
        # Leave no extra overrides behind for the inheritance assertions below.
        panel.overrides.pop("showGrid", None)
        panel.overrides.pop("fileType", None)
        panel.ApplyView(panel.ResolvedView())
        panel.RefreshControls()
        panel.sectionButtons["Canvas"].click()
        panel.sectionButtons["Grid"].click()
        assert panel.CaptureView() == view and main.ProjectSettings() == original
        assert panel.unitsField.currentText() == view["unitsMode"] and "unitsMode" not in panel.overrides
        main.RefreshProjectDirty()
        assert not main.projectDirty
        panel.unitsField.setCurrentText("Centimeters")
        panel.gridSliders["overall"].setValue(725)
        panel.lineworkFields["walls"].setValue(.875)
        panel.showGridField.setChecked(False)
        panel.canvasThemeField.setCurrentText("Light Canvas")
        panel.measurementVisibilityItems["walls"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        panel.visibilityItems["Doors"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        assert main.viewport.gridIntensities["overall"] == .725
        assert main.viewport.lineworkSettings["walls"] == .875
        assert not main.viewport.showGrid and palette.activeCanvasTheme == "Light Canvas"
        assert not main.viewport.measurementVisibility["walls"] and not main.viewport.visibility["Doors"]
        saved = main.BuildProjectData()
        assert {key: value for key, value in saved["settings"].items() if key != "exportSettings"} == original
        assert saved["settings"]["exportSettings"]["viewportSettings"] == {"overall": .725}
        assert saved["settings"]["exportSettings"]["visibility"] == {"Doors": False}
        assert saved["settings"]["exportSettings"]["unitsMode"] == "Centimeters"
        main.RefreshProjectDirty()
        assert main.projectDirty
        overrides = copy.deepcopy(panel.overrides)
        main.sidebarTabs.setCurrentIndex(0)
        assert main.viewport.panOffset == originalPan
        assert panel.CaptureView() == view, {key: (view[key], value) for key, value in panel.CaptureView().items() if value != view[key]}
        main.settingsWindow = SettingsWindow(main)
        main.settingsWindow.SetGridIntensity("major", .432)
        main.settingsWindow.SetLineWeight("furnishings", .625)
        main.SetThemes(canvasTheme = "Dark Canvas")
        panel.overrides["bounds"] = [1234, -5678, 8000, 6000]
        main.sidebarTabs.setCurrentWidget(panel)
        cropCenter = main.viewport.WorldToViewport(QtCore.QPointF(5234, -2678))
        assert (cropCenter - main.viewport.DrawingRect().center()).manhattanLength() < .001
        del panel.overrides["bounds"]
        assert main.viewport.gridIntensities["major"] == .432
        assert main.viewport.gridIntensities["overall"] == .725
        assert main.viewport.lineworkSettings["furnishings"] == .625
        assert palette.activeCanvasTheme == "Light Canvas"
        assert main.viewport.unitsMode == "Centimeters"
        main.settingsWindow.SetUnitsMode("Meters")
        assert main.viewport.unitsMode == "Centimeters"
        assert main.ProjectSettings()["unitsMode"] == "Meters"
        assert main.settingsWindow.unitsField.currentText() == "Meters"
        main.settingsWindow.SetUnitsMode(view["unitsMode"])
        # Normal controls still edit the normal project while Export is active.
        main.settingsWindow.SetGridIntensity("overall", .333)
        main.settingsWindow.SetLineWeight("walls", .5)
        assert main.viewport.gridIntensities["overall"] == .725
        assert main.viewport.lineworkSettings["walls"] == .875
        assert main.ProjectSettings()["viewportSettings"]["overall"] == .333
        assert main.ProjectSettings()["lineworkSettings"]["walls"] == .5
        assert main.settingsWindow.valueFields["overall"].value() == .333
        assert main.settingsWindow.lineworkFields["walls"].value() == .5
        assert panel.overrides == overrides
        # Reset uses the same authored defaults as Appearance and stays export-only.
        assert not panel.gridResetButtons["overall"].isEnabled()
        panel.showGridField.setChecked(True)
        panel.gridResetButtons["overall"].click()
        assert main.viewport.gridIntensities["overall"] == 1
        assert main.ProjectSettings()["viewportSettings"]["overall"] == .333
        panel.gridSliders["overall"].setValue(725)
        panel.showGridField.setChecked(False)
        panel.visibilityItems["World"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        assert not any(main.viewport.visibility.values())
        panel.visibilityItems["Doors"].setCheckState(0, QtCore.Qt.CheckState.Checked)
        assert main.viewport.visibility["Doors"] and main.viewport.visibility["World"]
        assert panel.visibilityItems["Walls"].checkState(0) == QtCore.Qt.CheckState.PartiallyChecked
        # Discard these extra tree edits by loading the saved sparse overrides.
        main.ApplyProject(DecodeProject(saved, main.viewport.furnishingDefinitions), None)
        assert panel.overrides == overrides
        assert main.sidebarTabs.currentWidget() is main.buildScrollArea
        assert main.viewport.gridIntensities["overall"] == view["viewportSettings"]["overall"]
        main.sidebarTabs.setCurrentIndex(0)
        assert panel.CaptureView() == view, {key: (view[key], value) for key, value in panel.CaptureView().items() if value != view[key]}
        # Opening another, older project clears overrides, even from Export.
        main.sidebarTabs.setCurrentWidget(panel)
        legacy = copy.deepcopy(saved)
        legacy["settings"].pop("exportSettings")
        legacy["ui"].pop("exportSections")
        main.ApplyProject(DecodeProject(legacy, main.viewport.furnishingDefinitions), None)
        assert panel.overrides == {} and panel.CaptureView() == view
        assert not any(button.isChecked() for button in panel.sectionButtons.values())
        assert "exportSettings" not in main.ProjectSettings()
        for bad in ({"showGrid": 1}, {"lineworkSettings": {"walls": -1}},
                    {"viewportSettings": {"major": 2}}, {"visibility": {"Doors": "yes"}},
                    {"canvasTheme": 123}, {"unitsMode": "Feet"}, {"unknown": True}):
            invalid = copy.deepcopy(saved)
            invalid["settings"]["exportSettings"] = bad
            try:
                DecodeProject(invalid, main.viewport.furnishingDefinitions)
            except ValueError:
                pass
            else:
                raise AssertionError(f"Accepted invalid export settings: {bad}")
        main.ApplyProject(DecodeProject(saved, main.viewport.furnishingDefinitions), None)
        main.close()
        recovered = MainWindow()
        recovered.show()
        app.processEvents()
        assert recovered.exportPanel.overrides == overrides
        assert recovered.exportPanel.sectionButtons["Canvas"].isChecked()
        assert recovered.exportPanel.sectionButtons["Grid"].isChecked()
        assert not recovered.exportPanel.sectionButtons["Visibility"].isChecked()
        assert recovered.sidebarTabs.currentWidget() is recovered.buildScrollArea
        assert recovered.viewport.gridIntensities["overall"] == view["viewportSettings"]["overall"]
        recovered.sidebarTabs.setCurrentIndex(0)
        assert recovered.exportPanel.CaptureView() == view
        recovered.close()
        print("PASS: inherited preview, sparse overrides, normal setting isolation, project loading, validation and recovery")


if __name__ == "__main__":
    Main()
