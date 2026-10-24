"""Nominal imperial autosizing, exact overrides, metric restoration and persistence."""
import copy
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Stair, Railing
from planner_app.project_codec import DecodeProject
from planner_app.project_recovery import RecoverProject
from planner_app.export_plan import RenderPlan
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.theme import ApplyApplicationTheme


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.show()
    app.processEvents()
    main.ShowSettings()
    panel, v, point = main.settingsWindow, main.viewport, QtCore.QPointF
    metricSteps, metricRailings = dict(v.stairStepSizes), dict(v.railingSpacings)
    stair = Stair(point(), point(3000, 0))
    railing = Railing(point(0, 3000), point(3000, 3000))
    v.walls = [stair, railing]
    geometry = [(QtCore.QPointF(obj.firstVertex), QtCore.QPointF(obj.secondVertex), obj.width) for obj in v.walls]
    for mode in ("Inches", "Feet and Inches", "Millimeters", "Inches"):
        panel.SetUnitsMode(mode)
        steps, rails = v.AutoSizingLimits("stairs"), v.AutoSizingLimits("railings")
        imperial = mode != "Millimeters"
        assert math.isclose(steps["minimum"], 254 if imperial else 250)
        assert math.isclose(steps["maximum"], 304.8 if imperial else 300)
        assert math.isclose(rails["minimum"], 914.4 if imperial else 900)
        assert math.isclose(rails["target"], 1219.2 if imperial else 1200)
        assert math.isclose(rails["maximum"], 1524 if imperial else 1500)
        assert stair.stepSizeBounds == (steps["minimum"], steps["maximum"])
        assert railing.spacingBounds == tuple(rails[key] for key in ("minimum", "maximum", "target"))
        assert [(obj.firstVertex, obj.secondVertex, obj.width) for obj in v.walls] == geometry
        assert all(not button.isEnabled() for button in panel.stepSizingResetButtons.values())
        assert all(not button.isEnabled() for button in panel.railingSizingResetButtons.values())
    assert panel.stepSizingFields["minimum"].value() == 10
    assert panel.stepSizingFields["maximum"].value() == 12
    assert panel.railingSizingFields["minimum"].value() == 36
    assert panel.railingSizingFields["target"].value() == 48
    assert panel.railingSizingFields["maximum"].value() == 60
    assert panel.stepSizingFields["minimum"].singleStep() == 1
    panel.grab().save(str(Path(__file__).resolve().parent.parent / "diagnostics/imperial-auto-sizing.png"))
    panel.stepSizingFields["minimum"].setValue(11.5)
    panel.railingSizingFields["target"].setValue(42.5)
    assert math.isclose(v.AutoSizingLimits("stairs")["minimum"], 292.1)
    assert math.isclose(v.AutoSizingLimits("railings")["target"], 1079.5)
    assert v.stairStepSizes == metricSteps and v.railingSpacings == metricRailings
    exact = copy.deepcopy(v.imperialAutoSizes)
    panel.SetUnitsMode("Millimeters")
    assert panel.stepSizingFields["minimum"].value() == 250
    assert panel.railingSizingFields["target"].value() == 1200
    panel.SetUnitsMode("Feet and Inches")
    assert v.imperialAutoSizes == exact
    panel.SetUnitsMode("Inches")
    assert panel.stepSizingFields["minimum"].value() == 11.5
    assert panel.railingSizingFields["target"].value() == 42.5
    project = main.BuildProjectData(includeHistory = False)
    decoded, repairs = RecoverProject(project, v.furnishingDefinitions, main.defaultProjectData)
    assert not repairs, repairs
    assert decoded[5]["imperialAutoSizes"] == exact
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "Imperial autosize.plan"
        assert main.SaveProject(path)
        assert main.NewProject() and not v.imperialAutoSizes
        assert main.OpenProject(path) and v.imperialAutoSizes == exact
        assert panel.stepSizingFields["minimum"].value() == 11.5
        assert RenderPlan(path, 50, (-1000, -1000, 6000, 6000), projectData = main.BuildProjectData(), applyTheme = False) is not None
        sourceLimits = v.AutoSizingLimits("stairs")
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        assert v.unitsMode == "Millimeters" and v.AutoSizingLimits("stairs") == sourceLimits
        panel.SetStepSizing("minimum", 11.75)
        assert math.isclose(v.AutoSizingLimits("stairs")["minimum"], 11.75 * 25.4)
        main.sidebarTabs.setCurrentIndex(0)
        assert v.unitsMode == "Inches" and v.autoSizingUnitsMode is None
    panel.stepSizingResetButtons["minimum"].click()
    panel.railingSizingResetButtons["target"].click()
    assert panel.stepSizingFields["minimum"].value() == 10
    assert panel.railingSizingFields["target"].value() == 48
    panel.stepSizingFields["minimum"].setValue(13)
    assert panel.stepSizingFields["maximum"].value() == 13
    invalid = copy.deepcopy(project)
    invalid["settings"]["imperialAutoSizes"]["stairs"]["minimum"] = 1000
    try:
        DecodeProject(invalid, v.furnishingDefinitions)
    except ValueError:
        pass
    else:
        raise AssertionError("Inverted imperial limits accepted")
    panel.SetUnitsMode("Millimeters")
    panel.stepSizingFields["minimum"].setValue(260)
    assert "stairs" not in v.imperialAutoSizes
    panel.SetUnitsMode("Inches")
    assert panel.stepSizingFields["minimum"].value() == 10
    expected = copy.deepcopy(v.imperialAutoSizes)
    main.MarkProjectClean()
    main.close()
    restored = MainWindow()
    assert restored.viewport.imperialAutoSizes == expected
    restored.MarkProjectClean()
    restored.close()


if __name__ == "__main__":
    Main()
