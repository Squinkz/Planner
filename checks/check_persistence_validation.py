"""Malformed imports/recovery and UTF-8 checkpoint limits preserve valid state."""
import copy
import json
import os
import sys
import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall
from planner_app.project_codec import DecodeProject, ValidateEditorUi, ReadProjectBytes
import planner_app.ui.session as session


def Main():
    app = QtWidgets.QApplication([])
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "PLANNER_SESSION_PATH": str(Path(directory) / "session.json"),
            "PLANNER_STARTUP_PATH": str(Path(directory) / "startup.plan")}):
        folder = Path(directory)
        main = MainWindow()
        main.sessionPollTimer.stop()
        main.sessionTimer.stop()
        main.projectTimer.stop()
        v = main.viewport
        before = v.CaptureState()
        v.walls = [Wall(QtCore.QPointF(0, 0), QtCore.QPointF(1000, 0), 120)]
        v.RecordEdit(before)
        main.RefreshProjectDirty()
        main.projectTimer.stop()
        main.sessionTimer.stop()
        assert main.WriteSession(wait = True)
        validBytes = main.sessionPath.read_bytes()
        valid = json.loads(validBytes)
        project = main.BuildProjectData()

        # Imports validate outer containers before dereferencing them, and never
        # replace the current scene or history when validation fails.
        for field, value in (("version", 99), ("scene", []), ("scene", {"objects": [[]]})):
            malformed = copy.deepcopy(project)
            malformed[field] = value
            try:
                DecodeProject(malformed, v.furnishingDefinitions)
            except ValueError:
                pass
            else:
                raise AssertionError(f"Invalid {field} was accepted.")
            path = folder / "malformed.plan"
            path.write_text(json.dumps(malformed), encoding = "utf-8")
            with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Discard) as message, \
                 patch.object(main, "ApplyProject", wraps = main.ApplyProject) as apply, \
                 patch.object(main, "ShowGeometryIssue", return_value = None) as geometry, \
                 patch("planner_app.ui.projects.ReadProjectBytes", wraps = ReadProjectBytes) as read:
                assert not main.OpenProject(path)
                read.assert_called_once_with(path.resolve())
                if geometry.called:
                    assert field == "scene" and isinstance(value, dict)
                else:
                    assert any(call.args[0] == "Cannot Open Project" for call in message.call_args_list)
                assert apply.call_count == 2  # Empty canvas, followed by actual rollback.
            assert main.BuildProjectData() == project

        malformed = {**project, "history": {"undo": [[[], {}]], "redo": []}}
        decoded = DecodeProject(malformed, v.furnishingDefinitions)
        assert decoded[5]["history"] == {"undo": [], "redo": []}
        assert main.BuildProjectData() == project

        for field, value in (("size", ["bad", 900]), ("size", [True, 900]), ("size", [900]),
                             ("geometry", "not base64!"), ("mainSplitter", [1]),
                             ("propertiesSplitter", [1, 2, 3]), ("propertiesRestoreHeight", -1)):
            for recovery in (False, True):
                ui = copy.deepcopy(valid["ui"] if recovery else project["ui"])
                ui[field] = value
                if not recovery and field in ("size", "geometry"):
                    ValidateEditorUi(ui, recovery = False, tabCount = main.sidebarTabs.count())
                    continue  # Legacy project window placement is ignored.
                try:
                    ValidateEditorUi(ui, recovery = recovery, tabCount = main.sidebarTabs.count())
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"Invalid {field} was accepted for recovery={recovery}.")

        # The failed primary must not apply its different scene before fallback.
        # The original bytes are preserved, while the backup restores correctly.
        for field, value in (("size", ["bad", 900]), ("geometry", "not base64!"),
                             ("mainSplitter", [1])):
            path = folder / (field + ".json")
            malformed = copy.deepcopy(valid)
            malformed["project"]["scene"]["objects"][0]["width"] = 900
            malformed["ui"][field] = value
            failedBytes = json.dumps(malformed).encode("utf-8")
            path.write_bytes(failedBytes)
            path.with_name(path.name + ".bak").write_bytes(validBytes)
            main.sessionPath = path
            main.sessionRestored = False
            with warnings.catch_warnings(record = True) as caught, patch.object(main, "ApplyProject", wraps = main.ApplyProject) as apply:
                main.RestoreSession()
            assert caught and main.sessionRestored and apply.call_count == 1
            assert v.walls[0].width == 120
            assert main.BuildProjectData()["scene"] == valid["project"]["scene"]
            preserved = list(folder.glob(path.name + ".failed-*"))
            assert len(preserved) == 1 and preserved[0].read_bytes() == failedBytes
            app.processEvents()

        # Without a backup, a bad checkpoint cannot partially replace a live scene.
        path = folder / "no-backup.json"
        path.write_bytes(failedBytes)
        main.sessionPath = path
        main.sessionRestored = False
        with warnings.catch_warnings(record = True), patch.object(main, "ApplyProject") as apply:
            main.RestoreSession()
        assert apply.call_count == 0 and v.walls[0].width == 120

        # Test byte boundaries with actual UTF-8 serialization, without allocating
        # a 64 MB fixture. Oversized writes must preserve primary AND backup.
        path = folder / "limit.json"
        data = copy.deepcopy(valid)
        data["padding"] = "測" * 40
        payloadBytes = json.dumps(data, ensure_ascii = False, separators = (",", ":"), allow_nan = False).encode("utf-8")
        with patch.object(session, "projectFileLimit", len(payloadBytes)):
            assert session.WriteSessionFile(path, data) is None
            main.sessionPath = path
            main.sessionRestored = False
            with patch.object(main, "ApplyProject", wraps = main.ApplyProject) as apply:
                main.RestoreSession()
            assert main.sessionRestored and apply.call_count == 1
            app.processEvents()
        backupPath = path.with_name(path.name + ".bak")
        backupPath.write_bytes(validBytes)
        with patch.object(session, "projectFileLimit", len(payloadBytes) - 1):
            assert session.WriteSessionFile(path, data) is not None
        assert path.read_bytes() == payloadBytes and backupPath.read_bytes() == validBytes
        missingPath = folder / "not-created" / "limit.json"
        with patch.object(session, "projectFileLimit", len(payloadBytes) - 1):
            assert session.WriteSessionFile(missingPath, data) is not None
        assert not missingPath.parent.exists()

        # A real close must remain rejected, with the specific reason displayed,
        # instead of accepting a checkpoint that the next launch cannot read.
        main.sessionPath = path
        main.sessionSignature = None
        event = QtGui.QCloseEvent()
        with patch.object(session, "projectFileLimit", 1), warnings.catch_warnings(record = True), patch.object(main, "ShowAppMessage") as message:
            main.closeEvent(event)
        assert not event.isAccepted()
        assert "64 MB" in message.call_args.kwargs["informativeText"]
        assert path.read_bytes() == payloadBytes and backupPath.read_bytes() == validBytes
        main.sessionPollTimer.stop()
        main.sessionSignature = None
        assert main.WriteSession(wait = True)
        assert main.close()
        print("PASS: malformed imports preserve state; recovery validates before application and uses backups; UTF-8 limits preserve checkpoints and reject unsafe close.")


if __name__ == "__main__":
    Main()
