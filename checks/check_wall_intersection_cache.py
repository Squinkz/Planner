"""Crossing walls reuse stationary joins without changing outlines or dimensions."""
import math
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import DrawingViewport, Wall


def Main():
    app = QtWidgets.QApplication([])
    viewport = DrawingViewport()
    reference = DrawingViewport()
    for view in (viewport, reference):
        view.resize(1200, 900)
        view.panOffset = QtCore.QPointF(.37, .71)
    point = QtCore.QPointF
    vertices = [point(math.cos(index * math.tau / 63) * 1500,
                      math.sin(index * math.tau / 63) * 1500) for index in range(63)]
    ring = [Wall(vertices[index], vertices[(index + 1) % 63], 120) for index in range(63)]
    moving = Wall(point(500, 0), point(1300, 0), 240)
    walls = ring + [moving]
    viewport.ConnectedWallPath(walls)
    with patch.object(viewport, "BuildWallComponent", wraps = viewport.BuildWallComponent) as builder:
        for position in (point(1410, 0), point(1480, 15), point(1530, 35), point(1700, 100),
                         point(-1800, -400), point(700, 500), point(1489.9999975, 0)):
            moving.secondVertex = position
            path = viewport.ConnectedWallPath(walls)
            dimensions = viewport.WallDimensions(walls, path, [], cachedBoundary = True)
            # The reference builds every wall together without component reuse.
            reference.wallBoundaryCache.clear()
            reference.wallBoundaryEdgeCache.clear()
            reference.wallTraceState = None
            reference.wallTraceContexts.clear()
            reference.wallTraceContextPoints = 0
            fresh = reference.BuildWallComponent(walls, True)
            freshDimensions = reference.BuildWallDimensions(walls, fresh, [])
            images = []
            for outline in (path, fresh):
                image = QtGui.QImage(1200, 900, QtGui.QImage.Format.Format_ARGB32)
                image.fill(QtCore.Qt.GlobalColor.black)
                painter = QtGui.QPainter(image)
                painter.fillPath(outline, QtCore.Qt.GlobalColor.white)
                painter.setPen(QtCore.Qt.GlobalColor.red)
                painter.drawPath(outline)
                painter.end()
                images.append(image)
            assert images[0] == images[1], position
            values = [sorted((round(first.x(), 3), round(first.y(), 3), round(second.x(), 3), round(second.y(), 3),
                              tuple(id(owner) for owner in owners)) for first, second, owners in entries)
                      for entries in (dimensions, freshDimensions)]
            assert values[0] == values[1], position
        assert all(len(call.args[0]) == 1 and call.args[0][0] is moving for call in builder.call_args_list)
    # An actual shared endpoint must still rebuild the combined miter junction.
    moving.secondVertex = vertices[0]
    with patch.object(viewport, "BuildWallComponent", wraps = viewport.BuildWallComponent) as builder:
        viewport.ConnectedWallPath(walls)
        assert any(len(call.args[0]) == 64 for call in builder.call_args_list)
    print("PASS: tangent, crossing, nested, fractional and shared-vertex wall geometry.")


if __name__ == "__main__":
    Main()
