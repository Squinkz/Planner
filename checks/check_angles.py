"""Verify Ctrl angle constraints during construction and endpoint dragging."""

import math
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtTest, QtWidgets

from check_history import Drag
from planner import MainWindow, Wall


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    alt = QtCore.Qt.KeyboardModifier.AltModifier
    leftButton = QtCore.Qt.MouseButton.LeftButton

    # All quadrants, including zero length; Ctrl is independent of Snap and Alt.
    anchor = point(37, 81)
    viewport.gridSnapEnabled = False
    for enabled in (True, False):
        viewport.snapEnabled = enabled
        for modifiers in (ctrl, ctrl | alt):
            for degrees in (-173, -98, -22, 0, 38, 112, 179):
                radians = math.radians(degrees)
                raw = anchor + point(700 * math.cos(radians), 700 * math.sin(radians))
                result = viewport.SnapWallEndpoint(raw, anchor, modifiers) - anchor
                expected = math.radians(round(degrees / 15) * 15)
                assert abs(result.x() - 700 * math.cos(expected)) < 1e-8
                assert abs(result.y() - 700 * math.sin(expected)) < 1e-8
            assert viewport.SnapWallEndpoint(anchor, anchor, modifiers) == anchor

    # Collinear endpoints remain exact, including when a closer off-line endpoint exists.
    viewport.snapEnabled = True
    target = point(600, 600)
    viewport.walls = [Wall(target, point(600, 610))]
    raw = point(608, 613)
    assert viewport.SnapWallEndpoint(raw, point(), ctrl) == target
    viewport.selectedWall = viewport.walls[0]
    viewport.selectedVertex = 0
    viewport.dragStart = point(1, 1)
    assert viewport.SnapWallEndpoint(raw, point(), ctrl) != target
    viewport.dragStart = None
    viewport.selectedWall = None
    viewport.selectedVertex = None
    assert viewport.SnapWallEndpoint(raw, point(), ctrl | alt) != target
    viewport.vertexSnapEnabled = False
    assert viewport.SnapWallEndpoint(raw, point(), ctrl) != target

    # Grid and alignment change length along the ray without breaking its angle.
    viewport.walls = []
    viewport.gridSnapEnabled = True
    result = viewport.SnapWallEndpoint(point(608, 613), point(), ctrl)
    assert abs(result.x() - 600) < 1e-8 and abs(result.y() - 600) < 1e-8
    viewport.gridSnapEnabled = False
    viewport.alignmentSnapEnabled = True
    viewport.vertexSnapEnabled = True
    viewport.walls = [Wall(point(630, 1200), point(1500, 1800))]
    result = viewport.SnapWallEndpoint(raw, point(), ctrl)
    assert abs(result.x() - 630) < 1e-8 and abs(result.y() - 630) < 1e-8
    viewport.walls = []
    viewport.vertexSnapEnabled = True
    viewport.alignmentSnapEnabled = False

    window.snapButton.setChecked(False)
    viewport.snapEnabled = False
    start = QtCore.QPoint(220, 300)
    end = QtCore.QPoint(420, 225)
    Drag(viewport, start, end, shift | ctrl, button = QtCore.Qt.MouseButton.RightButton)
    wall = viewport.walls[0]
    offset = wall.secondVertex - wall.firstVertex
    assert abs(math.degrees(math.atan2(offset.y(), offset.x())) - 15) < 1e-8
    viewport.Undo()
    assert not viewport.walls
    viewport.Redo()
    assert viewport.walls[0] is wall

    # Either endpoint rotates around the opposite one, without moving it.
    for vertexIndex in (0, 1):
        fixed = point(wall.secondVertex if vertexIndex == 0 else wall.firstVertex)
        moving = wall.firstVertex if vertexIndex == 0 else wall.secondVertex
        start = viewport.WorldToViewport(moving).toPoint()
        Drag(viewport, start, start + QtCore.QPoint(40, -70), ctrl)
        assert (wall.secondVertex if vertexIndex == 0 else wall.firstVertex) == fixed
        offset = (wall.firstVertex if vertexIndex == 0 else wall.secondVertex) - fixed
        angle = math.degrees(math.atan2(offset.y(), offset.x())) / 15
        assert abs(angle - round(angle)) < 1e-8
        viewport.Undo()

    # Ctrl press/release updates the preview even with a stationary cursor.
    start = QtCore.QPoint(220, 450)
    end = QtCore.QPoint(420, 375)
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.RightButton, shift, start)
    viewport.UpdateInteraction(point(end), shift)
    raw = point(viewport.pendingWall.secondVertex)
    QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_Control, shift)
    assert viewport.pendingWall.secondVertex != raw
    QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_Control, shift)
    assert viewport.pendingWall.secondVertex == raw
    viewport.CancelInteraction()

    # Ctrl constrains whole-wall translation without rotating the wall.
    original = (point(wall.firstVertex), point(wall.secondVertex))
    midpoint = viewport.WorldToViewport((original[0] + original[1]) / 2).toPoint()
    Drag(viewport, midpoint, midpoint + QtCore.QPoint(31, -43), ctrl)
    assert wall.firstVertex - original[0] == wall.secondVertex - original[1]
    translation = wall.firstVertex - original[0]
    assert translation == point(0, 215)
    print("Angle constraint checks passed.")


if __name__ == "__main__":
    Main()
