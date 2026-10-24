"""Joined material regions cover their complete footprint, including short bodies."""
import itertools
import math
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall
from planner_app.viewport.widget import DrawingViewport


def Main():
    app = QtWidgets.QApplication([])
    v = DrawingViewport()
    cases = (((0, 30), (80, 240)), ((0, 120, 240), (120, 600, 240)),
             ((0, 1), (240, 240)), ((0, 90, 180, 270), (80, 600, 240, 1000)))
    for (angles, widths), rotation, miter, length in itertools.product(cases, (0, 37), (0, .5, 1), (400, 3000)):
        walls = []
        for angle, width in zip(angles, widths):
            radians = math.radians(angle + rotation)
            walls.append(Wall(QtCore.QPointF(), QtCore.QPointF(math.cos(radians) * length,
                                                            math.sin(radians) * length), width, miter, miter))
        v.ConnectedWallPath(walls, traceContours = False)
        regions = []
        for owner, polygon in v.wallFillPolygons:
            path = QtGui.QPainterPath()
            path.addPolygon(polygon)
            path.closeSubpath()
            regions.append(path)
        bounds = v.wallGeometryPath.boundingRect()
        for x, y in itertools.product(range(25), repeat = 2):
            point = QtCore.QPointF(bounds.left() + bounds.width() * (x + .37) / 25,
                                  bounds.top() + bounds.height() * (y + .61) / 25)
            if v.wallGeometryPath.contains(point):
                assert any(path.contains(point) for path in regions), (angles, widths, rotation, miter, length, point)
    # Both-end clipping of a short middle segment must also retain material.
    v.walls = [Wall(QtCore.QPointF(-500, 0), QtCore.QPointF(0, 0), 240),
               Wall(QtCore.QPointF(), QtCore.QPointF(150, 50), 120),
               Wall(QtCore.QPointF(150, 50), QtCore.QPointF(150, 900), 600)]
    path = v.ConnectedWallPath(v.walls)
    assert not path.isEmpty()
    v.close()
    print("PASS: complete material ownership across acute, multi-branch, beveled and short-wall junctions")


if __name__ == "__main__":
    Main()
