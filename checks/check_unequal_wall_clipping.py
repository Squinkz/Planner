"""Unequal two-wall joins follow intersecting edges, without exposed endpoint caps."""
import itertools
import math
import os
from pathlib import Path
import sys

workspace = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall
from planner_app.viewport.geometry import FootprintGeometry


def Main():
    app = QtWidgets.QApplication([])
    point = QtCore.QPointF
    count = 0
    for degrees, widths, rotation, scale in itertools.product((15, 25, 60, 90, 120, 150),
            ((120, 240), (240, 120), (80, 600)), (0, 37, 90), (.2, 1)):
        angle = math.radians(degrees)
        transform = QtGui.QTransform().rotate(rotation)
        a, b = point(1, 0), point(math.cos(angle), math.sin(angle))
        firstNormal, secondNormal = point(-a.y(), a.x()), point(-b.y(), b.x())
        # Independent expected six-sided strip: only far caps and the two
        # offset-edge intersections, never either endpoint's original cap.
        intersections = []
        for sign in (1, -1):
            first = firstNormal * (widths[0] / 2 * sign)
            second = secondNormal * (-widths[1] / 2 * sign)
            delta = second - first
            distance = (delta.x() * b.y() - delta.y() * b.x()) / (a.x() * b.y() - a.y() * b.x())
            intersections.append(first + a * distance)
        corners = [intersections[0], a * 6000 + firstNormal * (widths[0] / 2),
                   a * 6000 - firstNormal * (widths[0] / 2), intersections[1],
                   b * 6000 + secondNormal * (widths[1] / 2), b * 6000 - secondNormal * (widths[1] / 2)]
        corners = [transform.map(corner) for corner in corners]
        walls = [Wall(point(), transform.map(a * 6000), widths[0]),
                 Wall(point(), transform.map(b * 6000), widths[1])]
        for reverseOrder, reverseEndpoints in itertools.product((False, True), repeat = 2):
            ordered = list(reversed(walls)) if reverseOrder else list(walls)
            if reverseEndpoints:
                ordered = [Wall(wall.secondVertex, wall.firstVertex, wall.width) for wall in ordered]
            geometry = FootprintGeometry(scale)
            actual = geometry.ConnectedWallPath(ordered)
            expected = QtGui.QPainterPath()
            expected.addPolygon(QtGui.QPolygonF([geometry.WorldToViewport(corner) for corner in corners]))
            expected.closeSubpath()
            for field in ("left", "right", "top", "bottom"):
                assert abs(getattr(actual.boundingRect(), field)() - getattr(expected.boundingRect(), field)()) < 1e-5, (degrees, widths, field)
            for x, y in itertools.product(range(-500, 501, 73), repeat = 2):
                sample = geometry.WorldToViewport(transform.map(point(x + .37, y + .61)))
                assert actual.contains(sample) == expected.contains(sample), (degrees, widths, rotation, scale, sample)
            stroke = QtGui.QPainterPathStroker()
            stroke.setWidth(1e-5)
            tolerance = expected.united(stroke.createStroke(expected))
            for owner, polygon in geometry.wallFillPolygons:
                assert all(tolerance.contains(vertex) for vertex in polygon), (degrees, widths, "material extends beyond join")
            warm = geometry.wallGeometryPath
            geometry.ConnectedWallPath(ordered)
            assert geometry.wallGeometryPath is warm
            count += 1
    print(f"PASS: {count} unequal joins against independent edge-intersection outlines, materials and warm cache reuse")


if __name__ == "__main__":
    Main()
