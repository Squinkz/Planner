"""Bounded pan checkpoints, immutable chunk reuse and recovered latest camera."""
import copy
import json
import os
import sys
import warnings
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow, Wall
from planner_app.ui import session


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.sessionPollTimer.stop()
    main.sessionTimer.stop()
    v = main.viewport
    before = v.CaptureState()
    v.walls = [Wall(QtCore.QPointF(), QtCore.QPointF(1000, 0))]
    v.RecordEdit(before)
    assert main.WriteSession(wait = True)
    initial = main.sessionPath.read_bytes()
    scene = main.projectSceneData
    history = main.ProjectHistory()
    dumps = json.dumps
    # Repeated camera-only saves do not encode the large chunks or decode the old file.
    with patch.object(session.json, "dumps", wraps = dumps) as encode, \
         patch.object(session.json, "loads", wraps = json.loads) as decode:
        for index in range(3):
            v.panOffset += QtCore.QPointF(3, 1)
            assert main.WriteSession(wait = True)
        assert not any(call.args[0] is scene or call.args[0] is history for call in encode.call_args_list)
        assert decode.call_count == 0
    assert main.sessionPath.with_name(main.sessionPath.name + ".bak").read_bytes() != initial
    # Short pans coalesce; a held button still permits a checkpoint every ten seconds.
    with patch.object(session, "monotonic", return_value = 100) as clock, \
         patch.object(main, "ProjectHistory", wraps = main.ProjectHistory) as historyEncode:
        v.isPanning = True
        for index in range(5):
            v.panOffset += QtCore.QPointF(11, -4)
            clock.return_value = 100 + index
            assert not main.WriteSession()
        assert historyEncode.call_count == 0 and main.sessionFuture is None
        clock.return_value = 110
        assert main.WriteSession()
        assert main.sessionFuture.result(timeout = 5) is None
        assert historyEncode.call_count == 1
        clock.return_value = 111
        assert not main.WriteSession()
        v.panOffset += QtCore.QPointF(29, 7)
        v.zoom = 1.75
        v.CancelInteraction()
    expectedView = {"pan": [v.panOffset.x(), v.panOffset.y()], "zoom": 1.75}
    main.sessionPollTimer.start()
    for index in range(100):
        app.processEvents()
        if main.sessionFuture is None or main.sessionFuture.done():
            if json.loads(main.sessionPath.read_bytes())["project"]["view"] == expectedView:
                break
        QtTest.QTest.qWait(50)
    main.sessionPollTimer.stop()
    assert json.loads(main.sessionPath.read_bytes())["project"]["view"] == expectedView
    # Serialization failure and disk errors remain observable with chunk caching enabled.
    before = v.CaptureState()
    v.walls[0].width += 1
    v.RecordEdit(before)
    with patch.object(session.json, "dumps", wraps = dumps) as encode:
        assert main.WriteSession(wait = True)
        assert any(call.args[0] is main.projectSceneData for call in encode.call_args_list)
        assert any(call.args[0] is main.ProjectHistory() for call in encode.call_args_list)
    good = main.sessionPath.read_bytes()
    invalid = json.loads(good)
    invalid["project"]["view"]["zoom"] = float("nan")
    assert main.sessionWriter.Write(main.sessionPath, invalid) is not None
    assert main.sessionPath.read_bytes() == good
    v.panOffset += QtCore.QPointF(1, 1)
    with patch.object(session, "WriteSessionFile", return_value = "Disk full"), warnings.catch_warnings(record = True):
        assert not main.WriteSession(wait = True)
    assert main.sessionError == "Disk full" and main.sessionPath.read_bytes() == good
    assert main.WriteSession(wait = True)
    # A file modified outside the writer is revalidated, never blindly copied over a good backup.
    backup = main.sessionPath.with_name(main.sessionPath.name + ".bak")
    previousBackup = backup.read_bytes()
    main.sessionPath.write_bytes(b"{broken")
    main.sessionSignature = None
    assert main.WriteSession(wait = True)
    assert backup.read_bytes() == previousBackup
    expected = copy.deepcopy(main.BuildProjectData())
    assert main.close()
    restored = MainWindow()
    assert restored.sessionRestored
    actual = restored.BuildProjectData()
    assert {key: value for key, value in actual.items() if key != "activityLog"} == {
        key: value for key, value in expected.items() if key != "activityLog"}
    from planner_app.activity_log import DecodeActivityLog
    previousEntries = DecodeActivityLog(expected["activityLog"])["entries"]
    assert restored.activityLog.entries[:len(previousEntries)] == previousEntries
    assert any(entry["summary"] == "Restored previous session" for entry in restored.activityLog.entries)
    assert restored.close()
    print("PASS: chunk reuse, bounded coalescing, latest-view recovery and observable failure safety")


if __name__ == "__main__":
    Main()
