"""Project round trips, dirty tracking, file actions and transactional failures."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Stair, Door, SlidingDoor, PocketDoor, OpenDoorway, Window, SilledWindow
from furnishings import Furnishing
from planner_app.project_codec import EncodeScene
import planner_app.ui.projects as projects
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    choice = [QtWidgets.QMessageBox.StandardButton.Discard]
    errors = []

    def AnswerMessage(title, text, kind = "info", **options):
        if kind == "error":
            errors.append(options.get("informativeText", text))
            return QtWidgets.QMessageBox.StandardButton.Ok
        return choice[0]

    with tempfile.TemporaryDirectory() as directory, \
         patch.object(MainWindow, "ShowAppMessage", side_effect = AnswerMessage):
        folder = Path(directory).resolve()
        path = folder / "Summer House.plan"
        main = MainWindow()
        main.show()
        app.processEvents()
        v = main.viewport
        assert v.unitsMode == "Millimeters"
        assert main.windowTitle() == "New Project - Planner" and not main.projectDirty
        assert not main.menuButtons["Revert"].isEnabled()
        assert not main.RevertProject()
        items = [None if action.isSeparator() else action.defaultWidget().accessibleName() for action in main.fileMenu.actions()]
        assert items[:9] == ["New Project", "Open Project", None, "Open Recent", None, "Revert", None, "Save Project", "Save Project as"]
        p = QtCore.QPointF
        wall = Wall(p(-3500, -1000), p(3500, -1000), 180, .8, 1.0, "Steel")
        stair = Stair(p(-1000, 0), p(-1000, 1500), 800, directionReversed = True)
        furnishing = Furnishing(v.furnishingDefinitions["desk"], p(1300, 800))
        furnishing.angle, furnishing.width = 33, 777
        types = (Door, SlidingDoor, PocketDoor, OpenDoorway, Window, SilledWindow)
        openings = [cls(wall, .03 + index * .15, .11 + index * .15) for index, cls in enumerate(types)]
        for opening in openings:
            for flag in ("hingeAtSecond", "swingsOutwards", "panelsFlipped"):
                if hasattr(opening, flag):
                    setattr(opening, flag, True)
        openings[-1].sillDepth = 91
        before = v.CaptureState()
        v.walls, v.windows, v.furnishings = [wall, stair], openings, [furnishing]
        v.RecordEdit(before)
        app.processEvents()
        assert main.windowTitle() == "New Project* - Planner"
        v.SetSelection([(wall, None), (stair, None), (furnishing, None)])
        assert v.GroupSelection()
        main.groupModeButton.setChecked(False)
        v.SetSelection([(furnishing, None), (openings[-1], None)])
        assert v.HideSelection()
        main.wallWidthSelector.slider.setValue(2)
        main.newWallMaterialField.setCurrentText("Metal")
        main.snapButton.setChecked(False)
        main.snapOptions["grid"].setChecked(False)
        main.snapOptions["midpoints"].setChecked(False)
        main.connectedOptions["vertices"].setChecked(False)
        main.connectedOptions["objects"].setChecked(True)
        main.visibilityItems["Windows"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        main.visibilityItems["Stairs"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        v.BeginOpeningMode("Door")
        v.CycleOpeningType(2)
        v.EndOpeningMode()
        v.BeginOpeningMode("Window")
        v.CycleOpeningType(1)
        v.EndOpeningMode()
        main.SetViewOption("showGrid")
        main.SetViewOption("showMeasurements")
        v.zoom, v.panOffset = 1.4, p(40, -60)
        assert main.SaveProjectAs(path)
        assert main.windowTitle() == "Summer House - Planner" and not main.projectDirty
        assert main.menuButtons["Revert"].isEnabled()
        saved = main.BuildProjectData()
        assert json.loads(path.read_text()) == saved
        # View/selection changes alone are not project edits.
        v.panOffset = p(80, -20)
        v.zoom = 2.3
        v.SetSelection([(wall, None)])
        app.processEvents()
        assert not main.projectDirty
        unchanged = main.BuildProjectData()
        with patch.object(main, "OpenProject") as opened:
            assert main.RevertProject()
            main.menuButtons["Revert"].click()
            opened.assert_not_called()
        assert main.BuildProjectData() == unchanged
        assert v.zoom == 2.3 and v.panOffset == p(80, -20)
        assert v.selection == [(wall, None)]
        assert main.NewProject() and not v.walls and not v.hiddenObjects and not v.objectGroups
        assert main.windowTitle() == "New Project - Planner"
        assert not main.menuButtons["Revert"].isEnabled()
        assert main.OpenProject(path)
        current = main.BuildProjectData()
        assert current == saved
        assert not main.projectDirty
        assert main.windowTitle() == "Summer House - Planner"
        assert len(v.undoHistory) == len(saved["history"]["undo"]) and len(v.redoHistory) == len(saved["history"]["redo"])
        savedWidth = v.walls[0].width
        before = v.CaptureState()
        v.walls[0].width += 10
        v.RecordEdit(before)
        choice[0] = QtWidgets.QMessageBox.StandardButton.Cancel
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName") as chooser:
            main.menuButtons["Revert"].click()
            assert v.walls[0].width == savedWidth + 10
            choice[0] = QtWidgets.QMessageBox.StandardButton.Discard
            main.menuButtons["Revert"].click()
            chooser.assert_not_called()
        assert v.walls[0].width == savedWidth and not main.projectDirty
        assert main.projectPath == path.resolve()
        wall = v.walls[0]
        # Undo to the saved content removes the star; redo restores it.
        before = v.CaptureState()
        wall.width += 20
        v.RecordEdit(before)
        app.processEvents()
        assert main.windowTitle() == "Summer House* - Planner"
        v.Undo()
        app.processEvents()
        assert not main.projectDirty
        v.Redo()
        app.processEvents()
        assert main.projectDirty
        v.Undo()
        app.processEvents()
        # Settings changes do not serialize the scene, and paint never does.
        with patch.object(projects, "EncodeScene", wraps = EncodeScene) as encode:
            main.newWallMaterialField.setCurrentText("Brick")
            app.processEvents()
            assert main.projectDirty and encode.call_count == 0
            main.newWallMaterialField.setCurrentText("Metal")
            app.processEvents()
            assert not main.projectDirty and encode.call_count == 0
            for index in range(3):
                v.grab()
                app.processEvents()
            assert encode.call_count == 0
        # Every saved setting becomes dirty and becomes clean when restored.
        buttons = [main.snapButton, main.snapOptions["vertices"], main.connectedOptions["objects"], main.groupModeButton]
        for button in buttons:
            old = button.isChecked()
            button.setChecked(not old)
            app.processEvents()
            assert main.projectDirty
            button.setChecked(old)
            app.processEvents()
            assert not main.projectDirty
        for mode in ("Door", "Window"):
            v.BeginOpeningMode(mode)
            v.CycleOpeningType(1)
            app.processEvents()
            assert main.projectDirty
            v.CycleOpeningType(-1)
            v.EndOpeningMode()
            app.processEvents()
            assert not main.projectDirty
        main.visibilityItems["World"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        app.processEvents()
        assert main.projectDirty
        main.visibilityItems["World"].setCheckState(0, QtCore.Qt.CheckState.Checked)
        app.processEvents()
        assert main.projectDirty
        # Re-enabling World now enables every branch rather than restoring preferences.
        for name in ("Windows", "Stairs"):
            main.visibilityItems[name].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        app.processEvents()
        assert not main.projectDirty
        # Temporary Alt inversion must never change the saved snapping choice.
        QtTest.QTest.keyPress(v, QtCore.Qt.Key.Key_Alt)
        app.processEvents()
        assert not main.projectDirty
        QtTest.QTest.keyRelease(v, QtCore.Qt.Key.Key_Alt)
        app.processEvents()
        assert not main.projectDirty
        # Invalid files cannot replace the current project or its dirty state.
        original = main.BuildProjectData()
        invalid = folder / "Broken.plan"
        for broken in ("not json", json.dumps({"format": "Planner Project", "version": 99}),
                       json.dumps({**saved, "scene": {**saved["scene"], "objects": [{"type": "Future Object"}]}})):
            invalid.write_text(broken)
            with patch.object(main, "ShowGeometryIssue", return_value = None):
                assert not main.OpenProject(invalid)
            assert main.BuildProjectData() == original and main.projectPath == path
        # Save failure preserves the old file/name and unsaved changes.
        main.newWallMaterialField.setCurrentText("Wood")
        app.processEvents()
        oldBytes = path.read_bytes()
        assert not main.SaveProjectAs(folder / "missing" / "Failure.plan")
        assert main.projectPath == path and path.read_bytes() == oldBytes and main.projectDirty
        choice[0] = QtWidgets.QMessageBox.StandardButton.Cancel
        assert not main.NewProject() and main.projectPath == path
        choice[0] = QtWidgets.QMessageBox.StandardButton.Save
        assert main.NewProject() and not main.projectDirty
        assert json.loads(path.read_text())["settings"]["wallMaterial"] == "Wood"
        assert main.OpenProject(path)
        assert main.SaveProjectAs(folder / "Winter House")
        assert main.windowTitle() == "Winter House - Planner"
        # Native file shortcuts and menu actions invoke real file operations.
        ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
        keyboardPath = folder / "Keyboard.plan"
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value = (str(keyboardPath), "")):
            QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_S, ctrl | QtCore.Qt.KeyboardModifier.ShiftModifier)
        assert main.projectPath == keyboardPath and keyboardPath.exists()
        main.newWallMaterialField.setCurrentText("Generic")
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_S, ctrl)
        assert not main.projectDirty and json.loads(keyboardPath.read_text())["settings"]["wallMaterial"] == "Generic"
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_N, ctrl)
        assert not v.walls and main.projectPath is None
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value = (str(path), "")):
            QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_O, ctrl)
        assert main.projectPath == path and len(v.windows) == 6
        # Ctrl+S must commit a value still being typed in a property editor.
        v.SetSelection([(v.walls[0], None)])
        field = main.propertyFields["width"]
        field.setFocus()
        field.lineEdit().selectAll()
        QtTest.QTest.keyClicks(field.lineEdit(), "150")
        assert v.walls[0].width == 180
        QtTest.QTest.keyClick(field.lineEdit(), QtCore.Qt.Key.Key_S, ctrl)
        assert v.walls[0].width == 150
        assert json.loads(path.read_text())["scene"]["objects"][0]["width"] == 150
        assert not main.projectDirty
        main.ShowHeaderMenu("File")
        main.menuButtons["Close Project"].click()
        assert not v.walls and main.projectPath is None and main.isVisible()
        main.newWallMaterialField.setCurrentText("Brick")
        choice[0] = QtWidgets.QMessageBox.StandardButton.Save
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value = ("", "")):
            assert not main.NewProject()
        choice[0] = QtWidgets.QMessageBox.StandardButton.Discard
        assert main.CloseProject() and not main.projectDirty
        assert main.close()
        assert len(errors) == 3  # Cancelling geometry recovery is not an error popup.
        print("PASS: all object/settings round trips, names/dirty/undo, cached tracking, menus/shortcuts, prompts and transactional failures.")


if __name__ == "__main__":
    Main()
