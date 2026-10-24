"""Rigid wall movement reuses contours and measurements without stale geometry."""
import math
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow, Stair, Wall


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    viewport = main.viewport
    point = QtCore.QPointF
    viewport.snapEnabled = False
    viewport.connectedEnabled = viewport.connectedVerticesEnabled = True
    corners = [point(math.cos(index * math.tau / 63) * 1500, math.sin(index * math.tau / 63) * 1500)
               for index in range(63)]
    walls = [Wall(corners[index], corners[(index + 1) % 63], 120) for index in range(63)]
    viewport.walls = walls
    viewport.SetSelection([(wall, None) for wall in walls])
    app.processEvents()
    start = viewport.WorldToViewport((walls[0].firstVertex + walls[0].secondVertex) / 2).toPoint()
    with patch.object(viewport, "AttachedVertices", wraps = viewport.AttachedVertices) as attachments:
        QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
        assert attachments.call_count == 1
    assert viewport.groupDrag
    with patch.object(viewport, "TraceWallBoundary", wraps = viewport.TraceWallBoundary) as trace:
        for index in range(10):
            viewport.UpdateInteraction(point(start) + point(30 + index * 1.37, 40 + index * .79),
                                       QtCore.Qt.KeyboardModifier.NoModifier)
            app.processEvents()
        assert trace.call_count == 0
    cachedPath = viewport.ConnectedWallPath(walls)
    cachedDimensions = viewport.WallDimensions(walls, cachedPath, [], cachedBoundary = True)
    # A cold rebuild must produce the same boundary and measurement positions.
    viewport.wallGeometryKey = viewport.dimensionCacheKey = None
    freshPath = viewport.ConnectedWallPath(walls)
    freshDimensions = viewport.WallDimensions(walls, freshPath, [], cachedBoundary = True)
    cachedPoints = {(round(cachedPath.elementAt(index).x, 4), round(cachedPath.elementAt(index).y, 4))
                    for index in range(cachedPath.elementCount())}
    freshPoints = {(round(freshPath.elementAt(index).x, 4), round(freshPath.elementAt(index).y, 4))
                   for index in range(freshPath.elementCount())}
    assert cachedPoints == freshPoints
    assert len(cachedDimensions) == len(freshDimensions)
    for old, new in zip(cachedDimensions, freshDimensions):
        assert QtCore.QLineF(old[0], new[0]).length() < 1e-4
        assert QtCore.QLineF(old[1], new[1]).length() < 1e-4
        assert old[2] == new[2]
    viewport.CancelInteraction()
    QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    viewport.ConnectedWallPath(walls)
    # Endpoint deformation and width changes must still rebuild the contours.
    with patch.object(viewport, "TraceWallBoundary", wraps = viewport.TraceWallBoundary) as trace:
        walls[0].firstVertex += point(30, 15)
        viewport.ConnectedWallPath(walls)
        assert trace.call_count == 1
        walls[0].width += 20
        viewport.ConnectedWallPath(walls)
        assert trace.call_count == 2
    # A stationary wall must not be translated along with the selected ring.
    stationary = Wall(point(-2500, -2500), point(-1500, -2500), 120)
    viewport.walls = walls + [stationary]
    viewport.ConnectedWallPath(viewport.walls)
    with patch.object(viewport, "TraceWallBoundary", wraps = viewport.TraceWallBoundary) as trace:
        for wall in walls:
            wall.firstVertex += point(80, 40)
            wall.secondVertex += point(80, 40)
        path = viewport.ConnectedWallPath(viewport.walls)
        assert trace.call_count == 1
        assert path.contains(viewport.WorldToViewport(point(-2000, -2500)))
    # Moving an unrelated wall must reuse the stationary construction, even
    # with snapping disabled and a large number of ordinary walls in the scene.
    moving = Wall(point(-400, 0), point(400, 0), 120)
    viewport.walls.append(moving)
    viewport.connectedEnabled = viewport.connectedVerticesEnabled = False
    viewport.SetSelection([(moving, None)])
    app.processEvents()
    start = viewport.WorldToViewport(point()).toPoint()
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    assert not viewport.groupDrag
    with patch.object(viewport, "BuildWallComponent", wraps = viewport.BuildWallComponent) as geometry, \
            patch.object(viewport, "BuildWallDimensions", wraps = viewport.BuildWallDimensions) as measurements:
        for index in range(5):
            viewport.UpdateInteraction(point(start) + point(25 + index * 2, 30 + index),
                                       QtCore.Qt.KeyboardModifier.NoModifier)
            app.processEvents()
        assert geometry.call_count >= 5
        assert measurements.call_count >= 5
        assert all(len(call.args[0]) == 1 and call.args[0][0] is moving for call in geometry.call_args_list)
        assert all(len(call.args[0]) == 1 and call.args[0][0] is moving for call in measurements.call_args_list)
    # Cached regions must render identically to a fully cold scene rebuild.
    cachedImage = viewport.grab().toImage()
    viewport.wallGeometryKey = viewport.dimensionCacheKey = viewport.materialGeometryKey = None
    viewport.wallComponentCache.clear()
    viewport.wallBoundaryCache.clear()
    viewport.wallDimensionComponentCache.clear()
    viewport.wallMaterialPathCache.clear()
    assert viewport.grab().toImage() == cachedImage
    wallComponents = viewport.wallGeometryComponents
    stairs = [Stair(point(-1000, -4000), point(-1000, -3000)),
              Stair(point(1000, -4000), point(1000, -3000))]
    viewport.ConnectedStairPath(stairs)
    assert viewport.wallGeometryComponents is wallComponents
    stairs[0].firstVertex += point(30, 0)
    viewport.ConnectedStairPath(stairs)
    assert viewport.wallGeometryComponents is wallComponents
    viewport.CancelInteraction()
    QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    main.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
