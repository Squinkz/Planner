"""Restricted arithmetic, native commit behavior, units and property transactions."""
import math
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner_app.number_expressions import EvaluateNumberExpression
from planner_app.ui.widgets import UnitSpinBox, ExpressionSpinBox, DragSpinBox
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.theme import ApplyApplicationTheme
from planner import MainWindow
from furnishings import Furnishing


def Main():
    for text, expected in (("120 + 4", 124), ("120*0.5", 60), ("120/3", 40),
                           ("(120+20)*2", 280), ("+4", 124), ("*0.5", 60),
                           ("/3", 40), ("-4", -4), ("120-4", 116),
                           ("2+3*4", 14), ("8/4/2", 1), ("1e-3*2", .002)):
        assert math.isclose(EvaluateNumberExpression(text, 120), expected), text
    malicious = ("__import__('os').system('echo unsafe')", "open('file', 'w')", "(1).__class__",
                 "[1][0]", "lambda:1", "True+1", "1**999999", "1//2", "1%2", "1;2",
                 "1e999", "1/0", "(1+2", "1+", "1 2", "1" * 300, "(" * 30 + "1" + ")" * 30)
    with patch("builtins.eval", side_effect = AssertionError("eval called")), \
            patch("builtins.exec", side_effect = AssertionError("exec called")):
        for text in malicious:
            try:
                EvaluateNumberExpression(text, 120)
            except ValueError:
                pass
            else:
                raise AssertionError(text)
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    ApplyApplicationTheme(app)
    host = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(host)
    fields = [UnitSpinBox(), ExpressionSpinBox(), DragSpinBox()]
    for field in fields:
        field.setRange(-1000, 1000)
        layout.addWidget(field)
    away = QtWidgets.QLineEdit()
    layout.addWidget(away)
    host.show()
    app.processEvents()
    for field in fields:
        for tracking in (False, True):
            field.setKeyboardTracking(tracking)
            for text, expected in (("+4", 124), ("*0.5", 60), ("120+4", 124),
                                   ("(120+20)*2", 280), ("120/3", 40)):
                field.setValue(120)
                field.setFocus()
                field.lineEdit().selectAll()
                QtTest.QTest.keyClicks(field.lineEdit(), text)
                assert text in field.text(), (type(field), tracking, text, field.text())
                QtTest.QTest.keyClick(field, QtCore.Qt.Key.Key_Return)
                assert field.value() == expected, (type(field), tracking, text, field.value(), field.text())
                field.interpretText()
                assert field.value() == expected, "Relative input must not be applied twice"
        field.setValue(120)
        field.lineEdit().setText("*0.5")
        away.setFocus()
        app.processEvents()
        assert field.value() == 60
        for text in ("+", "120/0", "__import__('os')", "120*1000"):
            field.setValue(120)
            field.lineEdit().setText(text)
            field.interpretText()
            assert field.value() == 120, (text, field.value())
    decimal = fields[0]
    decimal.setSuffix(" mm")
    decimal.setValue(120)
    decimal.lineEdit().setText("120 mm+4")
    decimal.interpretText()
    assert decimal.value() == 124
    decimal.setSuffix(" ft")
    decimal.setValue(1.234568)
    decimal.lineEdit().setText(decimal.text() + "*0.5")
    decimal.interpretText()
    assert math.isclose(decimal.value(), .617284), decimal.value()
    decimal.setValue(2)
    decimal.lineEdit().setText('2\' 0"*0.5')
    decimal.interpretText()
    assert decimal.value() == 1
    decimal.lineEdit().setText('1\' 0"+6"')
    decimal.interpretText()
    assert decimal.value() == 1.5
    decimal.setValue(2)
    decimal.lineEdit().setText("+1")
    decimal.interpretText()
    assert decimal.value() == 3
    decimal.setSuffix(" cm")
    decimal.setValue(-120)
    decimal.lineEdit().setText("-4 cm")
    decimal.interpretText()
    assert decimal.value() == -4
    decimal.setLocale(QtCore.QLocale("de_DE"))
    decimal.setValue(120)
    decimal.lineEdit().setText("120*0,5 cm")
    decimal.interpretText()
    assert decimal.value() == 60
    decimal.setSuffix(" ft")
    decimal.setValue(1.234568)
    decimal.lineEdit().setText(decimal.text() + "*0,5")
    decimal.interpretText()
    assert math.isclose(decimal.value(), .617284), decimal.value()
    integer = fields[1]
    integer.setValue(3)
    integer.lineEdit().setText("*0.5")
    integer.interpretText()
    assert integer.value() == 2
    host.close()
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.unitsMode = "Millimeters"
    desk = Furnishing(v.furnishingDefinitions["desk"])
    v.furnishings = [desk]
    v.SetSelection([(desk, None)])
    width, length = desk.width, desk.length
    before = v.CaptureState()
    field = main.propertyFields["width"]
    field.lineEdit().setText("*0.5 mm")
    field.interpretText()
    assert desk.width == width / 2 and desk.length == length / 2
    v.Undo()
    assert v.CaptureState() == before
    other = Furnishing(dict(v.furnishingDefinitions["desk"], width = 800), QtCore.QPointF(10000, 0))
    v.furnishings.append(other)
    v.SetSelection([(desk, None), (other, None)])
    for text in ("+4", "120/0"):
        before = v.CaptureState()
        field.setFocus()
        field.lineEdit().selectAll()
        QtTest.QTest.keyClicks(field.lineEdit(), text)
        QtTest.QTest.keyClick(field, QtCore.Qt.Key.Key_Return)
        assert v.CaptureState() == before, "Invalid mixed-field arithmetic must not flatten selected dimensions"
    assert isinstance(main.exportPanel.scaleField, UnitSpinBox)
    assert isinstance(main.exportPanel.borderSizeField, ExpressionSpinBox)
    main.MarkProjectClean()
    main.close()
    print("PASS: safe bounded arithmetic, relative inputs, commit/focus, integer/decimal/imperial fields, linked properties and undo.")


if __name__ == "__main__":
    Main()
