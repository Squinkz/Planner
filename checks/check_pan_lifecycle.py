"""Interrupted camera gestures and safe pan-to-scene ownership transfer."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall
from check_pan_dpi import CompareDirect


def Mouse(v, eventType, position, button, buttons):
    event = QtGui.QMouseEvent(eventType, position, QtCore.QPointF(v.mapToGlobal(position.toPoint())),
                             button, buttons, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(v, event)


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.sessionTimer.stop()
    main.sessionPollTimer.stop()
    main.show()
    app.processEvents()
    v = main.viewport
    v.performanceTimer.stop()
    point = QtCore.QPointF
    middle, none = QtCore.Qt.MouseButton.MiddleButton, QtCore.Qt.MouseButton.NoButton
    types = QtCore.QEvent.Type
    v.walls = [Wall(point(-1500, 0), point(1500, 0))]
    v.EnsureObjectIds()
    for export in (False, True):
        v.exportOverlay.SetActive(export)
        for ending in ("release", "lost-release", "ungrab", "deactivate", "cancel"):
            Mouse(v, types.MouseButtonPress, point(400, 300), middle, middle)
            assert v.isPanning
            before = point(v.panOffset)
            Mouse(v, types.MouseMove, point(420, 310), none, middle)
            assert v.panOffset == before + point(20, 10)
            before = point(v.panOffset)
            if ending == "release":
                Mouse(v, types.MouseButtonRelease, point(420, 310), middle, none)
            elif ending == "ungrab":
                app.sendEvent(v, QtCore.QEvent(types.UngrabMouse))
            elif ending == "deactivate":
                main.eventFilter(app, QtCore.QEvent(types.ApplicationDeactivate))
            elif ending == "cancel":
                v.CancelInteraction()
            Mouse(v, types.MouseMove, point(450, 340), none, none)
            assert not v.isPanning and v.lastPanPosition is None, (export, ending)
            assert not v.panFrameTimer.isActive() and v.panFrameDeadline is None
            assert v.panOffset == before, (export, ending)
            assert v.cursor().shape() != QtCore.Qt.CursorShape.ClosedHandCursor
    v.exportOverlay.SetActive(False)

    # Reuse is valid only if the last painted camera and scene still match.
    for change in ("none", "geometry", "selection", "camera", "zoom", "visibility", "measurements", "budget"):
        v.viewportRasterByteLimit = 128 * 1024 * 1024
        v.isPanning = True
        v.panOffset += point(4, 2)
        v.grab()
        raster = v.viewportPanRaster
        v.EndPan()
        if change == "geometry":
            v.walls[0].width += 10
        elif change == "selection":
            v.SetSelection([(v.walls[0], None)])
        elif change == "camera":
            v.panOffset += point(2, 1)
        elif change == "zoom":
            v.zoom *= 1.1
        elif change == "visibility":
            v.hiddenObjectIds.add(id(v.walls[0]))
        elif change == "measurements":
            v.showMeasurements = not v.showMeasurements
        elif change == "budget":
            v.viewportRasterByteLimit = 0
        with patch.object(v, "DrawScene", wraps = v.DrawScene) as draw:
            v.grab()
            assert (draw.call_count == 0) == (change == "none"), change
        if change == "none":
            assert v.viewportScene is raster
        assert v.viewportPanRaster is None
        assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
        CompareDirect(v)
    main.close()


if __name__ == "__main__":
    Main()
