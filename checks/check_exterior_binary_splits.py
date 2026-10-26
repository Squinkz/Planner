"""Exterior split controls and geometry are binary and independent of facing."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from planner_app.models import Door, Window
from planner_app.dimension_policy import AvailableDimensionActions
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan
from planner_app.viewport.rendering import RenderingMixin


def Signature(spans):
    return [(first.x(), first.y(), second.x(), second.y(), tuple(type(owner).__name__ for owner in owners))
            for first, second, owners in spans]


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        walls = Rectangle(-2000, -2000, 4000, 4000)
        door, window = Door(walls[0], .2, .4), Window(walls[2], .3, .6)
        InstallScene(main, walls + [door, window])
        v.showMeasurements = v.measurementVisibility["walls"] = True
        v.measurementSettings.update(doors = 1, windows = 1)
        main.ShowSettings()
        panel = main.settingsWindow
        panel.SetWallMeasurementMode("Exterior")
        for key in ("doors", "windows", "stairs", "counters"):
            slider = panel.measurementSliders[key]
            assert panel.measurementModes[key] == (0, 2) and slider.maximum() == 1
            assert slider.height() == 49
            labels = panel.measurementLabels[key]
            assert [label.text() for label in labels if not label.isHidden()] == ["Split wall dimensions", "Do not split wall dimensions"]
        assert v.measurementSettings["doors"] == v.measurementSettings["windows"] == 1
        v.SetSelection([])
        v.grab()
        original = Signature(v.sceneMeasurements[1])
        assert any(door in owners for first, second, owners in v.sceneMeasurements[1])
        assert any(window in owners for first, second, owners in v.sceneMeasurements[1])
        for facing in (False, True):
            for flipped in (False, True):
                for opening in (door, window):
                    opening.swingsOutwards, opening.measurementFlipped = facing, flipped
                    assert not AvailableDimensionActions(v, opening).canFlip
                v.grab()
                assert Signature(v.sceneMeasurements[1]) == original
        # Binary controls commit 0/2, and reset treats facing-side defaults as Split.
        for key, opening in (("doors", door), ("windows", window)):
            panel.measurementSliders[key].setValue(1)
            assert v.measurementSettings[key] == 2 and panel.measurementResetButtons[key].isEnabled()
            v.grab()
            assert not any(opening in owners for first, second, owners in v.sceneMeasurements[1])
            panel.measurementResetButtons[key].click()
            assert v.measurementSettings[key] == 0 and panel.measurementSliders[key].value() == 0
            assert not panel.measurementResetButtons[key].isEnabled()
        panel.SetWallMeasurementMode("All")
        for key in ("doors", "windows"):
            assert panel.measurementModes[key] == (0, 1, 2) and panel.measurementSliders[key].maximum() == 2
            panel.SetMeasurementMode(key, 1)
        panel.SetWallMeasurementMode("Exterior")
        panel.SetWallMeasurementMode("Exterior stacked")
        panel.SetWallMeasurementMode("All")
        assert v.measurementSettings["doors"] == v.measurementSettings["windows"] == 1
        assert AvailableDimensionActions(v, door).canFlip
        # Saved facing-side preferences remain valid; Exterior resolves them to
        # Split on reopen and in file exports, without rewriting All preferences.
        panel.SetWallMeasurementMode("Exterior")
        data = main.BuildProjectData()
        decoded = DecodeProject(data, v.furnishingDefinitions)
        assert decoded[5]["measurementSettings"]["doors"] == 1
        path = folder / "binary.plan"
        assert main.SaveProject(path) and main.OpenProject(path)
        assert panel.measurementModes["doors"] == (0, 2)
        assert v.measurementSettings["doors"] == 1
        observed = []
        draw = RenderingMixin.DrawSceneMeasurements

        def CheckExport(viewport, *args, **kwargs):
            result = draw(viewport, *args, **kwargs)
            assert viewport.wallMeasurementMode == "Exterior"
            spans = viewport.sceneMeasurements[1]
            assert all(any(opening in owners for first, second, owners in spans) for opening in viewport.windows)
            assert all(not AvailableDimensionActions(viewport, opening).canFlip for opening in viewport.windows)
            observed.append(True)
            return result

        with patch.object(RenderingMixin, "DrawSceneMeasurements", CheckExport):
            for outputFormat in ("png", "svg"):
                assert RenderPlan(path, 100, [-3000, -3000, 6000, 6000], projectData = data,
                                  outputFormat = outputFormat, applyTheme = False)
        assert len(observed) == 2
    print("PASS: binary Exterior selectors, facing/flip invariance, reset, mode switching, saved preferences and PNG/SVG")


if __name__ == "__main__":
    Main()
