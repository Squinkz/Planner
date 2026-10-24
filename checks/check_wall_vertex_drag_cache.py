"""Local wall edits preserve cold geometry and conservative collision results."""
import math
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner_app.models import Wall, Counter, Stair, Column, Furnishing
from planner_app.ui.main_window import MainWindow
from planner_app.viewport.geometry import CollisionPass, FootprintGeometry
from planner_app.viewport.spatial_index import BoundsIndex


@CollisionPass
def QueryPairs(viewport, pairs):
    return [viewport.JoinedObjectsOverlap(first, second) for first, second in pairs]


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    viewport = main.viewport
    point = QtCore.QPointF
    vertices = [point(index * 600, (index % 2) * 450) for index in range(31)]
    walls = [Wall(vertices[index], vertices[index + 1], 120 + (index % 3) * 60) for index in range(30)]
    viewport.walls = walls
    viewport.ConnectedWallPath(walls)
    for delta in (point(30, 50), point(-100, 20), point(80, -200)):
        walls[0].firstVertex = vertices[0] + delta
        with patch.object(viewport, "BuildWallJunction", wraps = viewport.BuildWallJunction) as builder:
            path = viewport.ConnectedWallPath(walls)
            assert builder.call_count <= 1, "An endpoint edit rebuilt unrelated junctions"
        reference = FootprintGeometry(viewport.basePixelsPerMillimeter, viewport)
        fresh = reference.BuildWallComponent(walls, True)
        assert path == fresh, "Warm outlines differ from a cold build"
        assert viewport.wallFillPolygons == reference.wallFillPolygons, "Warm material ownership differs"
    # Width, miter, topology and scale changes invalidate the same local inputs.
    for change in (lambda: setattr(walls[1], "width", 420),
                   lambda: setattr(walls[2], "firstMiter", .4),
                   lambda: walls.append(Wall(point(walls[2].firstVertex), point(-200, 900), 300)),
                   lambda: setattr(viewport, "basePixelsPerMillimeter", .13)):
        change()
        path = viewport.ConnectedWallPath(walls)
        reference = FootprintGeometry(viewport.basePixelsPerMillimeter, viewport)
        assert path == reference.BuildWallComponent(walls, True)
        assert viewport.wallFillPolygons == reference.wallFillPolygons

    # Every actual owned miter fragment must fit the early-rejection bound.
    # Include unequal widths, acute angles, collinear T joins, tolerance-boundary
    # clusters and a circular architectural member.
    for objectClass in (Wall, Counter, Stair):
        origin = point()
        star = [objectClass(origin, point(math.cos(angle) * 1800, math.sin(angle) * 1800), width)
                for angle, width in ((0, 120), (.0001, 240), (1.1, 450), (math.pi, 180), (-1.3, 320))]
        star.append(objectClass(point(.009, 0), point(-900, 800), 200))
        star.append(objectClass(point(-.009, 0), point(900, -800), 300))
        viewport.walls = star
        geometry = FootprintGeometry(viewport.basePixelsPerMillimeter)
        geometry.ConnectedWallPath(star, traceContours = False)
        transform = QtGui.QTransform().scale(1 / viewport.basePixelsPerMillimeter, -1 / viewport.basePixelsPerMillimeter)
        for owner, polygon in geometry.wallFillPolygons:
            bounds = viewport.JoinedObjectBounds(owner).adjusted(-1e-5, -1e-5, 1e-5, 1e-5)
            assert all(bounds.contains(vertex) for vertex in transform.map(polygon)), (objectClass, owner)

    # Compare optimized broad phase and retained pairs with uncached queries
    # that force construction of exact joined paths.
    walls = [Wall(point(), point(1800, 0), 240), Wall(point(), point(-900, 800), 300),
             Wall(point(10000, 10000), point(11000, 10000), 120),
             Column(point(1200, -300), point(1200, 300), 600)]
    viewport.walls = walls
    furnishings = [Furnishing(viewport.furnishingDefinitions["desk"], point(x, y))
                   for x, y in ((-250, -200), (600, 250), (1500, 150), (6000, 6000))]
    viewport.furnishings = furnishings
    viewport.windows = []
    pairs = [(wall, furnishing) for wall in walls for furnishing in furnishings]
    for change in (lambda: None, lambda: setattr(walls[0], "width", 600),
                   lambda: setattr(walls[1], "secondVertex", point(-1000, -30)),
                   lambda: setattr(walls[2], "secondVertex", point(12000, 9000))):
        change()
        with patch.object(viewport, "JoinedObjectBounds", return_value = QtCore.QRectF(-1e12, -1e12, 2e12, 2e12)):
            expected = [viewport.JoinedObjectsOverlap(first, second) for first, second in pairs]
        assert QueryPairs(viewport, pairs) == expected
    # A pair not queried during an edit must remain stale in a later pass;
    # merely seeing an unchanged scene cannot revive its earlier result.
    farWall, furnishing = walls[2], furnishings[-1]
    assert QueryPairs(viewport, [(farWall, furnishing)]) == [False]
    farWall.firstVertex = point(5500, 6000)
    farWall.secondVertex = point(6500, 6000)
    QueryPairs(viewport, [(walls[0], furnishings[0])])
    assert QueryPairs(viewport, [(farWall, furnishing)]) == [True]
    first, second = furnishings[:2]
    first.firstVertex, first.secondVertex, first.width = point(-350, -350), point(350, 350), 100
    second.firstVertex, second.secondVertex, second.width = point(-550, -150), point(150, 550), 100
    assert QueryPairs(viewport, [(first, second)]) == [False]
    pairKey = next(key for key in viewport.collisionPairKeys if set(key[:2]) == {id(first), id(second)})
    signature = viewport.collisionPairKeys[pairKey]
    farWall.secondVertex += point(500, 0)
    assert QueryPairs(viewport, [(first, second)]) == [False]
    assert viewport.collisionPairKeys[pairKey] is signature, "Recomputed an unaffected exact pair result"
    second.firstVertex, second.secondVertex = point(first.firstVertex), point(first.secondVertex)
    assert QueryPairs(viewport, [(first, second)]) == [True]
    # Oversized spatial queries stay bounded and keep sequential ownership order.
    index = BoundsIndex(10)
    entries = [(QtCore.QRectF(-1e8, -1e8, 2e8, 2e8), "large"),
               (QtCore.QRectF(0, 0, 4, 4), "first"), (QtCore.QRectF(2, 2, 4, 4), "second")]
    for bounds, value in entries:
        index.Insert(bounds, value)
    assert index.Query(QtCore.QRectF(1, 1, 4, 4)) == ["large", "first", "second"]
    assert len(index.buckets) <= 4

    # Suppressed validation must resume on cancel; a suppressed false value
    # must not poison the stationary furnishing's real collision result.
    wall = Wall(point(), point(1800, 0), 240)
    viewport.walls = [wall]
    viewport.furnishings = [Furnishing(viewport.furnishingDefinitions["desk"], point(600, 0))]
    viewport.labels = []
    viewport.SetSelection([(wall, 1)])
    viewport.zoom = .5
    viewport.panOffset = point()
    viewport.snapEnabled = False
    viewport.repaint()
    start = viewport.WorldToViewport(wall.secondVertex).toPoint()
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    assert viewport.dragStart is not None and viewport.selectedWall is wall
    with patch.object(viewport, "FurnishingFits", wraps = viewport.FurnishingFits) as validate:
        viewport.UpdateInteraction(point(start) + point(25, 30), QtCore.Qt.KeyboardModifier.NoModifier)
        viewport.repaint()
        assert validate.call_count == 0, "Validated a furnishing whose warning is suppressed"
        viewport.CancelInteraction()
        viewport.repaint()
        assert validate.call_count > 0, "Cancel did not restore furnishing validation"
    main.close()
    print("PASS: local junction reuse, cold geometry parity, conservative broad phase and drag validation lifecycle.")


if __name__ == "__main__":
    Main()
