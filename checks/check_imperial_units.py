"""Imperial editing, physical rounding, font fractions and portable exports."""
import math
import os
import sys
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtSvg, QtTest
from planner import MainWindow
from planner_app.models import Wall, Stair, Furnishing, SilledWindow, MeasurementGuide, Label, NorthArrow
from planner_app.units import FormatLength, ParseImperialLength, PropertyUnit, imperialModes
from planner_app.project_codec import DecodeProject
from planner_app.graphics.measurement_text import MeasurementTextPath
from planner_app.graphics.fonts import LoadApplicationFonts, fontFamily
from planner_app.ui.widgets import DragSpinBox
from planner_app.furnishing_search import FindFurnishings
from planner_app.export_plan import RenderPlan


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts()
    for mode in imperialModes:
        expected = "1' 3.125\"" if mode == "Feet and Inches" else '15.125"'
        assert FormatLength(15.125 * 25.4, mode) == expected
        assert math.isclose(ParseImperialLength(expected, mode), 15.125 * 25.4)
        assert FormatLength(-15.125 * 25.4, mode) == "-" + expected
        for precision, inches in (("Low", 15), ("Medium", 15.25), ("High", 15.3125)):
            expected = {15: '15"', 15.25: '15 1/4"', 15.3125: '15 5/16"'}[inches]
            if mode == "Feet and Inches":
                expected = "1' 3" + expected[2:]
            assert FormatLength(15.31 * 25.4, mode, precision = precision) == expected
        assert FormatLength(.5 * 25.4, mode, precision = "Low") == '1"'
        assert FormatLength(-.01 * 25.4, mode, precision = "Low") == '0"'
    assert FormatLength(11.9999 * 25.4, "Feet and Inches") == "1' 0\""
    assert FormatLength(11.99 * 25.4, "Feet and Inches", precision = "High") == "1' 0\""
    assert FormatLength(1.9375 * 25.4, "Inches", precision = "High") == '1 15/16"'
    assert FormatLength(1.234567 * 25.4, "Inches", decimals = 5) == '1.235"'
    assert math.isclose(ParseImperialLength("-1 ft 3.125 in", "Feet and Inches"), -15.125 * 25.4)
    assert math.isclose(ParseImperialLength("1.5", "Feet and Inches"), 457.2)
    assert math.isclose(ParseImperialLength("1.5", "Inches"), 38.1)
    definitions = [{"key": "sample", "name": "Sample", "width": 381, "length": 609.6}]
    for query in ("w:15in l:2ft", "w:1' 3\" l:24\"", "w:1.25 l:2"):
        assert FindFurnishings(definitions, query, "Feet and Inches") == definitions, query
    for text in ("nan", "inf", "1' garbage", "9" * 500 + " ft"):
        try:
            ParseImperialLength(text, "Feet and Inches")
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid imperial input accepted")
    font = QtGui.QFont(fontFamily, 14)
    fractionPath = MeasurementTextPath('1\' 3 5/16"', font.toString(), 96)
    assert not fractionPath.isEmpty()
    numerator = MeasurementTextPath("5/16", font.toString(), 96).boundingRect()
    plain = QtGui.QPainterPath()
    font.setPixelSize(round(14 * 96 / 72))
    plain.addText(0, 0, font, "5/16")
    assert numerator.width() < plain.boundingRect().width() * .9, (numerator, plain.boundingRect())
    assert MeasurementTextPath('1\' 3 5/16"', QtGui.QFont(fontFamily, 14).toString(), 96) is fractionPath
    # Typing commits decimal mixed units through the same signals used by dragging.
    editor = DragSpinBox()
    editor.setRange(-1000, 1000)
    editor.setKeyboardTracking(False)
    editor.setSuffix(" ft")
    editor.setValue(1.234567)
    before = editor.value()
    editor.interpretText()
    assert editor.value() == before
    assert editor.text() == "1' 2.815\"", editor.text()
    editor.setSuffix(" in")
    editor.setValue(1.23456)
    before = editor.value()
    assert editor.text() == "1.235 in", editor.text()
    editor.interpretText()
    assert editor.value() == before
    editor.setSuffix(" ft")
    editor.show()
    editor.lineEdit().selectAll()
    QtTest.QTest.keyClicks(editor.lineEdit(), "1' 3.125\"")
    editor.interpretText()
    assert abs(editor.value() * 304.8 - 15.125 * 25.4) < .001, editor.text()
    editor.close()
    main = MainWindow()
    main.show()
    main.ShowSettings()
    v, panel = main.viewport, main.settingsWindow
    point = QtCore.QPointF
    panel.unitsField.setCurrentText("Feet and Inches")
    v.snapEnabled = v.gridSnapEnabled = True
    snapped = v.SnapPosition(point(1219.5, .3), QtCore.Qt.KeyboardModifier.NoModifier, preparedTargets = [])
    assert QtCore.QLineF(snapped, point(1219.2, 0)).length() < 1e-8, snapped
    exactWall = Wall(point(), snapped)
    v.walls = [exactWall]
    v.SetSelection([(exactWall, None)])
    field = main.propertyFields["length"]
    assert field.text() == "4' 0\"", (field.text(), exactWall.secondVertex)
    historyCount = len(v.undoHistory)
    for unused in range(5):
        main.RefreshProperties()
        field.interpretText()
    assert math.isclose(QtCore.QLineF(exactWall.firstVertex, exactWall.secondVertex).length(), 1219.2, rel_tol = 0, abs_tol = 1e-8)
    assert len(v.undoHistory) == historyCount, "Refreshing rounded properties edited scene geometry"
    panel.unitsField.setCurrentText("Inches")
    assert field.text() == "48.000 in", field.text()
    panel.unitsField.setCurrentText("Feet and Inches")
    secondExact = Wall(point(0, 2000), point(1219.2, 2000), 100)
    v.walls.append(secondExact)
    v.SetSelection([(exactWall, None), (secondExact, None)])
    assert field.text() == "4' 0\"", field.text()
    wall = Wall(point(-1000, 0), point(1000, 0))
    stair = Stair(point(0, 2000), point(2000, 2000))
    furniture = Furnishing(v.furnishingDefinitions["null"])
    furniture.firstVertex, furniture.secondVertex = point(-2000, 2000), point(-1000, 2000)
    furniture.width = 600
    north = NorthArrow(point(3000, 2000))
    label = Label(point(1000, -1500), "Units")
    v.walls, v.furnishings, v.labels = [wall, stair], [furniture, north], [label]
    v.EnsureObjectIds()
    for mode in imperialModes:
        before = v.CaptureState()
        panel.unitsField.setCurrentText(mode)
        assert v.CaptureState() == before
        assert "1/4 inch" in panel.precisionField.itemData(1, QtCore.Qt.ItemDataRole.ToolTipRole)
        for obj in (wall, stair, furniture, north):
            v.SetSelection([(obj, None)])
            main.RefreshProperties()
            for name, physical in (("width", obj.width), ("length", QtCore.QLineF(obj.firstVertex, obj.secondVertex).length())):
                field = main.propertyFields[name]
                divisor, unit = PropertyUnit(name, obj, mode)
                assert abs(field.value() * divisor - physical) < .001, (mode, name, field.text())
                field.setValue((physical + 25.4) / divisor)
                actual = obj.width if name == "width" else QtCore.QLineF(obj.firstVertex, obj.secondVertex).length()
                assert abs(actual - physical - 25.4) < .001, (mode, name, actual, physical)
                v.Undo()
        v.SetSelection([(label, None)])
        for name in ("width", "length"):
            physical = getattr(label, name)
            field = main.labelFields[name]
            divisor, unused = PropertyUnit(name, label, mode)
            assert abs(field.value() * divisor - physical) < .001
        assert main.labelFields["pointSize"].suffix() == " pt"
        opening = SilledWindow(wall, .2, .4)
        v.windows = [opening]
        v.SetSelection([(opening, None)])
        divisor, unused = PropertyUnit("sillDepth", opening, mode)
        main.propertyFields["sillDepth"].setValue(50.8 / divisor)
        assert abs(opening.sillDepth - 50.8) < .001, (mode, opening.sillDepth, main.propertyFields["sillDepth"].text(), v.selectedWall)
        v.windows = []
        settingsDivisor = 304.8 if mode == "Feet and Inches" else 25.4
        panel.sizeFields["Door"].setValue(1016 / settingsDivisor)
        assert abs(v.DefaultPlacementSize("Door") - 1016) < .01
        assert v.openingDefaultSizes["Door"] == 90
        panel.buildResetButtons["Door"].click()
        assert v.openingDefaultSizes["Door"] == 90
        panel.stepSizingFields["minimum"].setValue(254 / settingsDivisor)
        assert abs(v.AutoSizingLimits("stairs")["minimum"] - 254) < .001
        assert v.stairStepSizes["minimum"] == 25
        panel.stepSizingResetButtons["minimum"].click()
        assert v.stairStepSizes["minimum"] == 25
        assert abs(v.AutoSizingLimits("stairs")["minimum"] - 254) < .001
        major, minor = v.GridSteps()
        assert math.isclose(major / minor, 4)
        assert major / 25.4 >= 1 / 16
        data = main.BuildProjectData()
        assert DecodeProject(data, v.furnishingDefinitions)[5]["unitsMode"] == mode
        v.SetSelection([])
        with patch("planner_app.viewport.rendering.MeasurementTextPath", wraps = MeasurementTextPath) as drawPath:
            v.grab()
            assert drawPath.call_count > 0
            assert any('"' in call.args[0] for call in drawPath.call_args_list)
    main.ApplyProject(DecodeProject(data, v.furnishingDefinitions), None)
    assert panel.unitsField.currentText() == "Inches"
    panel.unitsField.setCurrentText("Feet and Inches")
    walls = [obj for obj in v.walls if type(obj) is Wall]
    second = Wall(point(3000, 0), point(5000, 0), 100)
    v.walls.append(second)
    v.SetSelection([(walls[0], None), (second, None)])
    field = main.propertyFields["width"]
    assert field.lineEdit().placeholderText() == "(different)"
    field.lineEdit().setFocus()
    QtTest.QTest.keyClicks(field.lineEdit(), '6.25"')
    QtTest.QTest.keyClick(field.lineEdit(), QtCore.Qt.Key.Key_Return)
    assert all(abs(obj.width - 158.75) < .001 for obj in (walls[0], second)), [obj.width for obj in (walls[0], second)]
    guide = MeasurementGuide(point(0, -1000), point(15.3125 * 25.4, -1000))
    v.walls.append(guide)
    v.measurementPrecision = "High"
    v.SetSelection([])
    with patch("planner_app.viewport.rendering.MeasurementTextPath", wraps = MeasurementTextPath) as drawPath:
        v.grab()
        assert any(call.args[0] == "1' 3 5/16\"" for call in drawPath.call_args_list)
    v.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "imperial-units.png"))
    v.SetSelection([(guide, None)])
    main.ShowMoveSpecial()
    dialog = main.moveSpecialWindow
    dialog.xField.lineEdit().selectAll()
    QtTest.QTest.keyClicks(dialog.xField.lineEdit(), '1"')
    before = point(guide.firstVertex)
    dialog.accept()
    assert abs(guide.firstVertex.x() - before.x() - 25.4) < .001
    main.sidebarTabs.setCurrentWidget(main.exportPanel)
    main.exportPanel.unitsField.setCurrentText("Inches")
    assert v.unitsMode == "Inches"
    data = main.BuildProjectData()
    assert data["settings"]["exportSettings"]["unitsMode"] == "Inches"
    main.sidebarTabs.setCurrentIndex(0)
    assert v.unitsMode == "Feet and Inches"
    data["settings"]["unitsMode"] = "Feet and Inches"
    data["settings"]["measurementPrecision"] = "High"
    bounds = (-3000, -2000, 6000, 6000)
    image = RenderPlan("imperial.plan", 100, bounds, projectData = data, applyTheme = False)
    svg = RenderPlan("imperial.plan", 100, bounds, outputFormat = "svg", projectData = data, applyTheme = False)
    root = ElementTree.fromstring(svg)
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert root.findall(".//s:path", ns)
    assert not any('/' in (element.text or "") for element in root.findall(".//s:text", ns)), "SVG fractions depend on viewer fonts"
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg))
    assert renderer.isValid() and not image.isNull()
    main.close()
    app.processEvents()
    print("PASS: imperial conversion/editing, precision, grid, persistence, export overrides and outlined fractions.")


if __name__ == "__main__":
    Main()
