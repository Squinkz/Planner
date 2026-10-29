"""External palette validation, live painting and project/recovery theme choice."""
import json
import os
import sys
import tempfile
import warnings
import shutil
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.graphics import palette
from planner_app.graphics.theme import BuildStyle
from planner_app.ui.widgets import FurnishingButton
from planner_app.project_codec import DecodeProject


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    assert (palette.activeUITheme, palette.activeCanvasTheme) == ("Heather UI", "Magnetite Canvas")
    assert {"Dark UI", "Light UI", "Neutral UI", "Heather UI", "Dark Canvas", "Light Canvas", "Blueprint Canvas"}.issubset(palette.themeDefinitions)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)
        custom = {"name": "Custom", "type": "ui", "colors": dict(palette.themeDefinitions["Light UI"]["colors"])}
        (path / "custom.json").write_text(json.dumps(custom))
        commented = {"name": 'Comments // and "quotes"', "type": "canvas", "colors": dict(palette.themeDefinitions["Dark Canvas"]["colors"])}
        # Canvas themes written before export shading became configurable still load.
        commented["colors"].pop("exportOutsideShade")
        source = "// Theme header\n" + json.dumps(commented, indent = 4).replace('"colors": {', '"colors": { // Palette entries') + "\n// End of theme\n"
        (path / "commented.jsonc").write_text(source)
        (path / "broken.json").write_text('{"name": "Broken", "colors": {}}')
        with warnings.catch_warnings(record = True) as errors:
            definitions = palette.LoadThemes(path)
            assert set(definitions) == {"Custom", commented["name"]}
            assert definitions[commented["name"]]["colors"] == {**commented["colors"], "exportOutsideShade": "#41000000"}
            assert definitions[commented["name"]]["labelFont"] == "Noto Sans"
            assert len(errors) == 1
    main = MainWindow()
    main.show()
    main.headerButtons["Settings"].click()
    panel = main.settingsWindow
    panel.tabs.setCurrentIndex(2)
    assert {panel.uiThemeField.itemText(index) for index in range(panel.uiThemeField.count())} == {name for name, theme in palette.themeDefinitions.items() if theme["type"] == "ui"}
    assert {panel.canvasThemeField.itemText(index) for index in range(panel.canvasThemeField.count())} == {name for name, theme in palette.themeDefinitions.items() if theme["type"] == "canvas"}
    assert "Blueprint Canvas" in {main.exportPanel.canvasThemeField.itemText(index)
                                 for index in range(main.exportPanel.canvasThemeField.count())}
    v = main.viewport
    v.showGrid = False
    originalScene = main.BuildProjectData()["scene"]
    originalHistory = main.ProjectHistory()
    definition = main.viewport.furnishingDefinitions["desk"]
    for uiTheme in ("Light UI", "Neutral UI", "Dark UI"):
        oldCanvas = palette.activeCanvasTheme
        oldCanvasColors = {role: palette.themeColors[role] for role in palette.canvasRoles}
        panel.uiThemeField.setCurrentText(uiTheme)
        assert palette.activeCanvasTheme == oldCanvas
        assert {role: palette.themeColors[role] for role in palette.canvasRoles} == oldCanvasColors
        for canvasTheme in ("Light Canvas", "Blueprint Canvas", "Dark Canvas"):
            panel.canvasThemeField.setCurrentText(canvasTheme)
            assert palette.activeUITheme == uiTheme
            assert {role: palette.themeColors[role] for role in palette.uiRoles} == palette.themeDefinitions[uiTheme]["colors"]
    for name in ("Light Canvas", "Blueprint Canvas", "Dark Canvas", "Light Canvas"):
        oldPreview = main.furnishingThumbnails.Icon(definition).cacheKey()
        panel.canvasThemeField.setCurrentText(name)
        app.processEvents()
        assert palette.activeCanvasTheme == name
        assert oldPreview == main.furnishingThumbnails.Icon(definition).cacheKey(), "Canvas change needlessly rebuilt a catalog thumbnail"
        assert v.materialBrushes[("Generic", False)].color().name() == palette.themeColors["wallFill"]
        image = v.grab().toImage()
        assert image.pixelColor(v.DrawingRect().center().toPoint()).name() == palette.themeColors["canvas"]
        assert main.BuildProjectData()["scene"] == originalScene
        assert main.ProjectHistory() == originalHistory
        assert "canvasTheme" not in main.ProjectSettings()
        assert "uiTheme" not in main.ProjectSettings()
        assert "theme" not in main.ProjectSettings()
        for button in (main.fullscreenButton, main.groupModeButton):
            pixels = button.icon().pixmap(24, 24).toImage()
            assert any(pixels.pixelColor(x, y).name() == palette.themeColors["icon"] and pixels.pixelColor(x, y).alpha() > 200
                       for x in range(pixels.width()) for y in range(pixels.height()))
        Path("screenshots").mkdir(exist_ok = True)
        panel.grab().save("screenshots/appearance-theme-selectors.png")
    project = main.BuildProjectData()
    for legacyName in ("Dark", "Light", "Neutral", "Neutral, Dark Canvas", "Dark, Light Canvas"):
        legacy = {**project, "settings": dict(project["settings"])}
        legacy["settings"]["theme"] = legacyName
        decoded = DecodeProject(legacy, v.furnishingDefinitions)[5]
        assert "uiTheme" not in decoded and "canvasTheme" not in decoded
    main.SetThemes("Neutral UI", "Dark Canvas")
    main.ApplyProject(DecodeProject(project, v.furnishingDefinitions), None)
    assert panel.uiThemeField.currentText() == "Neutral UI" and panel.canvasThemeField.currentText() == "Dark Canvas"
    main.WriteSession(wait = True)
    main.close()
    recovered = MainWindow()
    assert (palette.activeUITheme, palette.activeCanvasTheme) == ("Neutral UI", "Dark Canvas")
    assert "canvasTheme" not in recovered.ProjectSettings()
    recovered.SetThemes(uiTheme = "Unavailable")
    assert palette.activeUITheme == "Heather UI" and palette.activeCanvasTheme == "Dark Canvas"
    recovered.SetThemes(canvasTheme = "Unavailable")
    assert palette.activeCanvasTheme == "Magnetite Canvas"
    recovered.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(dir = Path(__file__).resolve().parent) as folder:
        directory = Path(folder)
        os.environ["PLANNER_SESSION_PATH"] = str(directory / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(directory / "startup.plan")
        shutil.copy2(Path(__file__).resolve().parent.parent / "planner-main/startup.plan", directory / "startup.plan")
        Main()
    print("Independent UI/canvas themes, legacy migration and session recovery checks passed")
