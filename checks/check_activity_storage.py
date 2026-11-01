"""Bound decoded activity memory without losing descriptions or journal links."""
import gc
import os
from pathlib import Path
import sys
import weakref
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from planner_app.activity_storage import ActivityEntries
from planner_app.activity_records import EncodeActivityLog, DecodeActivityLog
from planner_app.models import Wall
from fixtures.parity_examples import ExampleWindow


def Main():
    class Entry(dict):
        pass

    entries = ActivityEntries()
    entries.entryLimit = 4
    entries.byteLimit = 16384
    expected, references = [], []
    for index in range(3000):
        entry = Entry(id = index + 1, time = None, kind = "Edit", summary = f"Edit {index}",
                      details = "Long description " * 30, objects = [], anchor = None)
        entries.append(entry)
        entry["anchor"] = dict(scope = "Scene", edit = index + 1, side = "after")
        expected.append(dict(entry))
        references.append(weakref.ref(entry))
    del entry
    gc.collect()
    assert sum(reference() is not None for reference in references) == len(entries.cache)
    assert len(entries) == 3000 and len(entries.cache) <= 4 and entries.cacheBytes <= entries.byteLimit
    assert entries == expected and expected == entries
    assert entries[:7] == expected[:7] and entries[-1] == expected[-1]
    assert list(reversed(entries)) == expected[::-1]
    assert entries.Find(None) is None and entries.Find(-1) is None and entries.Find(3) == expected[2]
    entries[2]["details"] = "Updated archived row"
    expected[2]["details"] = "Updated archived row"
    for index in range(10, 20):
        entries[index]
    assert entries[2]["details"] == expected[2]["details"]
    borrowed = entries[3]
    for index in range(20, 30):
        entries[index]
    borrowed["details"] = "Changed after a synchronous observer evicted the row"
    entries.Update(borrowed)
    expected[3]["details"] = borrowed["details"]
    record = EncodeActivityLog(dict(entries = entries, undo = [], redo = [], issues = {}, gridStep = 100))
    assert DecodeActivityLog(record)["entries"] == expected
    archive = Path(entries.connection.execute("PRAGMA database_list").fetchone()[2]).parent
    entries.Reset(expected[:2])
    assert not archive.exists() and entries == expected[:2] and entries.connection is None
    entries.Close()

    # The encoder must stop at the byte limit without materializing all rows.
    visited = []
    def Rows():
        for entry in expected:
            visited.append(entry["id"])
            yield entry
    with patch("planner_app.activity_records.activityByteLimit", 1024):
        try:
            EncodeActivityLog(dict(entries = Rows(), undo = [], redo = [], issues = {}, gridStep = 100))
        except ValueError as error:
            assert "64 MiB" in str(error)
        else:
            raise AssertionError("Oversized activity was accepted")
    assert len(visited) < 10

    with ExampleWindow() as (main, folder):
        log, v = main.activityLog, main.viewport
        log.entries.entryLimit = 2
        log.entries.byteLimit = 4096
        before = v.CaptureState()
        wall = Wall(QtCore.QPointF(), QtCore.QPointF(2000, 0), 200)
        v.walls.append(wall)
        v.RecordEdit(before)
        created = dict(log.entries[-1])
        for index in range(12):
            before = v.CaptureState()
            wall.firstVertex += QtCore.QPointF(10, 0)
            wall.secondVertex += QtCore.QPointF(10, 0)
            v.RecordEdit(before, coalesceKey = "recent" if index >= 10 else None)
        assert log.entries.connection is not None and len(log.entries.cache) <= 2
        assert log.Restore(created) and wall.firstVertex == QtCore.QPointF()
        saved = main.BuildProjectData()
        decoded = DecodeActivityLog(saved["activityLog"])
        assert decoded["entries"] == log.entries
        assert main.SaveProject(folder / "archived.plan") and main.OpenProject(folder / "archived.plan")
        assert log.entries == decoded["entries"]
        assert log.Position(log.entries[0]) is not None
        assert main.WriteSession(wait = True)
        previous = main.sessionPath.read_bytes()
        with patch("planner_app.activity_records.activityByteLimit", 128), \
                patch("planner_app.ui.session.warnings.warn") as warning:
            log.Add("Notice", "Another edit")
            assert not main.WriteSession(wait = True)
            assert warning.call_count == 1
            assert not main.WriteSession(wait = True) and warning.call_count == 1
            assert "activity log exceeds" in main.sessionError
            assert main.sessionPath.read_bytes() == previous
        assert main.WriteSession(wait = True)
        archive = Path(log.entries.connection.execute("PRAGMA database_list").fetchone()[2]).parent
        log.Clear()
        assert not archive.exists() and not log.entries
        for index in range(5):
            log.Add("Notice", f"Closing entry {index}")
        archive = Path(log.entries.connection.execute("PRAGMA database_list").fetchone()[2]).parent
    assert not archive.exists(), "Destroying the window left its activity archive open"
    print("PASS: bounded decoded activity, complete streaming persistence, live history, size failures and archive cleanup")


if __name__ == "__main__":
    Main()
