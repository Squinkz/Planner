"""Opt-in timing, injected stalls, cache reasons and bounded telemetry."""
import json
import os
from pathlib import Path
import sys
import tempfile
from time import sleep

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from unittest.mock import patch
from planner_app.models import Wall
from planner_app.viewport.widget import DrawingViewport
from planner_app.viewport.diagnostics import MeasurePaint


@MeasurePaint
def SlowCallback(viewport):
    sleep(.1)


def Main():
    app = QtWidgets.QApplication([])
    v = DrawingViewport()
    v.resize(1000, 700)
    v.walls = [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0))]
    v.show()
    app.processEvents()
    assert v.renderDiagnostics is None
    v.SetRenderDiagnosticsEnabled(True)
    diagnostics = v.renderDiagnostics
    v.grab()
    v.grab()
    v.isPanning = True
    v.grab()
    v.panOffset += QtCore.QPointF(3, 1)
    v.grab()
    v.panOffset += QtCore.QPointF(.3, .2)
    v.grab()
    assert diagnostics.cacheCounts[("pan", "hit", "reused")] >= 1
    assert diagnostics.cacheCounts[("pan", "miss", "fractional-movement")] >= 1
    assert any(event.get("name") == "scene-key" for event in diagnostics.events)
    QtTest.QTest.mouseMove(v, QtCore.QPoint(120, 120))
    v.grab()
    assert any(sample["inputAgeMs"] is not None for sample in diagnostics.paints)
    # Native input timestamps and delivery time are separate clocks. A delayed
    # event must expose relative queue lag instead of looking newly generated.
    event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(120, 120), QtCore.QPointF(120, 120),
                             QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.MiddleButton,
                             QtCore.Qt.KeyboardModifier.NoModifier)
    diagnostics.lastInputTimestamp = diagnostics.inputClockOffset = None
    event.setTimestamp(1000)
    with patch("planner_app.viewport.diagnostics.perf_counter", return_value = 10):
        diagnostics.RecordInput(event)
    event.setTimestamp(1010)
    with patch("planner_app.viewport.diagnostics.perf_counter", return_value = 10.09):
        diagnostics.RecordInput(event)
    assert abs(diagnostics.inputs[-1]["relativeQueueLagMs"] - 80) < 1e-6
    assert diagnostics.oldestInputAt <= diagnostics.inputAt
    diagnostics.inputAt = diagnostics.oldestInputAt = None
    QtTest.QTest.qWait(30)
    QtCore.QTimer.singleShot(1, lambda: SlowCallback(v))
    QtTest.QTest.qWait(180)
    report = diagnostics.Report()
    assert report["summary"]["paintCpuMs"]["max"] >= 90
    assert report["summary"]["paintCpuMs"]["over50Ms"] >= 1
    assert report["summary"]["eventLoopDelayMs"]["max"] >= 70
    assert report["summary"]["relativeInputQueueLagMs"]["max"] >= 79
    assert report["inputs"] and "inputsSincePaint" in report["paints"][-1]
    assert any(event["kind"] == "eventLoopDelay" for event in report["events"])
    for index in range(3000):
        diagnostics.RecordPaint(index, index + .001)
        diagnostics.RecordCache("scene", "miss", "cold-or-changed")
    assert len(diagnostics.paints) == len(diagnostics.events) == 2048
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "report.json"
        diagnostics.Write(path)
        assert json.loads(path.read_text())["version"] == 1
    v.SetRenderDiagnosticsEnabled(False)
    count = len(diagnostics.paints)
    v.grab()
    assert len(diagnostics.paints) == count and not diagnostics.timer.isActive()
    v.close()
    print("PASS: injected 100ms CPU/event-loop stalls, input age, cache reasons, bounded data and disabled mode.")


if __name__ == "__main__":
    Main()
