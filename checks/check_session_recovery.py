"""Exit/relaunch, unsaved crash checkpoints, UI state and recovery failure safety."""
import json
import os
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow, Wall, Stair, Window
from furnishings import Furnishing
import planner_app.ui.projects as projects
from planner_app.ui.session import WriteSessionFile


def Main():
    app = QtWidgets.QApplication([])
    if "--crash" in sys.argv:
        main = MainWindow()
        v = main.viewport
        before = v.CaptureState()
        v.walls[0].width = 180
        v.RecordEdit(before)
        # Abrupt termination after a background checkpoint, without closeEvent.
        main.WriteSession()
        main.sessionFuture.result(timeout = 5)
        os._exit(0)
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "PLANNER_SESSION_PATH": str(Path(directory) / "recovery.json")}):
        folder = Path(directory)
        main = MainWindow()
        assert not main.sessionRestored
        main.resize(760, 700)
        main.show()
        app.processEvents()
        v = main.viewport
        point = QtCore.QPointF
        wall = Wall(point(-1000, -1000), point(1000, -1000), 120)
        stair = Stair(point(-1000, 0), point(-1000, 1000), 600)
        desk = Furnishing(v.furnishingDefinitions["desk"], point(1200, 1000))
        before = v.CaptureState()
        v.walls, v.windows, v.furnishings = [wall, stair], [Window(wall, .25, .75)], [desk]
        v.RecordEdit(before)
        v.SetSelection([(wall, None), (stair, None)])
        v.GroupSelection()
        main.groupModeButton.setChecked(False)
        v.SetSelection([(stair, None)])
        v.HideSelection()
        main.snapOptions["alignment"].setChecked(False)
        main.snapOptions["corners"].setChecked(False)
        main.visibilityItems["Windows"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        assert main.SaveProject(folder / "Saved.plan")
        savedBytes = main.projectPath.read_bytes()
        before = v.CaptureState()
        wall.width = 240
        desk.angle = 25
        v.RecordEdit(before)
        v.SetSelection([(desk, None)])
        v.furnishingRotationObject = desk
        v.zoom, v.panOffset = 1.8, point(34, -78)
        main.sidebarTabs.setCurrentIndex(1)
        main.visibilityItems["Walls"].setExpanded(False)
        main.mainSplitter.setSizes([900, 400])
        main.sidebarContentSplitter.setSizes([350, 450])
        app.processEvents()
        expected = main.BuildProjectData()
        ui = main.SessionUiState()
        # Closing a dirty project must never ask a save question or alter its file.
        with patch.object(MainWindow, "ShowAppMessage", side_effect = AssertionError("Unexpected exit prompt")):
            assert main.close()
        assert (folder / "Saved.plan").read_bytes() == savedBytes
        restored = MainWindow()
        restored.show()
        app.processEvents()
        assert restored.sessionRestored and restored.BuildProjectData() == expected
        assert restored.viewport.vertexSnapEnabled and not restored.viewport.cornerSnapEnabled
        assert restored.windowTitle() == "Saved* - Planner" and restored.viewport.undoHistory
        assert restored.sidebarTabs.currentIndex() == 1
        assert restored.SessionUiState()["selection"] == ui["selection"]
        assert restored.SessionUiState()["rotationObject"] == ui["rotationObject"]
        assert not restored.visibilityItems["Walls"].isExpanded()
        assert restored.mainSplitter.sizes() == ui["mainSplitter"]
        assert restored.sidebarContentSplitter.sizes() == ui["propertiesSplitter"]
        # Polls and camera/UI edits must reuse the scene cache, not encode geometry.
        with patch.object(projects, "EncodeScene", wraps = projects.EncodeScene) as encode:
            restored.viewport.panOffset += point(10, 0)
            restored.sidebarTabs.setCurrentIndex(2)
            restored.WriteSession(wait = True)
            assert encode.call_count == 0
        # A committed edit must be recovered before application exit too.
        before = restored.viewport.CaptureState()
        restored.viewport.walls[0].width = 120
        restored.viewport.RecordEdit(before)
        for index in range(100):
            app.processEvents()
            # The polling timer can consume a completed future before this check sees it.
            # Verify the persisted edit, rather than the worker's transient bookkeeping.
            if restored.sessionFuture is None or restored.sessionFuture.done():
                checkpoint = json.loads(restored.sessionPath.read_text())
                if checkpoint["project"]["scene"]["objects"][0]["width"] == 120:
                    break
            QtTest.QTest.qWait(50)
        assert restored.sessionError is None
        assert json.loads(restored.sessionPath.read_text())["project"]["scene"]["objects"][0]["width"] == 120
        restored.close()
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--crash"],
                               capture_output = True, text = True, timeout = 15)
        assert child.returncode == 0, child.stderr
        recovered = MainWindow()
        recovered.show()
        app.processEvents()
        assert recovered.viewport.walls[0].width == 180 and recovered.projectDirty
        # Saving the recovered canvas establishes a clean baseline for relaunch.
        assert recovered.SaveProject()
        recovered.close()
        clean = MainWindow()
        clean.show()
        app.processEvents()
        assert clean.sessionRestored and not clean.projectDirty and clean.windowTitle() == "Saved - Planner"
        # Unsaved New Project has no filename, but still restores with its dirty star.
        assert clean.NewProject()
        # This commit check types 20 cm; keep it independent of adaptive units.
        clean.viewport.unitsMode = "Centimeters"
        before = clean.viewport.CaptureState()
        clean.viewport.walls.append(Wall(point(0, 0), point(1000, 0)))
        clean.viewport.RecordEdit(before)
        clean.viewport.SetSelection([(clean.viewport.walls[0], None)])
        field = clean.propertyFields["width"]
        field.setFocus()
        field.lineEdit().selectAll()
        QtTest.QTest.keyClicks(field.lineEdit(), "20")
        assert clean.viewport.walls[0].width == 240
        clean.close()
        unsaved = MainWindow()
        assert unsaved.sessionRestored and unsaved.projectPath is None and unsaved.windowTitle() == "New Project* - Planner"
        assert unsaved.viewport.walls[0].width == 200
        unsaved.close()
        # Failed atomic replacement leaves the previous checkpoint untouched.
        path = folder / "recovery.json"
        previous = path.read_bytes()
        assert WriteSessionFile(path, {"invalid": float("nan")}) is not None
        assert path.read_bytes() == previous
        path.write_text('{"format": "broken"}')
        backup = json.loads(path.with_name(path.name + ".bak").read_text())
        with warnings.catch_warnings(record = True) as caught:
            blank = MainWindow()
        assert caught and blank.sessionRestored
        assert blank.BuildProjectData()["scene"] == backup["project"]["scene"]
        failed = list(path.parent.glob(path.name + ".failed-*"))
        assert failed and failed[-1].read_text() == '{"format": "broken"}'
        blank.close()
        print("PASS: no exit prompts; dirty/clean/unsaved recovery, UI/camera, background crash recovery, cache reuse and atomic failure safety.")


if __name__ == "__main__":
    Main()
