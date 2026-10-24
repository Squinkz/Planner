"""Joined stair contours and direct endpoint snapping at obtuse angles."""
import math
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Stair, Wall
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    randomSource = random.Random(241)
    for rotation in (0, 37, 143):
        for angle in (91, 105, 120, 135, 150, 170):
            origin = point(13.375, -17.125)
            firstAngle = math.radians(rotation)
            secondAngle = math.radians(rotation + angle)
            stairs = [Stair(origin, origin + point(math.cos(firstAngle), math.sin(firstAngle)) * 3500, 997.5),
                      Stair(origin, origin + point(math.cos(secondAngle), math.sin(secondAngle)) * 2300, 811.25)]
            raw = viewport.ConnectedWallPath(stairs, traceContours = False)
            joined = viewport.ConnectedStairPath(stairs)
            outline = viewport.stairOutlinePath
            for index in range(0, outline.elementCount(), 2):
                first, second = outline.elementAt(index), outline.elementAt(index + 1)
                assert first.isMoveTo() and second.isLineTo()
                midpoint = point((first.x + second.x) / 2, (first.y + second.y) / 2)
                delta = point(second.x - first.x, second.y - first.y)
                normal = point(-delta.y(), delta.x()) / math.hypot(delta.x(), delta.y()) * .00001
                assert viewport.stairGeometryPath.contains(midpoint + normal) != viewport.stairGeometryPath.contains(midpoint - normal)
            bounds = raw.boundingRect()
            for index in range(700):
                sample = point(randomSource.uniform(bounds.left(), bounds.right()),
                               randomSource.uniform(bounds.top(), bounds.bottom()))
                assert joined.contains(sample) == raw.contains(sample), (rotation, angle, sample)
            # Panning/zooming reuse the cached union and preserve its coverage.
            geometry = viewport.stairGeometryPath
            viewport.zoom *= 1.1
            viewport.ConnectedStairPath(stairs)
            assert viewport.stairGeometryPath == geometry
            viewport.zoom /= 1.1
    # Closed loops preserve both the stair bodies and their empty center.
    corners = [point(0, 0), point(3000, 0), point(3000, 3000), point(0, 3000)]
    stairs = [Stair(corners[index], corners[(index + 1) % 4], 500) for index in range(4)]
    joined = viewport.ConnectedStairPath(stairs)
    assert not joined.contains(viewport.WorldToViewport(point(1500, 1500)))
    for stair in stairs:
        assert joined.contains(viewport.WorldToViewport((stair.firstVertex + stair.secondVertex) / 2))
    source = Stair(point(-2000, 0), point(0, 0), 800)
    target = Stair(point(1000, 500), point(2500, -500), 1000)
    viewport.walls = [source, target]
    viewport.snapEnabled = True
    viewport.vertexSnapEnabled = True
    viewport.gridSnapEnabled = False
    viewport.alignmentSnapEnabled = False
    viewport.midpointSnapEnabled = False
    raw = point(980, 480)
    snapped = viewport.SnapStairVertex(raw, source.firstVertex, source, QtCore.Qt.KeyboardModifier.NoModifier)
    assert snapped == target.firstVertex
    assert viewport.SnapStairVertex(raw, source.firstVertex, source, QtCore.Qt.KeyboardModifier.AltModifier) == raw
    Drag(viewport, viewport.WorldToViewport(source.secondVertex).toPoint(), viewport.WorldToViewport(raw).toPoint())
    assert source.secondVertex == target.firstVertex and viewport.StairFits(source)
    viewport.Undo()
    assert source.secondVertex == point(0, 0)
    viewport.Redo()
    assert source.secondVertex == target.firstVertex
    # All stair overlaps are allowed; wall collisions still block movement.
    overlap = Stair(point(-1000, 0), point(2000, 0), 1000)
    assert viewport.StairFits(overlap)
    duplicate = Stair(source.firstVertex, source.secondVertex, source.width)
    assert viewport.StairFits(duplicate)
    viewport.alignmentSnapEnabled = True
    viewport.vertexSnapEnabled = False
    viewport.cornerSnapEnabled = False
    raw = point(980, -480)
    assert viewport.SnapStairVertex(raw, source.firstVertex, source, QtCore.Qt.KeyboardModifier.NoModifier) == raw
    assert not viewport.alignmentGuides
    viewport.vertexSnapEnabled = True
    aligned = viewport.SnapStairVertex(raw, source.firstVertex, source, QtCore.Qt.KeyboardModifier.NoModifier)
    assert aligned == point(1000, -500)
    assert viewport.alignmentGuides == [(0, 1000), (1, -500)]
    assert viewport.SnapStairVertex(raw, source.firstVertex, source, QtCore.Qt.KeyboardModifier.AltModifier) == raw
    aligned = viewport.SnapStairVertex(raw, point(-2000, -500), source, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert aligned == point(1000, -500)
    assert viewport.alignmentGuides == [(0, 1000)]
    # Exercise alignment through actual endpoint dragging and history.
    viewport.Undo()
    Drag(viewport, viewport.WorldToViewport(source.secondVertex).toPoint(), viewport.WorldToViewport(raw).toPoint())
    assert source.secondVertex == point(1000, -500)
    viewport.Undo()
    assert source.secondVertex == point(0, 0)
    viewport.Redo()
    assert source.secondVertex == point(1000, -500)
    viewport.walls.append(Wall(point(0, 100), point(1000, 100)))
    assert not viewport.StairFits(source)
    viewport.walls = [Stair(point(-3000, 0), point(0, 0)), Stair(point(0, 0), point(1500, -1500))]
    viewport.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "stair-obtuse-junction.png"))
    window.close()
    print("PASS: obtuse contours, closed loops, cache reuse, endpoint joins, Alt, undo/redo and collision limits.")


if __name__ == "__main__":
    Main()
