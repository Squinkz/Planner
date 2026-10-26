"""Startup templates, project UI/shape, and durable undo/redo across object types."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, Pillar, Railing, Counter, Stair, Arrow, MeasurementGuide, Door, Label
from planner_app.models import Furnishing
from planner_app.project_codec import EncodeScene, DecodeProject
from planner_app.paths import appDirectory
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "PLANNER_STARTUP_PATH": str(Path(directory) / "startup.plan"),
            "PLANNER_SESSION_PATH": str(Path(directory) / "session.json")}):
        main = MainWindow()
        if os.environ.get("PLANNER_EXPORT_FACTORY_STARTUP") == "1":
            factoryStartup = json.loads(json.dumps(main.defaultProjectData))
            (appDirectory / "startup.plan").write_text(json.dumps(factoryStartup, indent = 2), encoding = "utf-8")
        main.show()
        app.processEvents()
        v, point = main.viewport, QtCore.QPointF
        factory = main.defaultProjectData
        assert factory["settings"]["measurementVisibility"] == {
            "walls": True, "stairs": False, "counters": False, "railings": False}
        assert not factory["scene"]["objects"] and "history" not in factory
        startup = main.startupPath
        before = v.CaptureState()
        for index, cls in enumerate((Wall, Pillar, Railing, Counter, Stair, Arrow, MeasurementGuide)):
            x = index * 5000
            obj = cls(point(x, 0), point(x + 1000, 0))
            if isinstance(obj, (Railing, Stair)):
                obj.autosize = False
            v.walls.append(obj)
        v.windows = [Door(v.walls[0], .1, .4)]
        v.labels = [Label(point(0, 3000), "First label")]
        v.furnishings = [Furnishing(v.furnishingDefinitions["desk"], point(0, 5000))]
        v.RecordEdit(before)
        initial = EncodeScene(v)
        before = v.CaptureState()
        v.walls[1].material = "Brick"
        v.labels[0].text = "Changed label"
        v.walls[-2].tipSize = 123
        v.windows[0].hingeAtSecond = not v.windows[0].hingeAtSecond
        v.RecordEdit(before)
        changed = EncodeScene(v)
        v.Undo()
        main.SetWallToolShape(2)
        main.mainSplitter.setSizes([800, 420])
        main.sidebarContentSplitter.setSizes([500, 250])
        main.SetPropertiesCollapsed(True)
        main.sidebarTabs.setCurrentIndex(1)
        path = Path(directory) / "history.plan"
        assert main.SaveProject(path)
        savedUi = main.ProjectUiState()
        assert main.NewProject() and main.OpenProject(path)
        assert v.wallShape == "circle" and main.wallToolButtons["circle"].isChecked()
        assert main.propertiesCollapsed and main.propertiesRestoreHeight == savedUi["propertiesRestoreHeight"]
        assert main.mainSplitter.sizes() == savedUi["mainSplitter"]
        assert main.sidebarTabs.currentIndex() == 1 and not v.SelectionEntries()
        assert EncodeScene(v) == initial and len(v.undoHistory) == len(v.redoHistory) == 1
        v.Redo()
        assert EncodeScene(v) == changed
        v.Undo()
        assert EncodeScene(v) == initial
        v.Undo()
        assert not v.walls and not v.furnishings and not v.labels
        v.Redo()
        assert EncodeScene(v) == initial
        v.Redo()
        assert EncodeScene(v) == changed
        # Group membership and hidden state are included in historical scenes.
        before = v.CaptureState()
        v.objectGroups = [(v.walls[1], v.walls[2])]
        v.hiddenObjects = [v.walls[2]]
        v.hiddenObjectIds = {id(v.walls[2])}
        v.RecordEdit(before)
        grouped = EncodeScene(v)
        assert main.SaveProject(path) and main.OpenProject(path)
        assert EncodeScene(v) == grouped
        v.Undo()
        assert EncodeScene(v) == changed
        v.Redo()
        assert EncodeScene(v) == grouped
        v.Undo()
        # A deletion survives save/open/undo.
        v.SetSelection([(v.labels[0], None)])
        v.DeleteSelected()
        assert main.SaveProject(path) and main.OpenProject(path)
        v.Undo()
        assert EncodeScene(v) == changed
        originalPath, originalDirty = main.projectPath, main.projectDirty
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Cancel):
            assert not main.SaveStartupFile() and not startup.exists()
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Save):
            assert main.SaveStartupFile()
        assert main.projectPath == originalPath and main.projectDirty == originalDirty
        template = json.loads(startup.read_text(encoding = "utf-8"))
        savedStartupBytes = startup.read_bytes()
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Cancel):
            assert not main.SaveStartupFile() and startup.read_bytes() == savedStartupBytes
        assert template["scene"] == changed and "history" not in template
        assert set(template["ui"]) == {"mainSplitter", "propertiesSplitter", "propertiesCollapsed", "propertiesRestoreHeight", "exportSections"}
        assert main.NewProject() and EncodeScene(v) == changed
        assert main.projectPath is None and not main.projectDirty and not v.undoHistory and not v.redoHistory
        # Recovery wins over startup; without recovery, startup wins over factory.
        assert main.close()
        startup.write_text(json.dumps(factory), encoding = "utf-8")
        recovered = MainWindow()
        assert recovered.sessionRestored and EncodeScene(recovered.viewport) == changed
        recovered.close()
        Path(os.environ["PLANNER_SESSION_PATH"]).unlink()
        Path(os.environ["PLANNER_SESSION_PATH"] + ".bak").unlink(missing_ok = True)
        startup.write_text(json.dumps(template), encoding = "utf-8")
        fresh = MainWindow()
        assert not fresh.sessionRestored and EncodeScene(fresh.viewport) == changed
        startup.write_text("broken json", encoding = "utf-8")
        assert fresh.NewProject() and not fresh.viewport.walls
        startup.unlink()
        assert fresh.NewProject() and not fresh.viewport.walls
        maximizedStartup = json.loads(json.dumps(factory))
        maximizedStartup["ui"]["maximized"] = True
        startup.write_text(json.dumps(maximizedStartup), encoding = "utf-8")
        assert fresh.NewProject() and not fresh.isMaximized()
        # Invalid optional history is discarded without rejecting the project.
        bad = json.loads(path.read_text(encoding = "utf-8"))
        bad["history"]["undo"] = ["bad"]
        decoded = DecodeProject(bad, v.furnishingDefinitions)
        assert decoded[5]["history"] == {"undo": [], "redo": []}
        fresh.close()
        main.ShowHeaderMenu("File")
        app.processEvents()
        main.fileMenu.grab().save(str(Path(__file__).resolve().parents[1] / "screenshots" / "startup-file-menu.png"))
        main.fileMenu.hide()
        main.deleteLater()
        recovered.deleteLater()
        fresh.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    Main()
