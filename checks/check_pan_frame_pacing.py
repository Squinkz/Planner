"""Pan input stays immediate while repaint requests share one refresh deadline."""
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner_app.viewport.widget import DrawingViewport
from planner_app.viewport import interaction


def Mouse(viewport, eventType, position, button, buttons):
    event = QtGui.QMouseEvent(eventType, position, position, button, buttons, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, event)


def Main():
    app = QtWidgets.QApplication([])
    v = DrawingViewport()
    v.resize(1000, 700)
    v.show()
    app.processEvents()
    point, types = QtCore.QPointF, QtCore.QEvent.Type
    middle, none = QtCore.Qt.MouseButton.MiddleButton, QtCore.Qt.MouseButton.NoButton
    for rate in (60, 144, 0, float("nan")):
        screen = SimpleNamespace(refreshRate = lambda: rate)
        with patch.object(v, "screen", return_value = screen), patch.object(interaction, "perf_counter", return_value = 100):
            Mouse(v, types.MouseButtonPress, point(200, 200), middle, middle)
        interval = 1 / (rate if math.isfinite(rate) and rate > 0 else 60)
        assert v.panFrameInterval == interval
        before = point(v.panOffset)
        with patch.object(v, "update") as redraw, patch.object(interaction, "perf_counter", return_value = 100):
            for index in range(1, 201):
                position = point(200 + index * .37, 200 - index * .19)
                Mouse(v, types.MouseMove, position, none, middle)
                assert QtCore.QLineF(v.panOffset, before + position - point(200, 200)).length() < 1e-9
            assert v.panFrameTimer.isActive()
            assert redraw.call_count == 0, 'Input bursts must not bypass the pan repaint scheduler'
        v.panFrameTimer.stop()
        with patch.object(v, "update") as redraw, patch.object(interaction, "perf_counter", return_value = 100 + interval * 8.3):
            v.PaintPanFrame()
            assert redraw.call_count == 1
            assert 100 + interval * 8.3 < v.panFrameDeadline <= 100 + interval * 9.3
        with patch.object(v, "update") as redraw:
            Mouse(v, types.MouseButtonRelease, position, middle, none)
            assert not v.isPanning and not v.panFrameTimer.isActive() and v.panFrameDeadline is None
            assert redraw.call_count > 0, 'Release must immediately schedule the final camera state'
        final = point(v.panOffset)
        QtTest.QTest.qWait(25)
        assert v.panOffset == final, 'No queued animation may continue after release'
    v.close()
    print("PASS: refresh-rate/fallback deadlines, immediate fractional input, one queued repaint, skipped late slots and final-state cleanup")


if __name__ == "__main__":
    Main()
