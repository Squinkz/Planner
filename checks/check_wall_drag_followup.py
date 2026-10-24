"""Indexed measurements match a full scan; immutable metadata remains bounded."""
import math
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Counter, Pillar, Column, Door, Fireplace
from planner_app.viewport.widget import DrawingViewport
from planner_app.viewport.spatial_index import BoundsIndex


def Main():
    app = QtWidgets.QApplication([])
    viewport = DrawingViewport()
    viewport.resize(1200, 900)
    point = QtCore.QPointF
    for objectClass in (Wall, Counter):
        corners = [point(math.cos(index * math.tau / 24) * 2000,
                         math.sin(index * math.tau / 24) * 2000) for index in range(24)]
        walls = [objectClass(corners[index], corners[(index + 1) % len(corners)], 120 + (index % 3) * 60)
                 for index in range(len(corners))]
        walls.extend((Pillar(point(-500, -200), point(-500, 200), 400),
                      Column(point(500, -200), point(500, 200), 400)))
        viewport.walls = walls
        viewport.windows = [Door(walls[0], .2, .7), Fireplace(walls[4], .2, .7)] if objectClass is Wall else []
        for frame in range(5):
            walls[0].firstVertex = corners[0] + point(35 * frame, 21 * frame)
            walls[1].width += 10
            walls[2].firstMiter = .2 + frame * .15
            if viewport.windows:
                viewport.windows[0].measurementFlipped = bool(frame % 2)
            viewport.SetSelection([(walls[3], None)] if frame % 2 else [])
            viewport.panOffset = point(.37 * frame, .71 * frame)
            viewport.zoom = .4 + frame * .13
            boundary = viewport.ConnectedWallPath(walls)
            viewport.dimensionCacheKey = None
            actual = viewport.BuildWallDimensions(walls, boundary, viewport.windows, measureCaps = objectClass is Counter)
            # Bypass both spatial rejection and retained matching results to
            # exercise the original full wall scan for every boundary segment.
            viewport.dimensionCacheKey = None
            viewport.dimensionOwnerCache.clear()
            viewport.dimensionOwnerState = None
            viewport.dimensionSpanCache.clear()
            viewport.dimensionSpanCachePoints = 0
            with patch.object(BoundsIndex, "Query", lambda self, bounds: [entry[1] for entry in self.entries]):
                expected = viewport.BuildWallDimensions(walls, boundary, viewport.windows, measureCaps = objectClass is Counter)
            assert actual == expected, (objectClass, frame)
    # Explicit long spans and near-parallel segments exercise the tolerance
    # margin independently of contours produced by the wall tracer.
    viewport.zoom = .6
    viewport.panOffset = point()
    viewport.walls = [Wall(point(), point(2000, 0), 240)]
    viewport.windows = []
    for offset in (0, 1e8):
        wall = viewport.walls[0]
        wall.firstVertex, wall.secondVertex = point(offset, offset), point(offset + 2000, offset)
        for slope in (0, .9e-6, -.9e-6):
            first = point(offset - 1e7, offset + 120 - 1e7 * slope)
            second = point(offset + 1e7, offset + 120 + 1e7 * slope)
            boundary = QtGui.QPainterPath(viewport.WorldToViewport(first))
            boundary.lineTo(viewport.WorldToViewport(second))
            viewport.dimensionCacheKey = None
            actual = viewport.BuildWallDimensions([wall], boundary, [])
            viewport.dimensionCacheKey = None
            viewport.dimensionOwnerCache.clear()
            with patch.object(BoundsIndex, "Query", lambda self, bounds: [entry[1] for entry in self.entries]):
                assert viewport.BuildWallDimensions([wall], boundary, []) == actual
    for width in (0, -.01):
        wall.width = width
        boundary = QtGui.QPainterPath(viewport.WorldToViewport(wall.firstVertex))
        boundary.lineTo(viewport.WorldToViewport(wall.secondVertex))
        viewport.dimensionCacheKey = None
        actual = viewport.BuildWallDimensions([wall], boundary, [])
        viewport.dimensionCacheKey = None
        viewport.dimensionOwnerCache.clear()
        viewport.dimensionOwnerState = None
        viewport.dimensionSpanCache.clear()
        viewport.dimensionSpanCachePoints = 0
        with patch.object(BoundsIndex, "Query", lambda self, bounds: [entry[1] for entry in self.entries]):
            assert viewport.BuildWallDimensions([wall], boundary, []) == actual

    # Candidate geometry that already failed need not be validated again when
    # another snap mode proposes exactly the same endpoint.
    wall = Wall(point(), point(2000, 0), 240)
    viewport.walls = [wall]
    viewport.SetSelection([(wall, 1)])
    viewport.dragStart = point(100, 100)
    viewport.dragVertices = (point(wall.firstVertex), point(wall.secondVertex))
    viewport.snapEnabled = viewport.alignmentSnapEnabled = True
    viewport.vertexSnapEnabled = False

    def Aligned(position, *args, **kwargs):
        viewport.alignmentGuides = [(1, 0)]
        viewport.snapApplied = True
        viewport.snapPriority = 1
        return point(position)

    with patch.object(viewport, "StairSnapTargets", return_value = []), \
         patch.object(viewport, "SnapPosition", side_effect = Aligned), \
         patch.object(viewport, "WallFits", return_value = False) as validate:
        viewport.SnapStairVertex(point(2100, 0), point(), wall, QtCore.Qt.KeyboardModifier.NoModifier)
        assert validate.call_count == 1, validate.call_count
    viewport.dragStart = None

    # Cache values retain their immutable source to prevent id reuse, and the
    # number of retained polygons remains capped through extended editing.
    for index in range(4200):
        polygon = QtGui.QPolygonF([point(index, 0), point(index + 1, 1), point(index + 1, 0)])
        coordinates, bounds, normalized = viewport.PreparedWallPolygon(polygon)
        assert coordinates[0] == (index, 0) and bounds.width() == 1
        assert normalized[0] == polygon[-1]
    assert len(viewport.wallPolygonCache) <= 4096
    assert viewport.wallPolygonPointCount == sum(len(data[0]) for polygon, data in viewport.wallPolygonCache.values())
    large = QtGui.QPolygonF([point(index, index % 2) for index in range(66000)])
    viewport.PreparedWallPolygon(large)
    assert id(large) not in viewport.wallPolygonCache
    assert viewport.wallPolygonPointCount <= 65536
    print("PASS: full-scan measurement parity, large-coordinate tolerance, snap deduplication and bounded metadata.")


if __name__ == "__main__":
    Main()
