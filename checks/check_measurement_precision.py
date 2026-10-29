"""Canvas-only precision rounds physical millimeters consistently across units."""
import copy
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.text import PathTextPainter
from planner import MainWindow, Wall
from planner_app.project_codec import DecodeProject
from planner_app.units import FormatLength, GridUnit, measurementPrecisions, unitModes
from planner_app.export_plan import RenderPlan


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    main.ShowSettings()
    app.processEvents()
    v, panel = main.viewport, main.settingsWindow
    assert v.measurementPrecision == "Medium" and panel.precisionField.currentText() == "Medium"
    assert [panel.precisionField.itemText(index) for index in range(3)] == ["High", "Medium", "Low"]
    wall = Wall(QtCore.QPointF(-617.3, 0), QtCore.QPointF(617.3, 0))
    v.walls, v.windows, v.furnishings, v.labels = [wall], [], [], []
    v.SetSelection([(wall, None)])
    main.RefreshProperties()
    geometry = v.CaptureState()
    drawn = []

    class RecordingPainter(PathTextPainter):
        def drawText(self, *arguments):
            drawn.append(arguments[-1])
            return super().drawText(*arguments)

    for precision, rounded in (("High", 1235), ("Medium", 1235), ("Low", 1240)):
        propertyValues = {name: field.value() for name, field in main.propertyFields.items()}
        panel.precisionField.setCurrentText(precision)
        assert v.measurementPrecision == precision and v.CaptureState() == geometry
        assert {name: field.value() for name, field in main.propertyFields.items()} == propertyValues
        for mode in unitModes[:4]:
            panel.unitsField.setCurrentText(mode)
            drawn.clear()
            with patch("planner_app.viewport.rendering.PathTextPainter", RecordingPainter):
                v.grab()
            expected = FormatLength(rounded, mode, includeUnit = False)
            assert expected in drawn, (precision, mode, drawn)
            assert FormatLength(1234.6, mode, precision = precision, includeUnit = False) == expected
            assert FormatLength(1234.6, mode) == FormatLength(1234.6, mode, precision = None)
        step = measurementPrecisions[precision]
        assert FormatLength(step * 2.5, "Millimeters", precision = precision, includeUnit = False) == str(step * 3)
    assert [FormatLength(1232, "Millimeters", precision = precision, includeUnit = False)
            for precision in measurementPrecisions] == ["1232", "1230", "1240"]
    panel.unitsField.setCurrentText("Adaptive Metric")
    panel.precisionField.setCurrentText("Medium")
    initialZoom = v.zoom
    initialPan = QtCore.QPointF(v.panOffset)
    observedUnits = set()
    for majorStep in (1000, 50, 5):
        v.zoom = 100 / (majorStep * v.basePixelsPerMillimeter)
        v.panOffset = QtCore.QPointF()
        divisor, unit = GridUnit(v.GridSteps()[0], v.unitsMode)
        observedUnits.add(unit)
        drawn.clear()
        with patch("planner_app.viewport.rendering.PathTextPainter", RecordingPainter):
            v.grab()
        expected = FormatLength(1234.6, v.unitsMode, adaptive = unit, precision = "Medium", includeUnit = False)
        assert expected in drawn and unit in drawn, (unit, drawn)
        # Explicit units do not change with zoom.
        panel.unitsField.setCurrentText("Meters")
        drawn.clear()
        with patch("planner_app.viewport.rendering.PathTextPainter", RecordingPainter):
            v.grab()
        assert "1.235" in drawn
        panel.unitsField.setCurrentText("Adaptive Metric")
    assert observedUnits == {"m", "cm", "mm"}
    v.zoom, v.panOffset = initialZoom, initialPan
    panel.unitsField.setCurrentText("Millimeters")
    panel.precisionField.setCurrentText("Low")
    data = main.BuildProjectData()
    assert DecodeProject(data, v.furnishingDefinitions)[5]["measurementPrecision"] == "Low"
    panel.precisionField.setCurrentText("High")
    main.ApplyProject(DecodeProject(data, v.furnishingDefinitions), None)
    assert panel.precisionField.currentText() == "Low"
    legacy = copy.deepcopy(data)
    legacy["settings"].pop("measurementPrecision")
    assert DecodeProject(legacy, v.furnishingDefinitions)[5]["measurementPrecision"] == "Medium"
    bad = copy.deepcopy(data)
    bad["settings"]["measurementPrecision"] = "Unknown"
    try:
        DecodeProject(bad, v.furnishingDefinitions)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid precision was accepted")
    main.sidebarTabs.setCurrentWidget(main.exportPanel)
    assert v.measurementPrecision == "Low"
    panel.precisionField.setCurrentText("Medium")
    assert v.measurementPrecision == "Medium" and main.ProjectSettings()["measurementPrecision"] == "Medium"
    with patch("planner_app.graphics.text.PathTextPainter", RecordingPainter), patch("planner_app.viewport.rendering.PathTextPainter", RecordingPainter):
        drawn.clear()
        image = RenderPlan("precision.plan", 100, (-1500, -1000, 3000, 2000), projectData = main.BuildProjectData(), applyTheme = False)
    assert not image.isNull() and "1235" in drawn
    main.sidebarTabs.setCurrentIndex(0)
    assert v.measurementPrecision == "Medium"
    main.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
