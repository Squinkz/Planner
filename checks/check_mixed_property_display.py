"""Mixed numeric properties show their placeholder without a unit suffix."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow, Wall, SlidingDoor, Stair, Arrow, MeasurementGuide, Counter, Door, Window, SilledWindow, CasementWindow, BarnDoor, BifoldDoor, PocketDoor, OpenDoorway, Label
from planner_app.models import Furnishing


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    viewport = window.viewport
    viewport.unitsMode = "Adaptive Metric"  # Assertions explicitly expect meter/centimeter suffixes.
    point = QtCore.QPointF
    first = Wall(point(), point(4000, 0), 240)
    second = Wall(point(0, 2000), point(5000, 2000), 120)
    viewport.walls = [first, second]
    doors = [SlidingDoor(first, .1, .5), SlidingDoor(second, .1, .5)]
    viewport.windows = doors
    stairs = [Stair(point(0, 4000), point(2000, 4000), 1000),
              Stair(point(0, 6000), point(3000, 6000), 1200)]
    viewport.walls.extend(stairs)
    for objects, fields in (([first, second], ("width", "length")),
                            (doors, ("length", "doorSize")),
                            (stairs, ("width", "length"))):
        viewport.SetSelection([(obj, None) for obj in objects])
        app.processEvents()
        for fieldName in fields:
            field = window.propertyFields[fieldName]
            assert field.mixedValue and field.suffix() == ""
            assert field.lineEdit().text() == ""
            assert field.lineEdit().placeholderText() == "(different)"
            field.setFocus()
            viewport.setFocus()
            app.processEvents()
            assert field.lineEdit().text() == "" and field.mixedValue
        viewport.SetSelection([(objects[0], None)])
        for fieldName in fields:
            field = window.propertyFields[fieldName]
            assert not field.mixedValue and field.suffix().strip() in ("cm", "m")
            assert field.lineEdit().text().endswith(field.suffix())
    viewport.SetSelection([(first, None), (second, None)])
    field = window.propertyFields["width"]
    field.lineEdit().setFocus()
    QtTest.QTest.keyClicks(field.lineEdit(), "24")
    QtTest.QTest.keyClick(field.lineEdit(), QtCore.Qt.Key.Key_Return)
    assert first.width == second.width == 240
    assert not field.mixedValue and field.lineEdit().text() == "24.000 cm"
    viewport.windows = []
    counters = [Counter(point(0, 4000), point(2000, 4000), 600), Counter(point(0, 6000), point(3000, 6000), 800)]
    furnishings = [Furnishing(viewport.furnishingDefinitions["null"], point()),
                   Furnishing(viewport.furnishingDefinitions["null"], point(0, 4000))]
    furnishings[0].width, furnishings[0].secondVertex = 1000, point(2000, 0)
    furnishings[1].width, furnishings[1].secondVertex = 1200, point(3000, 4000)
    for objects in (counters, furnishings):
        viewport.walls = counters if objects is counters else []
        viewport.furnishings = furnishings if objects is furnishings else []
        viewport.SetSelection([(obj, None) for obj in objects])
        for fieldName in ("width", "length"):
            field = window.propertyFields[fieldName]
            assert field.mixedValue and field.suffix() == "" and field.lineEdit().text() == ""
            assert field.lineEdit().placeholderText() == "(different)"
    viewport.furnishings = []
    stairs[0].autosize, stairs[0].manualStepCount = False, 7
    stairs[1].autosize, stairs[1].manualStepCount = False, 10
    viewport.walls = stairs
    viewport.SetSelection([(obj, None) for obj in stairs])
    for fieldName in ("stepCount", "stepSize"):
        field = window.propertyFields[fieldName]
        assert field.mixedValue and field.suffix() == "" and field.lineEdit().text() == ""
        assert field.lineEdit().placeholderText() == "(different)"
    for openingClass in (Door, Window, SilledWindow, CasementWindow, BarnDoor, BifoldDoor, PocketDoor, OpenDoorway):
        viewport.walls = [first, second]
        viewport.windows = [openingClass(first, .1, .3), openingClass(second, .1, .4)]
        viewport.SetSelection([(obj, None) for obj in viewport.windows])
        field = window.propertyFields["doorSize" if openingClass is PocketDoor else "length"]
        assert field.mixedValue and field.suffix() == "" and field.lineEdit().text() == ""
        assert field.lineEdit().placeholderText() == "(different)"
    viewport.windows = []
    viewport.walls = []
    viewport.labels = [Label(point(), text = "First", intensity = .4), Label(point(0, 4000), text = "Second", intensity = .8)]
    viewport.SetSelection([(obj, None) for obj in viewport.labels])
    assert window.labelTextField.placeholderText() == "(different)"
    assert window.labelIntensityValue.text() == "(different)"
    viewport.labels = []
    for objectClass in (Arrow, MeasurementGuide):
        objects = [objectClass(point(), point(1000, 0)), objectClass(point(500, 2000), point(2500, 2000))]
        viewport.walls = objects
        for units in ("Adaptive Metric", "Meters", "Centimeters", "Millimeters"):
            viewport.unitsMode = units
            viewport.SetSelection([(obj, None) for obj in objects])
            field = window.arrowFields["length"]
            assert field.mixedValue and field.suffix() == "" and field.lineEdit().text() == ""
            assert field.lineEdit().placeholderText() == "(different)"
            field.setFocus()
            viewport.setFocus()
            app.processEvents()
            assert field.lineEdit().text() == ""
            viewport.SetSelection([(obj, 0) for obj in objects])
            for coordinate in ("x", "y"):
                field = window.propertyFields[coordinate]
                assert field.mixedValue and field.suffix() == "" and field.lineEdit().text() == ""
                assert field.lineEdit().placeholderText() == "(different)"
            viewport.SetSelection([(objects[0], None)])
            field = window.arrowFields["length"]
            assert not field.mixedValue and field.suffix().strip() in ("m", "cm", "mm")
            assert field.lineEdit().text().endswith(field.suffix())
    window.close()
    print("PASS: mixed wall/stair/opening fields, focus changes, unit restoration and typing a shared value.")


if __name__ == "__main__":
    Main()
