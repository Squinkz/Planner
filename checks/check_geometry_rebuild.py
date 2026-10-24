"""Local tracing matches cold geometry; faster clipping matches the original."""
import math
import os
from pathlib import Path
import random
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Pillar, Column
from planner_app.viewport.geometry import FootprintGeometry
from planner_app.viewport.polygon_clipping import SubtractConvexPolygon


def OriginalSplit(points, first, second, orientation):
    inside, outside = [], []
    edge = second - first
    for index, point in enumerate(points):
        nextPoint = points[(index + 1) % len(points)]
        offset, nextOffset = point - first, nextPoint - first
        distance = (edge.x() * offset.y() - edge.y() * offset.x()) * orientation
        nextDistance = (edge.x() * nextOffset.y() - edge.y() * nextOffset.x()) * orientation
        (inside if distance >= 0 else outside).append(point)
        if (distance >= 0) != (nextDistance >= 0):
            crossing = point + (nextPoint - point) * (distance / (distance - nextDistance))
            inside.append(crossing)
            outside.append(crossing)
    return inside, outside


def OriginalSubtract(points, cutter):
    if not QtGui.QPolygonF(points).boundingRect().intersects(QtGui.QPolygonF(cutter).boundingRect()):
        return [points]
    area = sum(cutter[index].x() * cutter[(index + 1) % len(cutter)].y() -
               cutter[(index + 1) % len(cutter)].x() * cutter[index].y() for index in range(len(cutter)))
    if abs(area) < 1e-9:
        return [points]
    orientation = 1 if area > 0 else -1
    fragments, remaining = [], list(points)
    for index, first in enumerate(cutter):
        if len(remaining) < 3:
            break
        remaining, outside = OriginalSplit(remaining, first, cutter[(index + 1) % len(cutter)], orientation)
        if len(outside) >= 3:
            area = abs(sum(outside[index].x() * outside[(index + 1) % len(outside)].y() -
                           outside[(index + 1) % len(outside)].x() * outside[index].y() for index in range(len(outside))))
            if area > 1e-7:
                fragments.append(outside)
    return fragments


def Main():
    app = QtWidgets.QApplication([])
    point = QtCore.QPointF
    randomizer = random.Random(20261016)
    for index in range(500):
        factor = (1e-4, 1, 1e7)[index % 3]
        center = point(randomizer.uniform(-10, 10), randomizer.uniform(-10, 10)) * factor
        shapes = []
        for count in (4, 3 + index % 6):
            angle = randomizer.uniform(0, math.tau)
            width, height = randomizer.uniform(.01, 10) * factor, randomizer.uniform(.01, 10) * factor
            offset = center + point(randomizer.uniform(-2, 2), randomizer.uniform(-2, 2)) * factor
            vertices = [offset + point(math.cos(angle + vertex * math.tau / count) * width,
                                      math.sin(angle + vertex * math.tau / count) * height) for vertex in range(count)]
            shapes.append(vertices if index % 2 else list(reversed(vertices)))
        assert SubtractConvexPolygon(*shapes) == OriginalSubtract(*shapes), index
    degenerate = [point(), point(1, 0), point(2, 0)]
    assert SubtractConvexPolygon(degenerate, degenerate) == OriginalSubtract(degenerate, degenerate)

    for scale in (.001, .2, 1.5):
        for offset in (point(), point(1e8, -1e8)):
            corners = [point(-2000, -1500), point(2000, -1500), point(2000, 1500), point(-2000, 1500)]
            walls = [Wall(offset + corners[index], offset + corners[(index + 1) % 4], 200 + index * 30) for index in range(4)]
            moving = Wall(offset + point(-500, 1800), offset + point(-500, -1700), 240)
            # A locally changed crossing can affect intersections far along a
            # stationary span; its complete edge must remain in the trace index.
            walls += [moving, Wall(offset + point(-3000, 10), offset + point(3200, 10.0001), 150),
                      Wall(offset + point(1700, -2000), offset + point(1700, 2000), 180),
                      Pillar(offset + point(-500, -100), offset + point(-500, 200), 450)]
            warm = FootprintGeometry(scale)
            warm.ConnectedWallPath(walls)
            for index in range(12):
                moving.secondVertex = offset + point(-800 + index * 150, -1700 + index * 70)
                if index == 3:
                    walls[-1].width = 600
                if index == 5:
                    walls[1].firstMiter = .4
                if index == 7:
                    walls.append(Column(offset + point(100, -200), offset + point(100, 200), 500))
                if index == 9:
                    walls.remove(moving)
                actual = warm.ConnectedWallPath(walls)
                cold = FootprintGeometry(scale)
                assert actual == cold.ConnectedWallPath(walls), (scale, offset, index)
                assert warm.wallFillPolygons == cold.wallFillPolygons, (scale, offset, index)

    owner = FootprintGeometry(.2)
    child = FootprintGeometry(.2, owner)
    assert owner.wallTraceContexts is not child.wallTraceContexts
    polygon = QtGui.QPainterPath()
    polygon.addRect(0, 0, 20, 10)
    for index in range(24):
        for joinContours in (True, False):
            actual = owner.TraceWallComponent(polygon, joinContours, traceKey = index)
            assert actual == FootprintGeometry(.2).TraceWallComponent(polygon, joinContours)
        assert len(owner.wallTraceContexts) <= 8
        assert owner.wallTraceContextPoints == sum(size for state, size in owner.wallTraceContexts.values())
    large = QtGui.QPainterPath()
    for index in range(1800):
        large.addRect((index % 45) * 10, (index // 45) * 10, 1, 1)
    owner.TraceWallComponent(large, traceKey = "oversized")
    assert "oversized" not in owner.wallTraceContexts
    assert owner.wallTraceContextPoints <= 32768
    print("PASS: original clipping parity, cold-build geometry/ownership parity, trace isolation and bounded contexts")


if __name__ == "__main__":
    Main()
