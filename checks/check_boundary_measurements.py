"""Prepared contours and local measurement caches match frozen reference code."""
import math
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Pillar, Column, Door, Window, SilledWindow, CasementWindow, PocketDoor, SlidingDoor, BarnDoor, BifoldDoor, Fireplace
from planner_app.viewport.geometry import FootprintGeometry
from planner_app.viewport.widget import DrawingViewport
from planner_app.viewport.spatial_index import BoundsIndex
from fixtures.boundary_measurement_reference_20261016 import OriginalBuildWallDimensions, OriginalTraceWallComponent


def Main():
    app = QtWidgets.QApplication([])
    point = QtCore.QPointF
    for scale in (.001, .2, 1.5):
        for offset in (point(), point(1e8, -1e8)):
            warm = FootprintGeometry(scale)
            for frame in range(12):
                paths = [QtGui.QPolygonF([point(0, 0), point(500 + frame, 0), point(500, 100), point(0, 100)]),
                         QtGui.QPolygonF([point(50, -100), point(150, -100), point(100.00000001, 300)]),
                         QtGui.QPolygonF([point(800, 200), point(900, 200), point(900, 300), point(800, 300)]),
                         QtGui.QPolygonF([point(500, 100), point(500 + 1e-10, 100), point(600, 101), point(600, 200)]),
                         QtGui.QPolygonF([point(1, 1), point(1, 1), point(1, 1)])]
                transform = QtGui.QTransform().translate(offset.x(), offset.y()).scale(scale, scale)
                polygons = [transform.map(polygon) for polygon in paths]
                if frame % 3 == 1:
                    polygons[1] = QtGui.QPolygonF(list(reversed(polygons[1])))
                filled = QtGui.QPainterPath()
                filled.setFillRule(QtCore.Qt.FillRule.WindingFill)
                for polygon in polygons:
                    filled.addPolygon(polygon)
                    filled.closeSubpath()
                actual = warm.TraceWallComponent(filled, traceKey = "fixture",
                    preparedContours = [warm.PreparedWallContour(polygon) for polygon in polygons])
                assert actual == OriginalTraceWallComponent(FootprintGeometry(scale), filled), (scale, offset, frame)
                assert warm.TraceWallBoundary(filled, sourcePolygons = polygons) == FootprintGeometry(scale).TraceWallBoundary(filled)

    viewport, reference = DrawingViewport(), DrawingViewport()
    for view in (viewport, reference):
        view.resize(1200, 900)
    for offset in (point(), point(1e8, -1e8)):
        corners = [point(-2500, -1800), point(2500, -1800), point(2500, 1800), point(-2500, 1800)]
        walls = [Wall(offset + corners[index], offset + corners[(index + 1) % 4], 200) for index in range(4)]
        walls += [Wall(offset + point(-3000, 150), offset + point(3000, 150.0001), 140),
                  Pillar(offset + point(-2500, -200), offset + point(-2500, 200), 500),
                  Column(offset + point(400, -300), offset + point(400, 300), 600)]
        openings = [Door(walls[0], .05, .2), PocketDoor(walls[0], .3, .5),
                    BarnDoor(walls[1], .1, .3), SlidingDoor(walls[1], .5, .7),
                    Fireplace(walls[2], .2, .45), BifoldDoor(walls[2], .5, .7),
                    Window(walls[3], .05, .2), SilledWindow(walls[3], .35, .5), CasementWindow(walls[3], .65, .85)]
        for frame in range(18):
            walls[0].firstVertex = offset + corners[0] + point(frame * 3, frame * 5)
            walls[1].width = 200 + frame * 10
            openings[0].swingsOutwards = bool(frame % 2)
            openings[1].hingeAtSecond = bool(frame % 2)
            openings[2].measurementFlipped = bool(frame % 2)
            openings[3].panelsFlipped = bool(frame % 2)
            openings[4].depthOffset = frame * 3
            openings[6].firstFraction = .05 + frame * .001
            if frame == 8:
                openings[6] = Window(walls[3], openings[6].firstFraction, openings[6].secondFraction)
            members = walls[::-1] if frame % 4 == 0 else walls
            selected = [(walls[0], None)] if frame % 3 == 1 else [(openings[4], None)] if frame % 3 == 2 else []
            for view in (viewport, reference):
                view.walls, view.windows = members, openings
                view.SetSelection(selected)
                view.zoom = .4 + (frame // 6) * .2
                view.panOffset = point(.37, .71)
                view.measurementSettings["doors"] = frame % 3
                view.measurementSettings["windows"] = (frame // 3) % 3
            boundary = viewport.ConnectedWallPath(members)
            cutters = [QtGui.QPolygonF([offset + point(-1500 + frame * 30, -2000), offset + point(-1000, -2000),
                                       offset + point(-1000, -1500), offset + point(-1500 + frame * 30, -1500)])]
            blockers = [QtGui.QPolygonF([offset + point(-3000, -1200 + frame * 10), offset + point(-2200, -1200),
                                        offset + point(-2200, -800), offset + point(-3000, -800)])]
            viewport.dimensionCacheKey = reference.dimensionCacheKey = None
            actual = viewport.BuildWallDimensions(members, boundary, openings, measureCaps = bool(frame % 2),
                                                  blockers = blockers, cutters = cutters)
            expected = OriginalBuildWallDimensions(reference, members, boundary, openings, measureCaps = bool(frame % 2),
                                                    blockers = blockers, cutters = cutters)
            assert actual == expected, (offset, frame)
            assert [[id(owner) for owner in owners] for first, second, owners in actual] == [
                    [id(owner) for owner in owners] for first, second, owners in expected], (offset, frame, "owner identity")
            assert viewport.dimensionSpanCachePoints == sum(size for spans, size in viewport.dimensionSpanCache.values())
            assert viewport.dimensionSpanCachePoints <= 32768

    # Stable spans should stop querying the spatial index, while a changed
    # candidate entering their bounds must still update the exact owners.
    from unittest.mock import patch
    walls = [Wall(point(index * 1000, 0), point(index * 1000, 800), 200) for index in range(30)]
    viewport.walls, viewport.windows = walls, []
    viewport.SetSelection([])
    viewport.zoom = 1
    viewport.panOffset = point()
    viewport.dimensionCacheKey = viewport.dimensionOwnerState = None
    boundary = viewport.ConnectedWallPath(walls)
    viewport.BuildWallDimensions(walls, boundary, [])
    walls[0].firstVertex += point(30, 20)
    boundary = viewport.ConnectedWallPath(walls)
    with patch.object(BoundsIndex, "Query", autospec = True, side_effect = BoundsIndex.Query) as queries:
        actual = viewport.BuildWallDimensions(walls, boundary, [])
        assert queries.call_count < 20, queries.call_count
    reference.zoom, reference.panOffset = viewport.zoom, viewport.panOffset
    reference.SetSelection([])
    assert actual == OriginalBuildWallDimensions(reference, walls, boundary, [])
    assert viewport.wallContourCachePoints == sum(size for polygon, data, size in viewport.wallContourCache.values())
    assert len(viewport.wallContourCache) <= 2048 and viewport.wallContourCachePoints <= 32768
    child = FootprintGeometry(.2, viewport)
    assert child.dimensionSpanCache is not viewport.dimensionSpanCache
    assert child.wallContourCache is not viewport.wallContourCache
    for index in range(2200):
        polygon = QtGui.QPolygonF([point(index, 0), point(index + 1, 1), point(index + 1, 0)])
        child.PreparedWallContour(polygon)
    assert child.wallContourCachePoints == sum(size for polygon, data, size in child.wallContourCache.values())
    assert len(child.wallContourCache) <= 2048 and child.wallContourCachePoints <= 32768
    oversized = QtGui.QPolygonF([point(index, index % 2) for index in range(9000)])
    child.PreparedWallContour(oversized)
    assert id(oversized) not in child.wallContourCache
    wall = Wall(point(), point(2000, 0), 200)
    viewport.walls = [wall]
    viewport.measurementSettings["doors"] = 0
    oldDoor = Door(wall, .2, .4)
    boundary = viewport.ConnectedWallPath([wall])
    viewport.BuildWallDimensions([wall], boundary, [oldDoor])
    newDoor = Door(wall, .2, .4)
    dimensions = viewport.BuildWallDimensions([wall], boundary, [newDoor])
    assert any(owner is newDoor for first, second, owners in dimensions for owner in owners)
    assert not any(owner is oldDoor for first, second, owners in dimensions for owner in owners)
    for index in range(1100):
        boundary = QtGui.QPainterPath(viewport.WorldToViewport(point(index * .1, 100)))
        boundary.lineTo(viewport.WorldToViewport(point(1900, 100)))
        viewport.BuildWallDimensions([wall], boundary, [])
    assert len(viewport.dimensionSpanCache) <= 1024
    assert viewport.dimensionSpanCachePoints == sum(size for spans, size in viewport.dimensionSpanCache.values())
    assert viewport.dimensionSpanCachePoints <= 32768
    print("PASS: frozen boundary/measurement parity, opening settings, blockers, local owner queries and cache accounting")


if __name__ == "__main__":
    Main()
