"""Ruler drags move only the export grid; handles snap to its shifted lines."""
import copy
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from planner import MainWindow, Wall
from planner_app.project_codec import DecodeProject
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.resize(1300, 900)
    main.show()
    app.processEvents()
    v = main.viewport
    v.walls = [Wall(QtCore.QPointF(-1200, 0), QtCore.QPointF(1200, 0), 240)]
    main.sidebarTabs.setCurrentWidget(main.exportPanel)
    panel, overlay = main.exportPanel, v.exportOverlay
    panel.showGridField.setChecked(True)
    bounds = overlay.bounds
    scene = copy.deepcopy(main.BuildProjectData()["scene"])
    baseline = panel.Render("png")
    svg = panel.Render("svg")
    start = QtCore.QPoint(round(v.DrawingRect().center().x()), v.rulerSize // 2)
    end = start + QtCore.QPoint(73, 0)
    step = v.GridSteps(overlay.scale / 1000)[1]
    delta = 73 / (v.basePixelsPerMillimeter * v.zoom)
    expected = math.floor(delta / step + .5) * step
    Drag(v, start, end)
    assert v.gridOrigin == (expected, 0) and overlay.bounds == bounds
    start = QtCore.QPoint(v.rulerSize // 2, round(v.DrawingRect().center().y()))
    Drag(v, start, start - QtCore.QPoint(0, 37), QtCore.Qt.KeyboardModifier.AltModifier)
    assert abs(v.gridOrigin[1] - 37 / (v.basePixelsPerMillimeter * v.zoom)) < .001
    origin = v.gridOrigin
    assert main.BuildProjectData()["scene"] == scene and overlay.bounds == bounds
    assert panel.Render("png") != baseline and panel.Render("svg") != svg
    v.grab()
    assert overlay.snapshotViewport.gridOrigin == origin
    # Crop ruler strips also expose horizontal and vertical origin handles.
    cropTop = v.WorldToViewport(QtCore.QPointF(bounds[0] + bounds[2] / 2, bounds[1] + bounds[3]))
    assert overlay.HitRuler(cropTop - QtCore.QPointF(0, 12)) == 0
    v.gridSnapEnabled = False
    overlay.MoveEdge(0, bounds[0] + 337)
    assert abs((overlay.bounds[0] - origin[0]) / step - round((overlay.bounds[0] - origin[0]) / step)) < .001
    overlay.MoveEdge(0, bounds[0], reset = True)
    saved = main.BuildProjectData()
    assert saved["settings"]["exportSettings"]["gridOrigin"] == list(origin)
    assert "gridOrigin" not in saved["settings"]
    decoded = DecodeProject(saved, v.furnishingDefinitions)
    assert decoded[5]["exportSettings"]["gridOrigin"] == list(origin)
    main.sidebarTabs.setCurrentIndex(0)
    assert v.gridOrigin == (0, 0)
    main.sidebarTabs.setCurrentWidget(panel)
    assert v.gridOrigin == origin
    main.ApplyProject(decoded, None)
    assert v.gridOrigin == origin
    # Reset each ruler independently, without snapping the other axis or
    # starting a new drag from the double-click's trailing release.
    cropTop = v.WorldToViewport(QtCore.QPointF(overlay.bounds[0] + overlay.bounds[2] / 2,
                                              overlay.bounds[1] + overlay.bounds[3]))
    positions = ((QtCore.QPointF(v.DrawingRect().center().x(), v.rulerSize / 2), 0),
                 (QtCore.QPointF(v.rulerSize / 2, v.DrawingRect().center().y()), 1),
                 (cropTop - QtCore.QPointF(0, 12), 0))
    for position, axis in positions:
        panel.SetOverride("gridOrigin", [337.25, -123.75])
        panel.ResetExportHistory()
        before = tuple(v.gridOrigin)
        camera = (v.zoom, QtCore.QPointF(v.panOffset))
        crop = tuple(overlay.bounds)
        assert overlay.HitRuler(position) == axis
        QtTest.QTest.mouseDClick(v, QtCore.Qt.MouseButton.LeftButton, pos = position.toPoint())
        QtTest.QTest.mouseMove(v, (position + QtCore.QPointF(15, 15)).toPoint())
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = position.toPoint())
        expected = list(before)
        expected[axis] = 0.0
        assert v.gridOrigin == tuple(expected)
        assert (v.zoom, v.panOffset) == camera and tuple(overlay.bounds) == crop
        assert overlay.dragRuler is None and len(panel.exportUndoHistory) == 1
        v.Undo()
        assert v.gridOrigin == before
        v.Redo()
        assert v.gridOrigin == tuple(expected)
        QtTest.QTest.mouseDClick(v, QtCore.Qt.MouseButton.LeftButton, pos = position.toPoint())
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = position.toPoint())
        assert len(panel.exportUndoHistory) == 1, "Resetting an unchanged origin created an undo step"
    main.close()
    print("PASS: export ruler origin drag, snapping, rendering, persistence and viewport restoration")


if __name__ == "__main__":
    Main()
