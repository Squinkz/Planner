"""Settings-window controls, final grid multipliers and preference recovery."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from theme import BuildStyle
from planner_app.graphics.theme import gridIntensityDefaults


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas")  # Fixed palette for pixel assertions.
    main.show()
    app.processEvents()
    main.headerButtons["Settings"].click()
    app.processEvents()
    settings = main.settingsWindow
    v = main.viewport
    assert main.headerButtons["Settings"].toolTip() == "Settings"
    assert settings.isVisible() and settings.isWindow() and not settings.isModal()
    assert [settings.tabs.tabText(index) for index in range(settings.tabs.count())] == ["Build", "Measurements", "Appearance"]
    settings.tabs.setCurrentIndex(2)
    assert all(not button.isEnabled() and not button.icon().isNull() for button in settings.resetButtons.values())
    major, minor = v.GridSteps()

    def GridBrightness(x):
        position = v.WorldToViewport(QtCore.QPointF(x, major * .37)).toPoint()
        image = v.grab().toImage()
        return max(image.pixelColor(position.x() + dx, position.y()).red() for dx in (-1, 0, 1))

    locations = {"major": major, "minor": minor, "origin": 0}
    defaults = {key: GridBrightness(x) for key, x in locations.items()}
    for key, x in locations.items():
        settings.sliders[key].setValue(0)
        assert settings.valueFields[key].value() == 0 and v.gridIntensities[key] == 0
        assert GridBrightness(x) == 14
        assert all(GridBrightness(otherX) == defaults[other] for other, otherX in locations.items() if other != key)
        settings.resetButtons[key].click()
        assert v.gridIntensities[key] == gridIntensityDefaults[key] and not settings.resetButtons[key].isEnabled()
        settings.sliders[key].setValue(1000)
        assert GridBrightness(x) == 255
        settings.resetButtons[key].click()
    settings.sliders["overall"].setValue(0)
    assert all(GridBrightness(x) == 14 for x in locations.values())
    settings.valueFields["overall"].setValue(.5)
    settings.valueFields["major"].setValue(.5)
    brightness = GridBrightness(major)
    assert abs(brightness - (14 + (255 - 14) * .25)) <= 1
    settings.valueFields["minor"].setValue(.3)
    settings.valueFields["origin"].setValue(.8)
    settings.sliders["overall"].setValue(2000)
    assert settings.valueFields["overall"].value() == 2 and v.gridIntensities["overall"] == 2
    assert GridBrightness(0) == 255
    app.processEvents()
    assert main.projectDirty
    expected = dict(v.gridIntensities)
    settings.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "viewport-settings.png"))
    settings.close()
    main.headerButtons["Settings"].click()
    assert main.settingsWindow is settings and settings.isVisible()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "Viewport.plan"
        assert main.SaveProject(path)
        assert main.NewProject() and v.gridIntensities == gridIntensityDefaults
        assert main.OpenProject(path) and v.gridIntensities == expected
    main.close()
    assert not settings.isVisible()
    restored = MainWindow()
    assert restored.viewport.gridIntensities == expected and not restored.projectDirty
    restored.ShowSettings()
    assert all(restored.settingsWindow.valueFields[key].value() == value for key, value in expected.items())
    restored.close()
    print("PASS: modeless settings tab, slider/spinbox/reset sync, independent and multiplied grid pixels, clean projects and preference recovery.")


if __name__ == "__main__":
    Main()
