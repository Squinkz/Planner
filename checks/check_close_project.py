"""Close clears project content and overrides without loading the startup template."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, Door, Label
from furnishings import Furnishing
from planner_app.project_codec import DecodeProject
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.theme import ApplyApplicationTheme


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    ApplyApplicationTheme(app)
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "PLANNER_SESSION_PATH": str(Path(directory) / "session.json"),
            "PLANNER_STARTUP_PATH": str(Path(directory) / "startup.plan")}):
        main = MainWindow()
        main.show()
        app.processEvents()
        v = main.viewport
        point = QtCore.QPointF
        before = v.CaptureState()
        wall = Wall(point(-2000, 0), point(2000, 0))
        v.walls = [wall]
        v.windows = [Door(wall, .2, .4)]
        desk = Furnishing(v.furnishingDefinitions["desk"], point(0, 2000))
        v.furnishings = [desk]
        v.labels = [Label(point(0, 4000), "Test")]
        v.objectGroups = [(wall, desk)]
        v.hiddenObjects, v.hiddenObjectIds = [desk], {id(desk)}
        v.RecordEdit(before)
        template = main.BuildProjectData(includeHistory = False)
        DecodeProject(template, v.furnishingDefinitions)
        main.startupPath.write_text(json.dumps(template), encoding = "utf-8")
        main.snapOptions["grid"].setChecked(False)
        main.SetTransformOrientation(True)
        settings = main.ProjectSettings()
        imagePath = Path(directory) / "reference.png"
        image = QtGui.QImage(100, 80, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor("red"))
        assert image.save(str(imagePath)) and main.referenceImage.Load(imagePath)
        main.referenceImage.Hide()
        main.visibilityItems["Walls"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        v.showMeasurements = False
        v.measurementVisibility = dict.fromkeys(v.measurementVisibility, False)
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        main.exportPanel.SetOverride("border", "Plain")
        main.exportPanel.SetOverride("canvasColor", "#335577")
        main.exportPanel.SetOverride("scale", 250)
        main.exportPanel.folderField.setText(directory)
        main.exportPanel.folderField.editingFinished.emit()
        beforeClose = main.BuildProjectData()
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Cancel):
            assert not main.CloseProject()
        assert main.BuildProjectData() == beforeClose
        with patch.object(main, "LoadStartupProject", side_effect = AssertionError("Close loaded startup")), \
                patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Discard):
            assert main.CloseProject()
        app.processEvents()
        assert not (v.walls or v.windows or v.furnishings or v.labels or v.objectGroups or v.hiddenObjects or v.hiddenObjectIds)
        assert not v.SelectionEntries() and not v.undoHistory and not v.redoHistory
        assert main.projectPath is None and not main.projectDirty
        assert main.referenceImage.state is None and not main.referenceImage.active and main.referenceImage.image.isNull()
        assert all(v.visibility.values())
        assert v.measurementVisibility == main.defaultProjectData["settings"]["measurementVisibility"]
        assert not main.exportPanel.overrides
        assert main.exportPanel.exportFolder is None and "exportFolder" not in main.ProjectSettings()
        assert not main.exportPanel.exportUndoHistory and not main.exportPanel.exportRedoHistory
        assert "referenceImage" not in main.ProjectSettings() and "exportSettings" not in main.ProjectSettings()
        assert main.ProjectSettings()["snap"] == settings["snap"]
        assert main.ProjectSettings()["localTransforms"] == settings["localTransforms"]
        assert main.isVisible() and main.sidebarTabs.currentWidget() is main.exportPanel
        # New Project still restores the startup scene, and Close stays empty after relaunch.
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Discard) as notices:
            assert main.NewProject() and v.walls and v.windows and v.furnishings and v.labels, notices.call_args_list
        assert main.CloseProject() and main.close()
        restored = MainWindow()
        assert restored.sessionRestored and not restored.viewport.walls and restored.referenceImage.state is None
        restored.close()
    print("PASS: Close cancellation, empty scene, visibility/reference/export reset, retained editing settings, startup isolation and session restore.")


if __name__ == "__main__":
    Main()
