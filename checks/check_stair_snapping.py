"""Stairs snap footprint corners and their alignment during placement and editing."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall, Stair
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    wall = Wall(point(-1500, 0), point(1500, 0))
    viewport.walls = [wall]
    viewport.gridSnapEnabled = False
    viewport.alignmentSnapEnabled = False
    viewport.midpointSnapEnabled = False
    targets = viewport.StairSnapTargets()
    assert point(-1500, 120) in targets and point(1500, -120) in targets
    assert wall.firstVertex not in targets and wall.secondVertex not in targets
    snapped = viewport.SnapPosition(point(1480, 130), QtCore.Qt.KeyboardModifier.NoModifier, snapTargets = targets)
    assert snapped == point(1500, 120)
    raw = point(1490, 0)
    assert viewport.SnapPosition(raw, QtCore.Qt.KeyboardModifier.NoModifier, snapTargets = targets) == raw
    # Drag-out placement snaps a footprint corner, not a centerline endpoint.
    placement = viewport.FindStairPlacement(viewport.WorldToViewport(point(-975, 650)))
    assert placement is not None and placement.firstVertex == point(-1500, 620)
    assert point(-1500, 120) in viewport.ObjectCorners(placement)
    assert viewport.StairFits(placement)
    # Whole-object dragging uses the same footprint anchors.
    source = Stair(point(-1900, 1150), point(-900, 1150))
    viewport.walls.append(source)
    start = viewport.WorldToViewport(point(-1400, 1150)).toPoint()
    end = viewport.WorldToViewport(point(-975, 650)).toPoint()
    Drag(viewport, start, end)
    assert source.firstVertex == point(-1500, 620) and source.secondVertex == point(-500, 620)
    viewport.Undo()
    # Endpoint edits preserve the width while putting its cap corner on target.
    source.firstVertex, source.secondVertex = point(-2500, 620), point(-1500, 620)
    target = viewport.SnapStairVertex(point(-1510, 630), source.firstVertex, source, QtCore.Qt.KeyboardModifier.NoModifier)
    assert QtCore.QLineF(target, point(-1500, 620)).length() < 1e-8
    ctrlTarget = viewport.SnapStairVertex(point(-1510, 620), source.firstVertex, source, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert QtCore.QLineF(ctrlTarget, point(-1500, 620)).length() < 1e-8
    # Alignment originates at wall faces, and Alt reverses snapping as usual.
    viewport.alignmentSnapEnabled = True
    aligned = viewport.SnapPosition(point(1000, 130), QtCore.Qt.KeyboardModifier.NoModifier, snapTargets = targets)
    assert aligned.y() == 120 and viewport.alignmentGuides == [(1, 120)]
    raw = point(1000, 10)
    assert viewport.SnapPosition(raw, QtCore.Qt.KeyboardModifier.NoModifier, snapTargets = targets) == raw
    raw = point(1480, 130)
    assert viewport.SnapPosition(raw, QtCore.Qt.KeyboardModifier.AltModifier, snapTargets = targets) == raw
    # Joined wall miter corners are included, beyond the rectangular end caps.
    viewport.walls = [Wall(point(), point(1000, 0)), Wall(point(), point(0, 1000))]
    targets = viewport.StairSnapTargets()
    assert any(QtCore.QLineF(vertex, point(120, 120)).length() < 1e-6 for vertex in targets)
    window.close()
    print("PASS: OBB corner targets, exclusion of control vertices, placement/body/vertex snapping, alignment, Ctrl, Alt and miter corners.")


if __name__ == "__main__":
    Main()
