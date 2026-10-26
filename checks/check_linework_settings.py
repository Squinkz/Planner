"""Appearance sliders, independent project widths, startup and recovery persistence."""
import copy
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow
from planner_app.project_codec import DecodeProject
from planner_app.preferences import lineworkDefaults
from planner_app.ui.widgets import SectionHeading


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    window = MainWindow()
    window.show()
    window.headerButtons["Settings"].click()
    panel = window.settingsWindow
    panel.tabs.setCurrentIndex(2)
    app.processEvents()
    assert lineworkDefaults == {"baseWidth": 4, "walls": 1, "architectural": .5, "furnishings": .25, "dimensions": .25}
    for key, field in panel.lineworkFields.items():
        original = field.value()
        field.setFocus()
        field.lineEdit().selectAll()
        valueText = "3.725" if key == "baseWidth" else "0.375"
        for character in valueText:
            QtTest.QTest.keyClicks(field, character)
            assert field.value() == original, "Typing committed an incomplete number"
        assert field.lineEdit().text() == valueText + field.suffix()
        QtTest.QTest.keyClick(field, QtCore.Qt.Key.Key_Return)
        assert panel.isVisible(), "Enter closed Settings while editing a value"
        assert not field.hasFocus() and not field.lineEdit().hasFocus(), "Enter did not release input focus"
        assert window.viewport.lineworkSettings[key] == float(valueText)
        assert panel.lineworkSliders[key].value() == round(float(valueText) * 1000)
        panel.lineworkResetButtons[key].click()
        assert window.viewport.lineworkSettings[key] == lineworkDefaults[key]
    panel.tabs.setCurrentIndex(0)
    app.processEvents()
    field = panel.buildPage.findChild(QtWidgets.QDoubleSpinBox)
    field.setFocus()
    field.lineEdit().selectAll()
    QtTest.QTest.keyClicks(field.lineEdit(), "15")
    QtTest.QTest.keyClick(field.lineEdit(), QtCore.Qt.Key.Key_Enter)
    assert panel.isVisible(), "Numpad Enter closed Settings from the embedded editor"
    assert not field.hasFocus() and not field.lineEdit().hasFocus()
    assert field.value() == 15
    panel.tabs.setCurrentIndex(2)
    headings = {label.text() for label in panel.viewportPage.findChildren(QtWidgets.QLabel)}
    assert {"Theme", "Grid", "Line Weight"} <= headings
    app.processEvents()
    for heading in panel.viewportPage.findChildren(SectionHeading):
        assert heading.objectName() == "sectionHeading"
        heading.layout().activate()
        caption = heading.titleLabel.parentWidget()
        assert abs(caption.geometry().center().x() - heading.rect().center().x()) <= 1
        assert len([frame for frame in heading.findChildren(QtWidgets.QFrame)
                    if frame.frameShape() == QtWidgets.QFrame.Shape.HLine]) == 2
    assert {"Auto Tread Depth", "Collisions", "Auto Railing Sizing"} <= {
        heading.titleLabel.text() for heading in panel.buildPage.findChildren(SectionHeading)}
    for key, slider in panel.lineworkSliders.items():
        assert (slider.minimum(), slider.maximum()) == ((1000, 4000) if key == "baseWidth" else (0, 2000))
        slider.setValue(3500 if key == "baseWidth" else 1250)
        assert panel.lineworkFields[key].value() == window.viewport.lineworkSettings[key]
        assert panel.lineworkResetButtons[key].isEnabled()
    expected = dict(window.viewport.lineworkSettings)
    for theme in ("Light", "Neutral", "Dark"):
        window.SetThemes(theme + " UI", ("Light" if theme == "Neutral" else theme) + " Canvas")
        assert window.viewport.lineworkSettings == expected
        assert window.viewport.lineWidths["walls"] == expected["baseWidth"] * expected["walls"]
    legacy = window.BuildProjectData()
    legacy["settings"].pop("lineworkSettings")
    assert DecodeProject(legacy, window.viewport.furnishingDefinitions)[5]["lineworkSettings"] == lineworkDefaults
    for key, invalid in (("baseWidth", 0), ("walls", -1), ("furnishings", 2.1), ("dimensions", float("nan"))):
        data = copy.deepcopy(window.BuildProjectData())
        data["settings"]["lineworkSettings"][key] = invalid
        try:
            DecodeProject(data, window.viewport.furnishingDefinitions)
            assert False, "Invalid line weight accepted"
        except ValueError:
            pass
    with tempfile.TemporaryDirectory() as folder:
        projectPath = Path(folder) / "weighted.plan"
        assert window.SaveProject(projectPath)
        panel.lineworkResetButtons["walls"].click()
        assert window.viewport.lineworkSettings["walls"] == lineworkDefaults["walls"]
        assert window.OpenProject(projectPath)
        assert window.viewport.lineworkSettings == expected
        assert panel.lineworkFields["walls"].value() == expected["walls"]
        with patch.object(window, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Save):
            assert window.SaveStartupFile()
        window.SetLinework(dict(lineworkDefaults))
        window.LoadStartupProject()
        assert window.viewport.lineworkSettings == expected
    app.processEvents()
    Path("screenshots").mkdir(exist_ok = True)
    assert panel.grab().save("screenshots/appearance-line-weight.png")
    panel.confirmButtons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).click()
    assert not panel.isVisible(), "The explicit OK button no longer closes Settings"
    window.close()
    recovered = MainWindow()
    assert recovered.sessionRestored and recovered.viewport.lineworkSettings == expected
    recovered.close()


if __name__ == "__main__":
    Main()
