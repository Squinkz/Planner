"""Independent export folder/name fields, native folder browsing and undo."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall
from planner_app.project_codec import DecodeProject
from planner_app.project_recovery import RecoverProject


def Main():
    with ExampleWindow() as (main, folder):
        v, panel = main.viewport, main.exportPanel
        InstallScene(main, [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0))])
        main.projectPath = folder / "project.plan"
        (folder / "project.png").write_bytes(b"existing")
        main.sidebarTabs.setCurrentWidget(panel)
        assert Path(panel.folderField.text()) == folder and panel.fileNameField.text() == "project_1.png"
        panel.fileNameField.setText("custom.png")
        panel.fileNameField.editingFinished.emit()
        panel.ResetExportHistory()
        target = folder / "output folder"
        target.mkdir()
        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value = str(target)) as browse:
            panel.browseButton.click()
            assert Path(browse.call_args.args[2]) == folder
        assert Path(panel.folderField.text()) == target and panel.fileNameField.text() == "custom.png"
        assert panel.typeField.currentData() == "PNG" and len(panel.exportUndoHistory) == 1
        assert main.BrowseDirectory(forExport = True) == target
        v.Undo()
        assert Path(panel.folderField.text()) == folder and panel.fileNameField.text() == "custom.png"
        v.Redo()
        assert panel.OutputPath() == target / "custom.png"
        panel.fileNameField.setText("another")
        panel.fileNameField.editingFinished.emit()
        assert panel.fileNameField.text() == "another.png"
        v.Undo()
        assert panel.OutputPath() == target / "custom.png"
        v.Redo()
        assert panel.OutputPath() == target / "another.png"
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        assert panel.OutputPath() == target / "another.svg" and Path(panel.folderField.text()) == target
        v.Undo()
        assert panel.typeField.currentData() == "PNG" and panel.OutputPath() == target / "another.png"
        state = panel.ExportHistoryState()
        count = len(panel.exportUndoHistory)
        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value = ""):
            panel.browseButton.click()
        assert panel.ExportHistoryState() == state and len(panel.exportUndoHistory) == count
        for name in ("../bad.png", "bad\\name.png", "..", "bad:name.png"):
            panel.fileNameField.setText(name)
            panel.fileNameField.editingFinished.emit()
            with patch.object(main, "ShowAppMessage") as error:
                panel.Export()
            assert error.call_count == 1 and error.call_args.args[0] == "Export Failed"
            assert main.exportButton.isEnabled() and QtWidgets.QApplication.overrideCursor() is None
        panel.fileNameField.setText("finished.png")
        panel.fileNameField.editingFinished.emit()
        with patch.object(main, "ShowAppMessage") as message:
            panel.Export()
        assert not message.called and (target / "finished.png").exists()
        main.sidebarTabs.setCurrentIndex(0)
        main.sidebarTabs.setCurrentWidget(panel)
        assert panel.OutputPath() == target / "finished.png"
        # Destinations belong to the plan, including typed edits and session data.
        main.sidebarTabs.setCurrentIndex(0)
        assert main.SaveProject()
        saved = main.BuildProjectData(includeHistory = False)
        assert saved["settings"]["exportFolder"] == str(target)
        decoded, repairs = RecoverProject(saved, v.furnishingDefinitions, main.defaultProjectData)
        assert not repairs, repairs
        otherFolder = folder / "other project"
        otherFolder.mkdir()
        other = main.BuildProjectData(includeHistory = False)
        other["settings"].pop("exportFolder")
        # Old global preferences must not influence a new project's destination.
        main.appPreferences["lastExportFolder"] = str(target)
        main.ApplyProject(DecodeProject(other, v.furnishingDefinitions), otherFolder / "other.plan")
        assert Path(panel.folderField.text()) == otherFolder and panel.exportFolder is None
        assert main.SaveProject()
        otherPath = main.projectPath
        assert main.OpenProject(folder / "project.plan")
        assert Path(panel.folderField.text()) == target
        assert panel.fileNameField.text() == "finished.png"
        typedFolder = folder / "typed output"
        typedFolder.mkdir()
        main.sidebarTabs.setCurrentWidget(panel)
        panel.folderField.setText(str(typedFolder))
        panel.folderField.editingFinished.emit()
        assert main.ProjectSettings()["exportFolder"] == str(typedFolder)
        v.Undo()
        assert panel.exportFolder == str(target)
        v.Redo()
        assert panel.exportFolder == str(typedFolder)
        main.sidebarTabs.setCurrentIndex(0)
        assert main.SaveProject()
        assert main.OpenProject(otherPath)
        assert Path(panel.folderField.text()) == otherFolder
        assert main.OpenProject(folder / "project.plan")
        assert Path(panel.folderField.text()) == typedFolder
        assert panel.fileNameField.text() == "finished.png"
    print("Export destinations: separate folder/name, native folder-only picker, extensions, undo/redo, cancellation and export passed")


if __name__ == "__main__":
    Main()
