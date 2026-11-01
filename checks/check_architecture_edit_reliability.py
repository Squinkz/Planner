"""Archive failures preserve committed edits, dirty tracking and recovery data."""
import json
import os
from pathlib import Path
import sqlite3
import sys
from threading import get_ident
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall
from planner_app.activity_records import ActivityEncoding, DecodeActivityLog


def Main():
    with ExampleWindow() as (main, folder):
        v, log = main.viewport, main.activityLog
        wall = Wall(QtCore.QPointF(), QtCore.QPointF(4000, 0), 200)
        InstallScene(main, [wall])
        main.MarkProjectClean()
        log.Clear()
        log.entries.entryLimit = 2
        log.Add("Notice", "Preserved first entry")
        log.Add("Notice", "Preserved second entry")
        previous = list(log.entries)
        notifications = []
        v.sceneChanged.connect(lambda: notifications.append(v.sceneRevision))
        with patch("planner_app.activity_storage.tempfile.TemporaryDirectory", side_effect = OSError("archive disk full")), \
                patch("planner_app.activity_log.warnings.warn") as warning:
            before = v.CaptureState()
            wall.width = 350
            v.RecordEdit(before)
            assert notifications and len(v.undoHistory) == 1
            main.RefreshProjectDirty()
            assert main.projectDirty and main.projectSceneData["objects"][0]["width"] == 350
            assert list(log.entries) == previous and len(log.entries.cache) == 2
            assert log.Add("Notice", "Cannot spill another row") is None
            assert warning.call_count == 1, "Storage failures recursively/repeatedly reported themselves"
            v.Undo()
            assert wall.width == 200 and len(v.redoHistory) == 1
            v.Redo()
            assert wall.width == 350 and len(v.undoHistory) == 1
        assert main.WriteSession(wait = True)
        recovered = json.loads(main.sessionPath.read_bytes())
        assert recovered["project"]["scene"]["objects"][0]["width"] == 350
        assert log.Add("Notice", "Archive recovered") is not None
        assert log.entries.connection is not None and list(log.entries)[:2] == previous
        archived = list(log.entries)
        connection = log.entries.connection
        dirty = next(iter(log.entries.cache.values()))[0]
        previousDetails = dirty["details"]
        dirty["details"] = "Dirty row must be written before eviction"

        class UnwritableArchive:
            def execute(self, statement, *arguments):
                if statement.startswith("INSERT"):
                    raise sqlite3.OperationalError("SQLite disk full")
                return connection.execute(statement, *arguments)

        with patch.object(log.entries, "connection", UnwritableArchive()), \
                patch("planner_app.activity_log.warnings.warn"):
            before = v.CaptureState()
            wall.width = 360
            v.RecordEdit(before)
            main.RefreshProjectDirty()
            assert main.projectSceneData["objects"][0]["width"] == 360
            assert len(log.entries) == len(archived) and len(log.entries.cache) <= 2
        dirty["details"] = previousDetails
        assert list(log.entries) == archived

        # Even a programming error in an observer cannot hide an applied edit.
        with patch.object(log, "SceneEdited", side_effect = RuntimeError("observer failure")):
            before = v.CaptureState()
            wall.width = 375
            count = len(notifications)
            try:
                v.RecordEdit(before)
            except RuntimeError:
                pass
            else:
                raise AssertionError("An unexpected observer error was hidden")
            assert len(notifications) == count + 1
        main.RefreshProjectDirty()
        assert main.projectSceneData["objects"][0]["width"] == 375

        with patch.object(log, "Encode", side_effect = sqlite3.OperationalError("archive read failed")), \
                patch.object(main, "ShowAppMessage") as message, \
                patch("planner_app.ui.session.warnings.warn"):
            assert not main.SaveProject(folder / "failed.plan")
            assert message.call_count == 1 and not (folder / "failed.plan").exists()
            assert not main.WriteSession(wait = True)
            assert "archive read failed" in main.sessionError
        assert main.SaveProject(folder / "preserved.plan")
        assert main.WriteSession(wait = True)
        log.Add("Notice", "Frozen checkpoint boundary")
        snapshot = log.Encode(deferred = True)
        expectedEntries = list(log.entries)
        assert snapshot.record is None
        log.Add("Notice", "Added while the checkpoint is pending")
        encodedOn = []
        encode = ActivityEncoding.Encode

        def Encode(encoding):
            encodedOn.append(get_ident())
            return encode(encoding)

        with patch.object(ActivityEncoding, "Encode", Encode):
            assert main.WriteSession()
            assert main.sessionFuture.result(timeout = 10) is None
        assert encodedOn and all(thread != get_ident() for thread in encodedOn)
        assert DecodeActivityLog(snapshot.Encode())["entries"] == expectedEntries
        assert len(DecodeActivityLog(json.loads(main.sessionPath.read_bytes())["project"]["activityLog"])["entries"]) == len(expectedEntries) + 1
    print("PASS: activity storage failure isolation, bounded rollback, dirty state, undo/redo and recovery")


if __name__ == "__main__":
    Main()
