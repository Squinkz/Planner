"""Application preferences kept independently of project and recovery files."""
import json
import os
import warnings
from pathlib import Path
from PySide6 import QtCore, QtWidgets
from planner_app.paths import appDirectory
from planner_app.graphics import palette
from planner_app.graphics.theme import ApplyApplicationTheme


def LoadAppPreferences():
    override = os.environ.get("PLANNER_PREFERENCES_PATH")
    path = (Path(override) if override else
        Path(QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.GenericDataLocation)) /
        "Planner" / "preferences.json")
    preferences = {}
    try:
        data = json.loads(path.read_text(encoding = "utf-8"))
        if isinstance(data, dict):
            preferences = data
    except FileNotFoundError:
        pass
    except (OSError, ValueError, UnicodeError) as error:
        warnings.warn(f"Cannot read application preferences: {error}")
    return path, preferences


class AppPreferencesMixin:
    def InitializeAppPreferences(self):
        self.appPreferencesPath, self.appPreferences = LoadAppPreferences()
        recentProjects = self.appPreferences.get("recentProjects", [])
        paths, seen = [], set()
        for value in recentProjects if isinstance(recentProjects, list) else []:
            if not isinstance(value, str) or not value or "\0" in value:
                continue
            path = Path(value)
            key = os.path.normcase(str(path))
            if path.is_absolute() and key not in seen:
                paths.append(str(path))
                seen.add(key)
            if len(paths) == 10:
                break
        self.appPreferences["recentProjects"] = paths
        themes = {}
        for field, themeType in (("uiTheme", "ui"), ("canvasTheme", "canvas")):
            name = self.appPreferences.get(field)
            if isinstance(name, str) and palette.themeDefinitions.get(name, {}).get("type") == themeType:
                themes[field] = name
        previousUI = palette.activeUITheme
        palette.SetThemes(**themes)
        if previousUI != palette.activeUITheme:
            ApplyApplicationTheme(QtWidgets.QApplication.instance())

    def SaveAppPreferences(self):
        try:
            self.appPreferencesPath.parent.mkdir(parents = True, exist_ok = True)
            payload = json.dumps(self.appPreferences, indent = 2, ensure_ascii = False).encode("utf-8")
            file = QtCore.QSaveFile(str(self.appPreferencesPath))
            if not file.open(QtCore.QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(file.errorString())
            if file.write(payload) != len(payload):
                error = file.errorString()
                file.cancelWriting()
                raise OSError(error)
            if not file.commit():
                raise OSError(file.errorString())
        except (OSError, ValueError) as error:
            warnings.warn(f"Cannot save application preferences: {error}")

    def BrowseDirectory(self, forExport = False):
        lastFolder = self.appPreferences.get("lastExportFolder" if forExport else "lastBrowseFolder")
        if isinstance(lastFolder, str) and lastFolder and Path(lastFolder).is_dir():
            return Path(lastFolder)
        project = getattr(self, "projectPath", None)
        if project is not None and project.parent.is_dir():
            return project.parent
        return appDirectory

    def RememberBrowseFolder(self, path, forExport = False):
        folder = Path(path).resolve().parent
        if folder.is_dir():
            self.appPreferences["lastExportFolder" if forExport else "lastBrowseFolder"] = str(folder)
            self.SaveAppPreferences()

    def RememberRecentProject(self, path):
        path = str(Path(path).resolve())
        key = os.path.normcase(path)
        recentProjects = [value for value in self.appPreferences["recentProjects"] if os.path.normcase(value) != key]
        self.appPreferences["recentProjects"] = [path, *recentProjects][:10]
        self.SaveAppPreferences()
        if hasattr(self, "menuButtons") and "Open Recent" in self.menuButtons:
            self.menuButtons["Open Recent"].setEnabled(True)
