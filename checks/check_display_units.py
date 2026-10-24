"""Display units convert editor fields without changing world geometry."""
import os
import sys
import math
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.models import Wall, Stair, Furnishing, SilledWindow, SlidingDoor
from planner_app.units import unitModes, PropertyUnit, FormatLength
from planner_app.project_codec import DecodeProject
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    main.ShowSettings()
    panel, v = main.settingsWindow, main.viewport
    assert v.unitsMode == panel.unitsField.currentText() == "Millimeters"
    assert panel.tabs.tabText(1) == "Measurements"
    assert [panel.unitsField.itemText(index) for index in range(len(unitModes))] == list(unitModes)
    point = QtCore.QPointF
    wall = Wall(point(), point(5000, 0))
    stair = Stair(point(10000, 10000), point(12000, 10000))
    furniture = Furnishing(v.furnishingDefinitions["null"])
    furniture.firstVertex, furniture.secondVertex = point(-5000, 5000), point(-3800, 5000)
    furniture.width = 600
    v.walls = [wall, stair]
    v.furnishings = [furniture]
    v.EnsureObjectIds()
    painterClass = QtGui.QPainter
    drawnText = []

    class RecordingPainter(painterClass):
        def drawText(self, *arguments):
            drawnText.append(arguments[-1])
            return super().drawText(*arguments)

    for mode in unitModes[:4]:
        before = v.CaptureState()
        panel.unitsField.setCurrentText(mode)
        assert v.CaptureState()[0] == before[0] and v.CaptureState()[5] == before[5]
        v.hoverPosition = v.WorldToViewport(point(1000, 0))
        drawnText.clear()
        with patch.object(QtGui, "QPainter", RecordingPainter):
            v.grab()
        unit, dimension, coordinate = {"Adaptive Metric": ("m", "5", "1.000 m"),
                                       "Meters": ("m", "5", "1.000 m"),
                                       "Centimeters": ("cm", "500", "100.000 cm"),
                                       "Millimeters": ("mm", "5000", "1000 mm")}[mode]
        assert unit in drawnText and dimension in drawnText, (mode, drawnText)
        assert dimension + " " + unit not in drawnText
        assert any(isinstance(text, str) and text.startswith(f"x: {coordinate}") for text in drawnText)
        for obj in (wall, stair, furniture):
            v.SetSelection([(obj, None)])
            main.RefreshProperties()
            for name, physical in (("width", obj.width), ("length", QtCore.QLineF(obj.firstVertex, obj.secondVertex).length())):
                divisor, unit = PropertyUnit(name, obj, mode)
                field = main.propertyFields[name]
                assert math.isclose(field.value(), physical / divisor, abs_tol = .0005)
                assert field.suffix() == " " + unit
                if mode == "Millimeters":
                    assert field.decimals() == 0
                field.setValue(physical / divisor + 100 / divisor)
                actual = obj.width if name == "width" else QtCore.QLineF(obj.firstVertex, obj.secondVertex).length()
                assert abs(actual - physical - 100) < .001
                v.Undo()
                assert abs((obj.width if name == "width" else QtCore.QLineF(obj.firstVertex, obj.secondVertex).length()) - physical) < .001
        v.SetSelection([(wall, 0)])
        divisor, unused = PropertyUnit("x", wall, mode)
        main.propertyFields["x"].setValue(100 / divisor)
        assert abs(wall.firstVertex.x() - 100) < .001
        v.Undo()
        for cls, fieldName, physical in ((SilledWindow, "sillDepth", 40), (SlidingDoor, "doorSize", 500)):
            opening = cls(wall, .2, .4)
            v.windows = [opening]
            v.SetSelection([(opening, None)])
            divisor, unit = PropertyUnit(fieldName, opening, mode)
            assert abs(main.propertyFields[fieldName].value() - physical / divisor) < .001
            main.propertyFields[fieldName].setValue((physical + 100) / divisor)
            assert abs((opening.sillDepth if fieldName == "sillDepth" else opening.length / 2) - physical - 100) < .001
            v.windows = []
        v.SetSelection([(stair, None)])
        main.EditStairAutosize(False)
        divisor, unit = PropertyUnit("stepSize", stair, mode)
        main.propertyFields["stepSize"].setValue(300 / divisor)
        assert stair.stepCount == 7 and abs(stair.stepSize - 2000 / 7) < .001
        main.EditStairAutosize(True)
        settingsDivisor = {"Meters": 1000, "Centimeters": 10, "Millimeters": 1}.get(mode, 10)
        panel.sizeFields["Door"].setValue(1000 / settingsDivisor)
        assert v.openingDefaultSizes["Door"] == 100
        panel.buildResetButtons["Door"].click()
        assert v.openingDefaultSizes["Door"] == 90
        panel.stepSizingFields["minimum"].setValue(260 / settingsDivisor)
        assert v.stairStepSizes["minimum"] == 26
        panel.stepSizingResetButtons["minimum"].click()
        assert v.stairStepSizes["minimum"] == 25
        v.SetSelection([(wall, None), (stair, None)])
        main.RefreshProperties()
    # Common-class bulk editing and mixed placeholders retain the displayed units.
    second = Wall(point(-5000, 0), point(-1000, 0), 120)
    v.walls.append(second)
    v.SetSelection([(wall, None), (second, None)])
    assert main.propertyFields["width"].lineEdit().placeholderText() == "(different)"
    main.EditProperty("width", 180)
    assert wall.width == second.width == 180
    # Display rounding preserves fractional geometry, even through repeated refreshes.
    wall.width = 180.6
    v.SetSelection([(wall, None)])
    main.RefreshProperties()
    assert main.propertyFields["width"].value() == 181 and wall.width == 180.6
    assert FormatLength(180.6, "Millimeters") == "181 mm"
    assert FormatLength(180.4, "Millimeters") == "180 mm"
    for mode, divisor in (("Adaptive Metric", 1000), ("Meters", 1000), ("Centimeters", 10)):
        for value, expected in ((.999, "1"), (59.999, "60"), (42.999, "43"),
                                (44.999, "45"), (101.999, "102"), (60.001, "60"), (59.998, "59.998")):
            assert FormatLength(value * divisor, mode, includeUnit = False, snapToInteger = True) == expected
    assert FormatLength(59.999 * 1000, "Meters") == "59.999 m"
    assert panel.sizeFields["Door"].decimals() == panel.stepSizingFields["minimum"].decimals() == 0
    app.processEvents()
    panel.tabs.setCurrentIndex(1)
    panel.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "measurement-units.png"))
    # Temporary openings and direct geometry changes above bypass history tracking.
    # Start persistence coverage with a consistent history and one real editor change.
    v.undoHistory.clear()
    v.redoHistory.clear()
    main.propertyFields["width"].setValue(190)
    assert wall.width == 190 and len(v.undoHistory) == 1
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "Units.plan"
        assert main.SaveProject(path)
        panel.unitsField.setCurrentText("Meters")
        app.processEvents()
        assert main.projectDirty
        with patch.object(main, "ConfirmProjectReplacement", return_value = True):
            assert main.NewProject() and v.unitsMode == "Millimeters"
        assert main.OpenProject(path) and v.unitsMode == "Millimeters"
        assert not main.projectDirty and len(v.undoHistory) == 1
        assert panel.unitsField.currentText() == "Millimeters" and main.wallWidthSelector.unitsMode == "Millimeters"
        data = main.BuildProjectData()
        del data["settings"]["unitsMode"]
        # Older projects without a unit preference retain their legacy display mode.
        assert DecodeProject(data, v.furnishingDefinitions)[5]["unitsMode"] == "Adaptive Metric"
    main.close()
    restored = MainWindow()
    assert restored.viewport.unitsMode == "Millimeters" and not restored.projectDirty
    assert len(restored.viewport.undoHistory) == 1
    restored.close()
    print("PASS: all unit modes, geometry preservation, editable sizes/coordinates/openings, manual steps, resets, bulk edits and persistence.")


if __name__ == "__main__":
    Main()
