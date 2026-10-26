"""Stacked exterior split/overall rows, disabled selectors and complete thumbs."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtSvg
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from check_scene_render_cache import CompareDirect
from planner_app.models import Door, Window
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan
from planner_app.viewport.rendering import RenderingMixin


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        walls = Rectangle(-2000, -2000, 4000, 4000)
        door = Door(walls[0], .25, .5)
        window = Window(walls[2], .25, .5)
        InstallScene(main, walls + [door, window])
        v.showMeasurements = True
        v.measurementVisibility = dict.fromkeys(v.measurementVisibility, False)
        v.measurementVisibility["walls"] = True
        v.measurementSettings.update(doors = 2, windows = 2, stairs = 0, counters = 0)
        original = dict(v.measurementSettings)
        main.ShowSettings()
        panel = main.settingsWindow
        panel.tabs.setCurrentIndex(1)
        field = panel.wallMeasurementModeField
        # The whole 16 px thumb stays inside a 20 px selector at every stop.
        for slider in panel.measurementSliders.values():
            blocker = QtCore.QSignalBlocker(slider)
            previous = slider.value()
            for value in range(slider.minimum(), slider.maximum() + 1):
                slider.setValue(value)
                option = QtWidgets.QStyleOptionSlider()
                slider.initStyleOption(option)
                thumb = slider.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_Slider, option,
                                                     QtWidgets.QStyle.SubControl.SC_SliderHandle, slider)
                assert thumb.left() >= 0 and thumb.right() < slider.width(), (thumb, slider.rect())
                assert thumb.width() >= 16
            slider.setValue(previous)
            del blocker
        field.setCurrentText("Exterior stacked")
        QtWidgets.QApplication.processEvents()
        assert panel.wallReferenceWidget.isVisible() and not panel.measurementSplitWidget.isVisible()
        assert panel.wallReferenceField.currentText() == "Wall faces"
        panel.SetMeasurementVisibility("walls", False)
        assert not panel.wallReferenceField.isEnabled()
        panel.SetMeasurementVisibility("walls", True)
        assert panel.wallReferenceField.isEnabled()
        assert all(not slider.isEnabled() for slider in panel.measurementSliders.values())
        assert all(not button.isEnabled() for button in panel.measurementResetButtons.values())
        assert all(not label.isEnabled() for label in panel.measurementPage.findChildren(QtWidgets.QLabel)
                   if label.property("measurementKey") or label.property("measurementHeadingKey"))
        assert v.measurementSettings == original
        v.grab()
        inner, outer = v.sceneMeasurements[1:]
        assert len(inner) == 8 and len(outer) == 2, (len(inner), len(outer))
        assert any(door in owners for first, second, owners in inner)
        assert any(window in owners for first, second, owners in inner)
        assert all(door not in owners and window not in owners for first, second, owners, tier in outer)
        assert all(abs(QtCore.QLineF(first, second).length() - 4200) < 1e-6 for first, second, owners, tier in outer)
        panel.wallReferenceField.setCurrentText("Centerline")
        v.grab()
        assert len(v.sceneMeasurements[1]) == 8 and len(v.sceneMeasurements[2]) == 2
        assert all(abs(QtCore.QLineF(first, second).length() - 4000) < 1e-6
                   for first, second, owners, tier in v.sceneMeasurements[2])
        assert all(abs(QtCore.QLineF(first, second).length() - 1000) < 1e-6
                   for first, second, owners in v.sceneMeasurements[1] if door in owners or window in owners)
        CompareDirect(v)
        panel.wallReferenceField.setCurrentText("Wall faces")
        v.windows = []
        v.grab()
        assert len(v.sceneMeasurements[1]) == 4 and not v.sceneMeasurements[2]
        v.windows = [door, window]
        v.grab()
        assert len(v.sceneMeasurements[1]) == 8 and len(v.sceneMeasurements[2]) == 2
        CompareDirect(v)
        v.panOffset += QtCore.QPointF(23, -7)
        CompareDirect(v)
        v.SetSelection([(walls[0], None)])
        v.grab()
        assert any(door in owners for first, second, owners in v.sceneMeasurements[1])
        v.SetSelection([])
        v.zoom = .5
        v.panOffset = QtCore.QPointF()
        v.showTips = False
        main.viewport.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/stacked-measurements.png"))
        panel.measurementPage.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/stacked-measurement-settings.png"))
        path = folder / "stacked.plan"
        assert main.SaveProject(path)
        data = main.BuildProjectData()
        assert DecodeProject(data, v.furnishingDefinitions)[5]["wallMeasurementMode"] == "Exterior stacked"
        panel.wallReferenceField.setCurrentText("Centerline")
        assert main.SaveProject(path)
        data = main.BuildProjectData()
        assert DecodeProject(data, v.furnishingDefinitions)[5]["wallMeasurementReference"] == "Centerline"
        legacy = main.BuildProjectData()
        legacy["settings"].pop("wallMeasurementReference")
        assert DecodeProject(legacy, v.furnishingDefinitions)[5]["wallMeasurementReference"] == "Wall faces"
        legacy["settings"]["wallMeasurementReference"] = "Invalid"
        try:
            DecodeProject(legacy, v.furnishingDefinitions)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid wall reference accepted")
        panel.wallReferenceField.setCurrentText("Wall faces")
        field.setCurrentText("All")
        assert not panel.wallReferenceWidget.isVisible() and panel.measurementSplitWidget.isVisible()
        assert all(slider.isEnabled() for slider in panel.measurementSliders.values())
        assert v.measurementSettings == original
        assert main.OpenProject(path)
        assert field.currentText() == "Exterior stacked" and not panel.measurementSliders["doors"].isEnabled()
        assert panel.wallReferenceField.currentText() == v.wallMeasurementReference == "Centerline"
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        panel.wallReferenceField.setCurrentText("Wall faces")
        assert main.exportPanel.projectView["wallMeasurementReference"] == "Wall faces"
        assert main.BuildProjectData()["settings"].get("wallMeasurementReference", "Wall faces") == "Wall faces"
        panel.wallReferenceField.setCurrentText("Centerline")
        main.sidebarTabs.setCurrentIndex(0)
        assert v.wallMeasurementReference == "Centerline"
        observed = []
        draw = RenderingMixin.DrawSceneMeasurements

        def DrawSceneMeasurements(viewport, *args, **kwargs):
            result = draw(viewport, *args, **kwargs)
            observed.append((viewport.wallMeasurementMode, viewport.wallMeasurementReference,
                             len(viewport.sceneMeasurements[1]), len(viewport.sceneMeasurements[2])))
            assert all(abs(QtCore.QLineF(first, second).length() - 4000) < 1e-6
                       for first, second, owners, tier in viewport.sceneMeasurements[2])
            return result

        with patch.object(RenderingMixin, "DrawSceneMeasurements", DrawSceneMeasurements):
            for format in ("png", "svg"):
                output = RenderPlan(path, 100, bounds = [-3000, -3000, 6000, 6000], projectData = data,
                                    outputFormat = format, applyTheme = False, useExportSettings = True)
                assert output if format == "png" else QtSvg.QSvgRenderer(output).isValid()
        assert observed and all(value == ("Exterior stacked", "Centerline", 8, 2) for value in observed), observed
    print("PASS: complete slider thumbs, stacked splits/totals, selection, persistence and PNG/SVG")


if __name__ == "__main__":
    Main()
