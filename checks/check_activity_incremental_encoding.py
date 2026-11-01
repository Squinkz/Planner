"""Complete activity persistence reuses archived compression and observes edits."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from planner_app.activity_storage import ActivityEntries
from planner_app.activity_records import EncodeActivityLog, DecodeActivityLog


def Main():
    entries = ActivityEntries()
    entries.entryLimit = 4
    expected = []
    try:
        for index in range(2000):
            entry = dict(id = index + 1, time = None, kind = "Notice", summary = f"Entry {index} é 家",
                         details = "Complete archived description " * 5, objects = [], anchor = None)
            entries.append(entry)
            expected.append(dict(entry))
        data = dict(entries = entries, undo = [], redo = [], issues = {}, gridStep = 100)
        initial = EncodeActivityLog(data)
        assert DecodeActivityLog(initial)["entries"] == expected
        prefix = entries.encodingPrefix
        count = prefix[0]
        visited = []
        original = entries.IterFrom

        def Rows(start):
            for row in original(start):
                visited.append(row["id"])
                yield row

        with patch.object(entries, "IterFrom", side_effect = Rows):
            entry = dict(expected[-1], id = 2001, summary = "Appended after checkpoint")
            entries.append(entry)
            expected.append(dict(entry))
            nextRecord = EncodeActivityLog(data)
        assert len(visited) <= 4 and entries.encodingPrefix is prefix
        assert prefix[0] == count + 1
        assert DecodeActivityLog(nextRecord)["entries"] == expected
        assert EncodeActivityLog(data) == nextRecord, "Camera-only checkpoints changed identical activity data"

        # Coalescing the recent entry updates the tail without losing the prefix.
        entries[-1]["details"] = "Coalesced mutable tail"
        expected[-1]["details"] = "Coalesced mutable tail"
        assert DecodeActivityLog(EncodeActivityLog(data))["entries"] == expected
        assert entries.encodingPrefix is prefix

        # Browsing archived rows neither rewrites them nor rebuilds compression.
        statements = []
        entries.connection.set_trace_callback(statements.append)
        borrowed = entries[3]
        visited.clear()
        with patch.object(entries, "IterFrom", side_effect = Rows):
            assert DecodeActivityLog(EncodeActivityLog(data))["entries"] == expected
        entries.connection.set_trace_callback(None)
        assert entries.encodingPrefix is prefix and len(visited) <= 4
        assert not any(statement.startswith("INSERT") for statement in statements)
        borrowed["details"] = "Corrected cached archive row"
        expected[3]["details"] = borrowed["details"]
        assert DecodeActivityLog(EncodeActivityLog(data))["entries"] == expected
        assert entries.encodingPrefix is not prefix

        # An old borrowed row can also be changed after eviction, then updated.
        borrowed = entries[4]
        for index in range(100, 110):
            entries[index]
        borrowed["details"] = "Corrected archived entry"
        entries.Update(borrowed)
        expected[4]["details"] = borrowed["details"]
        assert DecodeActivityLog(EncodeActivityLog(data))["entries"] == expected
        assert entries.cachedPayloads.keys() == entries.cache.keys()

        # The same size guard applies when cached compression already exists.
        with patch("planner_app.activity_records.activityByteLimit", 64):
            try:
                EncodeActivityLog(data)
            except ValueError:
                pass
            else:
                raise AssertionError("A cached prefix bypassed the activity size limit")
        entries.Reset(expected[:2])
        data["issues"] = {"1:test:False": dict(object = 1, label = "Updated issue", fingerprint = None)}
        assert DecodeActivityLog(EncodeActivityLog(data))["entries"] == expected[:2]
        assert DecodeActivityLog(EncodeActivityLog(data))["issues"] == data["issues"]
        # Archived bytes bypass reserialization when reused as a prefix, so
        # storage itself must reject nonfinite values before they reach it.
        count = len(entries)
        try:
            entries.append(dict(expected[0], id = 9999, objects = [float("nan")]))
        except ValueError:
            pass
        else:
            raise AssertionError("Nonfinite values entered the reusable archive")
        assert len(entries) == count
        # A valid incoming row can encounter a previously borrowed row that
        # was made unserializable. Failed eviction must not leave a ghost row
        # outside the sequence's count or persist it on the next iteration.
        entries.entryLimit = 1
        retired = entries[0]
        details = retired["details"]
        retired["details"] = float("nan")
        try:
            entries.append(dict(expected[0], id = 10000))
        except ValueError:
            pass
        else:
            raise AssertionError("Unserializable retired row was accepted")
        assert len(entries) == count and all(index < count for index in entries.cache)
        assert entries.cachedPayloads.keys() == entries.cache.keys()
        retired["details"] = details
        assert list(entries) == expected[:2]
    finally:
        entries.Close()
    print("PASS: complete incremental encoding, bounded tail work, mutation invalidation and size limits")


if __name__ == "__main__":
    Main()
