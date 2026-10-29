"""Removed export themes must not break project loading or session restoration."""
import copy
import os
from pathlib import Path
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtWidgets
from planner import MainWindow
from planner_app.graphics import palette
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.project_codec import DecodeProject


def Main():
    with tempfile.TemporaryDirectory(dir = Path(__file__).parent) as folder:
        for name, filename in (("PLANNER_SESSION_PATH", "session.json"),
                               ("PLANNER_STARTUP_PATH", "startup.plan"),
                               ("PLANNER_PREFERENCES_PATH", "preferences.json")):
            os.environ[name] = str(Path(folder) / filename)
        app = QtWidgets.QApplication([])
        LoadApplicationFonts(app)
        ApplyApplicationTheme(app)
        main = MainWindow()
        data = main.BuildProjectData(includeHistory = False, includeActivity = False)
        uiTheme = next(name for name, definition in palette.themeDefinitions.items() if definition["type"] == "ui")
        for theme in ("Print Canvas", "Removed Custom Canvas", uiTheme):
            saved = copy.deepcopy(data)
            saved["settings"]["exportSettings"] = dict(canvasTheme = theme, canvasColor = "#f0eedd",
                titleBlock = dict(enabled = True), bounds = [0, 0, 2000, 2000], scale = 100)
            main.ApplyProject(DecodeProject(saved, main.viewport.furnishingDefinitions), None)
            panel = main.exportPanel
            assert main.sidebarTabs.currentWidget() is main.buildScrollArea
            resolvedTheme = panel.ResolvedView()["canvasTheme"]
            assert palette.themeDefinitions[resolvedTheme]["type"] == "canvas"
            assert panel.canvasThemeField.currentText() == resolvedTheme
            assert panel.overrides["canvasColor"] == "#f0eedd"
            assert panel.overrides["canvasTheme"] == theme, "Resolution must not discard the saved theme preference"
            main.sidebarTabs.setCurrentWidget(panel)
            assert palette.activeCanvasTheme == resolvedTheme
            assert not panel.Render("png").isNull()
            main.sidebarTabs.setCurrentWidget(main.buildScrollArea)
        # Reproduce the reported MainWindow -> RestoreSession -> ApplyProject path.
        main.exportPanel.overrides["canvasTheme"] = "Print Canvas"
        main.MarkProjectClean()
        main.close()
        recovered = MainWindow()
        assert palette.themeDefinitions[recovered.exportPanel.ResolvedView()["canvasTheme"]]["type"] == "canvas"
        recovered.MarkProjectClean()
        recovered.close()
    print("Missing export theme project loading and startup recovery passed")


if __name__ == "__main__":
    Main()
