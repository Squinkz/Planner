"""Recovery/GC attribution uses one bounded timeline and leaves no global callback."""
import gc
import json
import os
import sys
import warnings
from pathlib import Path
from time import sleep
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow
from planner_app.ui import session
from planner_app.viewport.diagnostics import MeasureRecoveryWrite
from planner_app.viewport import diagnostics as diagnosticModule


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.sessionPollTimer.stop()
    main.sessionTimer.stop()
    v = main.viewport
    originalCallbacks = list(gc.callbacks)
    assert v.renderDiagnostics is None
    with patch.object(diagnosticModule, "perf_counter", side_effect = AssertionError("Disabled diagnostics read a clock")):
        assert main.WriteSession(wait = True)
    assert gc.callbacks == originalCallbacks
    v.SetRenderDiagnosticsEnabled(True)
    diagnostics = v.renderDiagnostics
    v.SetRenderDiagnosticsEnabled(True)
    assert gc.callbacks.count(diagnostics.gcCallback) == 1
    diagnostics.events.clear()
    v.panOffset += QtCore.QPointF(1, 0)
    assert main.WriteSession()
    assert main.sessionFuture.result(timeout = 5) is None
    assert main.WriteSession(wait = True)
    events = diagnostics.Report()["events"]
    recovery = [event for event in events if event["kind"] == "recovery"]
    assert [event["stage"] for event in recovery] == ["submitted", "started", "finished"]
    assert len({event["jobId"] for event in recovery}) == 1
    assert recovery[0]["onGuiThread"] and not recovery[0]["synchronous"]
    assert not recovery[1]["onGuiThread"] and not recovery[2]["onGuiThread"]
    assert recovery[2]["outcome"] == "saved" and recovery[2]["durationMs"] >= 0
    assert any(event.get("name") == "recovery-checkpoint" for event in events)
    # Real synchronous disk failure remains observable; no error/path content is logged.
    v.panOffset += QtCore.QPointF(1, 0)
    with patch.object(session, "WriteSessionFile", return_value = "Disk full"), warnings.catch_warnings(record = True):
        assert not main.WriteSession(wait = True)
    finished = [event for event in diagnostics.Report()["events"]
                if event["kind"] == "recovery" and event["stage"] == "finished"][-1]
    assert finished["outcome"] == "failed" and finished["onGuiThread"]
    assert main.sessionError == "Disk full"

    @MeasureRecoveryWrite
    def StalledWrite(writer):
        sleep(.1)
        raise ValueError("synthetic")

    try:
        StalledWrite(None, diagnostics = diagnostics, jobId = 999)
    except ValueError:
        pass
    else:
        raise AssertionError("Diagnostic wrapper swallowed a writer exception")
    stalled = [event for event in diagnostics.Report()["events"] if event.get("jobId") == 999][-1]
    assert stalled["outcome"] == "exception" and stalled["durationMs"] >= 90
    cycle = []
    cycle.append(cycle)
    del cycle
    gc.collect(2)
    collected = [event for event in diagnostics.Report()["events"] if event["kind"] == "gc"][-1]
    assert collected["generation"] == 2 and collected["collected"] > 0 and collected["onGuiThread"]
    assert collected["durationMs"] >= 0
    # Simulate callbacks on a worker without collecting Qt wrappers off the GUI thread.
    def WorkerGc():
        diagnostics.gcCallback("start", {"generation": 0})
        diagnostics.gcCallback("stop", {"generation": 0, "collected": 0, "uncollectable": 0})
    main.sessionExecutor.submit(WorkerGc).result(timeout = 5)
    workerGc = [event for event in diagnostics.Report()["events"] if event["kind"] == "gc"][-1]
    assert not workerGc["onGuiThread"]
    report = diagnostics.Report()
    assert report["environment"]["qt"] == QtCore.qVersion()
    assert report["environment"]["clock"] == "perf_counter"
    json.dumps(diagnostics.Report(), allow_nan = False)
    def RecordBurst():
        for index in range(3000):
            diagnostics.RecordRecovery("started", index)
    burst = main.sessionExecutor.submit(RecordBurst)
    for index in range(100):
        json.dumps(diagnostics.Report(), allow_nan = False)
    burst.result(timeout = 5)
    assert len(diagnostics.events) == 2048
    v.SetRenderDiagnosticsEnabled(False)
    assert gc.callbacks == originalCallbacks
    count = len(diagnostics.events)
    gc.collect(2)
    assert len(diagnostics.events) == count
    assert main.WriteSession(wait = True)
    assert len(diagnostics.events) == count
    v.SetRenderDiagnosticsEnabled(True)
    # Qt destruction must remove the global callback even without explicit Stop.
    main.close()
    main.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    assert gc.callbacks == originalCallbacks
    print("PASS: asynchronous/synchronous recovery, failure/exception timing, GC and callback cleanup")


if __name__ == "__main__":
    Main()
