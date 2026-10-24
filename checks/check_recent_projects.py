"""Recent project ordering, durable preferences and themed submenu actions."""
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


def Main():
    app = QtWidgets.QApplication([])
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        os.environ["PLANNER_PREFERENCES_PATH"] = str(folder / "preferences.json")
        main = MainWindow()
        assert not main.menuButtons["Open Recent"].isEnabled()
        actions = main.fileMenu.actions()
        assert actions[1].defaultWidget().accessibleName() == "Open Project"
        assert actions[2].isSeparator()
        assert actions[3].defaultWidget().accessibleName() == "Open Recent"
        project = json.dumps(main.BuildProjectData(includeHistory = False))
        paths = []
        for index in range(12):
            path = folder / f"folder{index}" / "house.plan"
            path.parent.mkdir()
            path.write_text(project, encoding = "utf-8")
            paths.append(path)
            assert main.OpenProject(path)
        expected = [str(path.resolve()) for path in reversed(paths[2:])]
        assert main.appPreferences["recentProjects"] == expected
        assert main.menuButtons["Open Recent"].isEnabled()
        assert main.OpenProject(paths[4])
        expected.remove(str(paths[4].resolve()))
        expected.insert(0, str(paths[4].resolve()))
        assert main.appPreferences["recentProjects"] == expected
        with patch.object(main, "ConfirmProjectReplacement", return_value = False):
            assert not main.OpenProject(paths[0])
        with patch.object(main, "ShowAppMessage"):
            assert not main.OpenProject(folder / "missing.plan")
        assert main.appPreferences["recentProjects"] == expected
        menu = QtWidgets.QMenu(main)
        main.PopulateRecentProjects(menu)
        rows = [action.defaultWidget() for action in menu.actions()]
        assert len(rows) == 10 and len({row.accessibleName() for row in rows}) == 10
        assert "folder4" in rows[0].accessibleName() and "house.plan" in rows[0].accessibleName()
        assert rows[0].toolTip() == expected[0]
        with patch.object(main, "OpenProject", return_value = True) as opened:
            rows[0].click()
            opened.assert_called_once_with(Path(expected[0]))
        paths[4].unlink()
        menu.clear()
        main.PopulateRecentProjects(menu)
        assert not menu.actions()[0].defaultWidget().isEnabled()
        saved = folder / "new.plan"
        assert main.SaveProject(saved)
        assert main.appPreferences["recentProjects"][0] == str(saved.resolve())
        stored = json.loads(main.appPreferencesPath.read_text(encoding = "utf-8"))["recentProjects"]
        assert "recentProjects" not in main.BuildProjectData()["settings"]
        main.MarkProjectClean()
        main.close()
        reopened = MainWindow()
        assert reopened.appPreferences["recentProjects"] == stored
        assert reopened.menuButtons["Open Recent"].isEnabled()
        reopened.MarkProjectClean()
        reopened.close()
        # Invalid preference entries cannot break startup or enter the submenu.
        preferences = json.loads((folder / "preferences.json").read_text(encoding = "utf-8"))
        preferences["recentProjects"] = [None, 12, "", "relative.plan", "bad\0path", str(saved), str(saved).upper()]
        (folder / "preferences.json").write_text(json.dumps(preferences), encoding = "utf-8")
        cleaned = MainWindow()
        assert cleaned.appPreferences["recentProjects"] == [str(saved)]
        cleaned.MarkProjectClean()
        cleaned.close()
    print("PASS: recent projects capped at ten, deduplicated, persisted, disambiguated and opened safely")


if __name__ == "__main__":
    Main()
