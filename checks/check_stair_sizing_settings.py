"""Project step limits drive autosizing without changing manual counts."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Stair
from planner_app.project_codec import DecodeProject


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.ShowSettings()
    panel = main.settingsWindow
    v = main.viewport
    assert v.unitsMode == "Millimeters"
    assert panel.stepSizingFields["minimum"].suffix() == " mm"
    point = QtCore.QPointF
    stair = Stair(point(), point(2200, 0))
    manual = Stair(point(0, 4000), point(2200, 4000))
    manual.SetAutosize(False)
    before = v.CaptureState()
    v.walls = [stair, manual]
    v.RecordEdit(before)
    v.SetSelection([(stair, None)])
    main.RefreshProperties()
    assert stair.stepCount == manual.stepCount == 8
    panel.SetStepSizing("maximum", 500)
    panel.stepSizingFields["minimum"].setValue(400)
    assert stair.stepCount == 5 and stair.stepSize == 440
    assert manual.stepCount == 8 and manual.stepSize == 275
    assert main.stepCountLabel.text() == "5"
    panel.stepSizingFields["minimum"].setValue(600)
    assert v.stairStepSizes == {"minimum": 60, "maximum": 60}
    assert panel.stepSizingFields["maximum"].value() == 600
    panel.stepSizingFields["maximum"].setValue(300)
    assert v.stairStepSizes == {"minimum": 30, "maximum": 30}
    panel.stepSizingResetButtons["minimum"].click()
    assert v.stairStepSizes == {"minimum": 25, "maximum": 30}
    assert stair.stepCount == 8 and not panel.stepSizingResetButtons["minimum"].isEnabled()
    panel.SetStepSizing("maximum", 500)
    panel.SetStepSizing("minimum", 400)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "Step Limits.plan"
        assert main.SaveProject(path)
        panel.SetStepSizing("minimum", 420)
        app.processEvents()
        assert main.projectDirty
        panel.SetStepSizing("minimum", 400)
        app.processEvents()
        assert not main.projectDirty
        assert main.NewProject() and v.stairStepSizes == {"minimum": 25, "maximum": 30}
        assert main.OpenProject(path) and v.stairStepSizes == {"minimum": 40, "maximum": 50}
        assert panel.stepSizingFields["minimum"].value() == 400
        assert v.walls[0].stepCount == 5 and v.walls[1].stepCount == 8
        legacy = main.BuildProjectData()
        del legacy["settings"]["stairStepSizes"]
        assert DecodeProject(legacy, v.furnishingDefinitions)[5]["stairStepSizes"] == {"minimum": 25, "maximum": 30}
        legacy["settings"]["stairStepSizes"] = {"minimum": 50, "maximum": 40}
        try:
            DecodeProject(legacy, v.furnishingDefinitions)
        except ValueError:
            pass
        else:
            raise AssertionError("Inverted step-size limits accepted")
    main.close()
    restored = MainWindow()
    assert restored.viewport.stairStepSizes == {"minimum": 40, "maximum": 50}
    assert restored.viewport.walls[0].stepCount == 5
    restored.close()
    print("PASS: autosizing limits, manual counts, range constraints, reset, dirty state, project and session persistence.")


if __name__ == "__main__":
    Main()
