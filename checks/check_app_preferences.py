"""Durable dialog folders and app themes are independent of project/export themes."""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtWidgets
from planner import MainWindow
from planner_app.graphics import palette
from planner_app.paths import appDirectory
from planner_app.project_codec import DecodeProject
from planner_app.project_recovery import RecoverProject


def Main():
    app = QtWidgets.QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory).resolve()
        projectFolder, browseFolder, exportFolder = [folder / name for name in ("projects", "browse", "exports")]
        for child in (projectFolder, browseFolder, exportFolder):
            child.mkdir()
        main = MainWindow()
        assert (palette.activeUITheme, palette.activeCanvasTheme) == ("Heather UI", "Magnetite Canvas")
        assert main.BrowseDirectory() == appDirectory
        main.projectPath = projectFolder / "home.plan"
        assert main.BrowseDirectory() == projectFolder
        main.RememberBrowseFolder(browseFolder / "example.plan")
        assert main.BrowseDirectory() == browseFolder
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value = ("", "")) as dialog:
            assert not main.OpenProject()
            assert Path(dialog.call_args.args[2]) == browseFolder
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value = ("", "")) as dialog:
            assert not main.SaveProjectAs()
            assert Path(dialog.call_args.args[2]) == browseFolder / "home.plan"
        assert main.BrowseDirectory() == browseFolder
        target = exportFolder / "drawing.svg"
        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value = str(exportFolder)) as dialog:
            main.exportPanel.BrowsePath()
            assert Path(dialog.call_args.args[2]) == projectFolder
        assert main.BrowseDirectory() == browseFolder
        assert main.BrowseDirectory(forExport = True) == exportFolder
        assert Path(main.exportPanel.folderField.text()) == exportFolder
        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value = "") as dialog:
            main.exportPanel.BrowsePath()
            assert Path(dialog.call_args.args[2]) == exportFolder
        main.appPreferences["lastExportFolder"] = str(folder / "missing")
        assert main.BrowseDirectory(forExport = True) == projectFolder
        main.RememberBrowseFolder(target, forExport = True)
        main.appPreferences["lastBrowseFolder"] = str(folder / "missing")
        assert main.BrowseDirectory() == projectFolder
        main.projectPath = folder / "missing" / "home.plan"
        assert main.BrowseDirectory() == appDirectory
        main.projectPath = None
        main.RememberBrowseFolder(browseFolder / "example.plan")
        main.SetThemes("Light UI", "Blueprint Canvas")
        main.MarkProjectClean()
        assert not main.projectDirty
        main.SetThemes("Neutral UI", "Light Canvas")
        main.RefreshProjectDirty()
        assert not main.projectDirty, "Application theme changes marked the project dirty"
        selectedThemes = (palette.activeUITheme, palette.activeCanvasTheme)
        assert main.NewProject()
        assert (palette.activeUITheme, palette.activeCanvasTheme) == selectedThemes
        project = main.BuildProjectData(includeHistory = False)
        assert not {"theme", "uiTheme", "canvasTheme"} & project["settings"].keys()
        legacy = copy.deepcopy(project)
        legacy["settings"].update(theme = "Dark", uiTheme = "Dark UI", canvasTheme = "Removed Canvas")
        decoded, repairs = RecoverProject(legacy, main.viewport.furnishingDefinitions, main.defaultProjectData)
        assert not repairs, repairs
        main.ApplyProject(decoded, None)
        assert (palette.activeUITheme, palette.activeCanvasTheme) == selectedThemes
        planPath = projectFolder / "saved.plan"
        assert main.SaveProject(planPath)
        savedData = json.loads(planPath.read_text(encoding = "utf-8"))
        assert not {"theme", "uiTheme", "canvasTheme"} & savedData["settings"].keys()
        assert main.OpenProject(planPath)
        assert (palette.activeUITheme, palette.activeCanvasTheme) == selectedThemes
        panel = main.exportPanel
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetOverride("canvasTheme", "Dark Canvas")
        assert palette.activeCanvasTheme == "Dark Canvas"
        exportingData = main.BuildProjectData(includeHistory = False)
        assert "canvasTheme" not in exportingData["settings"]
        assert exportingData["settings"]["exportSettings"]["canvasTheme"] == "Dark Canvas"
        preferences = json.loads(main.appPreferencesPath.read_text(encoding = "utf-8"))
        assert (preferences["uiTheme"], preferences["canvasTheme"]) == selectedThemes
        main.SetThemes(canvasTheme = "Blueprint Canvas")
        assert palette.activeCanvasTheme == "Dark Canvas", "Export override was lost"
        assert panel.projectView["canvasTheme"] == "Blueprint Canvas"
        main.sidebarTabs.setCurrentIndex(0)
        assert palette.activeCanvasTheme == "Blueprint Canvas"
        main.ApplyProject(DecodeProject(exportingData, main.viewport.furnishingDefinitions), None)
        assert palette.activeCanvasTheme == "Blueprint Canvas"
        assert main.exportPanel.overrides["canvasTheme"] == "Dark Canvas"
        main.RememberBrowseFolder(browseFolder / "example.plan")
        main.MarkProjectClean()
        main.SetViewOption("showTips")
        main.SetViewOption("showFpsCounter")
        assert not main.viewport.showTips and main.viewport.showFpsCounter
        main.RefreshProjectDirty()
        assert not main.projectDirty
        assert not {"showTips", "showFpsCounter"} & main.ProjectSettings().keys()
        legacyOptions = main.BuildProjectData(includeHistory = False)
        legacyOptions["settings"].update(showTips = True, showFpsCounter = False)
        decodedOptions, repairs = RecoverProject(legacyOptions, main.viewport.furnishingDefinitions, main.defaultProjectData)
        assert not repairs, repairs
        main.ApplyProject(decodedOptions, None)
        assert not main.viewport.showTips and main.viewport.showFpsCounter
        assert main.NewProject()
        assert not main.viewport.showTips and main.viewport.showFpsCounter
        main.WriteSession(wait = True)
        main.close()
        palette.SetThemes("Dark UI", "Dark Canvas")
        restarted = MainWindow()
        assert (palette.activeUITheme, palette.activeCanvasTheme) == ("Neutral UI", "Blueprint Canvas")
        assert restarted.BrowseDirectory() == browseFolder
        assert restarted.BrowseDirectory(forExport = True) == exportFolder
        assert not restarted.viewport.showTips and restarted.viewport.showFpsCounter
        assert restarted.viewport.performanceTimer.isActive() and not restarted.viewport.performanceLabel.isHidden()
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value = ("", "")) as dialog:
            assert not restarted.OpenProject()
            assert Path(dialog.call_args.args[2]) == browseFolder
        restarted.close()
    print("PASS: dialog folder precedence/restart, app themes, legacy projects, dirty state and isolated export themes.")


if __name__ == "__main__":
    Main()
