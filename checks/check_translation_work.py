"""Unsnapped selection previews skip snap work while retaining collision rollback."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall
from planner_app.models import Furnishing


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    left = QtCore.Qt.MouseButton.LeftButton
    viewport.snapEnabled = False
    viewport.connectedEnabled = False
    wall = Wall(point(-2000, 0), point(2000, 0), 240)
    desk = Furnishing(viewport.furnishingDefinitions["desk"], point(0, -900))
    second = Furnishing(viewport.furnishingDefinitions["desk"], point(1500, -900))
    viewport.walls = [wall]
    viewport.furnishings = [desk, second]
    viewport.SetSelection([(desk, None), (second, None)])
    original = viewport.CaptureState()
    start = viewport.WorldToViewport((desk.firstVertex + desk.secondVertex) / 2).toPoint()
    end = viewport.WorldToViewport(point(0, 0)).toPoint()
    QtTest.QTest.mousePress(viewport, left, pos = start)
    assert viewport.groupDrag
    with patch.object(viewport, "StairSnapTargets", wraps = viewport.StairSnapTargets) as targets, \
            patch.object(viewport, "FurnishingFits", wraps = viewport.FurnishingFits) as fits:
        event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, point(end),
                                 point(viewport.mapToGlobal(end)), QtCore.Qt.MouseButton.NoButton,
                                 left, QtCore.Qt.KeyboardModifier.NoModifier)
        app.sendEvent(viewport, event)
        assert targets.call_count == fits.call_count == 0
        assert desk.firstVertex != original[5][0][1]
        assert viewport.ObjectsOverlap(desk, wall)
        viewport.grab()
        assert fits.call_count > 0  # The invalid preview still gets validated.
        QtTest.QTest.mouseRelease(viewport, left, pos = end)
        assert targets.call_count == 0
    assert viewport.CaptureState()[5] == original[5]
    assert not viewport.undoHistory
    # Ctrl must still constrain the common delta when there are no snap anchors.
    QtTest.QTest.mousePress(viewport, left, pos = start)
    constrainedEnd = start + QtCore.QPoint(50, 20)
    event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, point(constrainedEnd),
                             point(viewport.mapToGlobal(constrainedEnd)), QtCore.Qt.MouseButton.NoButton,
                             left, QtCore.Qt.KeyboardModifier.ControlModifier)
    app.sendEvent(viewport, event)
    assert desk.firstVertex.y() == original[5][0][1].y()
    assert desk.firstVertex.x() != original[5][0][1].x()
    viewport.CancelInteraction()
    window.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
