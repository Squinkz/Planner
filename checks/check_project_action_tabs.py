"""Project replacement returns to Build; saving preserves the current workspace."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))

from PySide6 import QtWidgets
from planner import MainWindow


def Main():
    with tempfile.TemporaryDirectory(dir = Path(__file__).parent) as folder:
        folder = Path(folder)
        os.environ["PLANNER_SESSION_PATH"] = str(folder / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(folder / "startup.plan")
        app = QtWidgets.QApplication([])
        main = MainWindow()
        main.show()
        path = folder / "Actions.plan"
        assert main.SaveProjectAs(path)
        actions = (main.NewProject, main.CloseProject, lambda: main.OpenProject(path), main.RevertProject)
        for action in actions:
            assert main.OpenProject(path)
            main.sidebarTabs.setCurrentWidget(main.exportPanel)
            assert main.viewport.exportOverlay.active
            assert action()
            assert main.sidebarTabs.currentWidget() is main.buildScrollArea
            assert not main.viewport.exportOverlay.active and main.exportPanel.projectView is None
        for action in (main.SaveProject, lambda: main.SaveProjectAs(folder / "Copy.plan")):
            main.sidebarTabs.setCurrentWidget(main.exportPanel)
            view = main.exportPanel.projectView
            assert action()
            assert main.sidebarTabs.currentWidget() is main.exportPanel
            assert main.viewport.exportOverlay.active and main.exportPanel.projectView is view
            assert not main.projectDirty
        for action, dialog in ((main.OpenProject, "getOpenFileName"), (main.SaveProjectAs, "getSaveFileName")):
            main.sidebarTabs.setCurrentWidget(main.exportPanel)
            with patch.object(QtWidgets.QFileDialog, dialog, return_value = ("", "")):
                assert not action()
            assert main.sidebarTabs.currentWidget() is main.exportPanel
            assert main.viewport.exportOverlay.active
        main.exportPanel.SetScaleOption("scaleMode", "Digital")
        main.exportPanel.SetBorder("Frame")
        main.exportPanel.BeginExportGesture()
        main.exportPanel.borderSizeField.lineEdit().setFocus()
        main.exportPanel.borderSizeField.lineEdit().setText("70")
        app.processEvents()
        assert main.SaveProject()
        saved = json.loads(main.projectPath.read_text(encoding = "utf-8"))
        assert saved["settings"]["exportSettings"]["borderSize"] == 70, "Save missed pending export text"
        assert main.exportPanel.exportGestureBefore is None and not main.viewport.exportOverlay.previewGesture
        assert main.sidebarTabs.currentWidget() is main.exportPanel
        with patch.object(main, "ShowAppMessage"):
            assert not main.SaveProject(folder / "missing-folder" / "Failed.plan")
        assert main.sidebarTabs.currentWidget() is main.exportPanel and main.viewport.exportOverlay.active
        main.CloseProject()
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        assert not main.RevertProject()
        assert main.sidebarTabs.currentWidget() is main.buildScrollArea
        main.MarkProjectClean()
        main.close()
        app.processEvents()
    print("Project action tab checks passed")


if __name__ == "__main__":
    Main()
