"""Joined stairs measure exterior contours exactly as counters do."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Stair, Counter


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    v = main.viewport
    point = QtCore.QPointF
    for rotation in (0, 37, 143):
        for angle in (82, 90, 105, 135):
            transform = QtGui.QTransform().rotate(rotation)
            origin = point(13.375, -17.125)
            first = origin + transform.map(point(-5700, 0))
            last = origin + transform.map(point(math.cos(math.radians(angle)), math.sin(math.radians(angle))) * 2800)
            for widths in ((1000, 1000), (1000, 800)):
                stairs = [Stair(first, origin, widths[0]), Stair(origin, last, widths[1])]
                counters = [Counter(first, origin, widths[0]), Counter(origin, last, widths[1])]
                for zoom in (.5, 2):
                    v.zoom = zoom
                    v.walls = counters
                    counterPath, expected, polygons = v.ConnectedCounterPath(counters)
                    v.walls = stairs
                    v.ConnectedStairPath(stairs)
                    oldGeometry = QtGui.QPainterPath(v.stairGeometryPath)
                    oldOutline = QtGui.QPainterPath(v.stairOutlinePath)
                    actual = v.StairDimensions(stairs)
                    assert v.stairGeometryPath == oldGeometry and v.stairOutlinePath == oldOutline
                    spans = []
                    for dimensions in (expected, actual):
                        spans.append(sorted(tuple(sorted(((round(first.x(), 4), round(first.y(), 4)),
                                                          (round(second.x(), 4), round(second.y(), 4)))))
                                            for first, second, owners in dimensions))
                    assert spans[0] == spans[1], (rotation, angle, widths, spans)
                    # Every measured edge separates filled and empty space;
                    # internal landing/cap edges must never receive dimensions.
                    for first, second, owners in actual:
                        midpoint = (first + second) / 2
                        direction = second - first
                        normal = point(-direction.y(), direction.x()) / QtCore.QLineF(first, second).length() * .01
                        assert counterPath.contains(v.WorldToViewport(midpoint + normal)) != counterPath.contains(v.WorldToViewport(midpoint - normal))
    main.close()


if __name__ == "__main__":
    Main()
