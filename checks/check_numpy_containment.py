"""Batched bounds filtering preserves the frozen ordered containment decisions."""
import math
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner_app.models import Wall, Pillar, Column, Counter, Elevator, Stair, Arrow, MeasurementGuide, Railing
from planner_app.viewport import geometry
from planner_app.viewport.widget import DrawingViewport
from fixtures.native_paths_reference_20261017 import Load

Load("graphics/arrows.py")
ReferenceGeometry = Load("viewport/geometry.py").GeometryMixin


def MakeWalls(count, seed = 20261030):
    randomizer = random.Random(seed)
    point = QtCore.QPointF
    walls = []
    for index in range(count):
        angle = randomizer.uniform(-math.pi, math.pi)
        length = randomizer.uniform(100, 3000)
        center = point(randomizer.uniform(-10000, 10000), randomizer.uniform(-10000, 10000))
        direction = point(math.cos(angle), math.sin(angle)) * length / 2
        kind = (Wall, Wall, Pillar, Counter, Column, Elevator)[index % 6]
        wall = kind(center - direction, center + direction, randomizer.uniform(100, 800))
        if walls and index % 11 == 0:
            previous = walls[-1]
            wall = type(previous)(point(previous.secondVertex), point(previous.firstVertex), previous.width)
        elif walls and index % 13 == 0:
            previous = walls[-1]
            center = (previous.firstVertex + previous.secondVertex) / 2
            direction = (previous.secondVertex - previous.firstVertex) / 4
            wall = Wall(center - direction, center + direction, previous.width / 3)
        elif index % 37 == 0:
            wall.secondVertex = point(wall.firstVertex)
        walls.append(wall)
    return walls


def Compare(view, walls):
    view.containedWallKey = None
    expected = ReferenceGeometry.ContainedWalls(view, walls)
    view.containedWallKey = None
    actual = view.ContainedWalls(walls)
    assert actual == expected, ([id(wall) for wall in actual], [id(wall) for wall in expected])
    with patch.object(geometry, "LoadNumPy", side_effect = AssertionError("Warm containment rebuilt arrays")):
        assert view.ContainedWalls(walls) is actual
    return actual


def Main():
    app = QtWidgets.QApplication([])
    view = DrawingViewport()
    view.performanceTimer.stop()
    for count in (0, 1, 2, 31, 63):
        with patch.object(geometry, "LoadNumPy", side_effect = AssertionError("Small scenes initialized NumPy")):
            Compare(view, MakeWalls(count))
    assert "numpy" not in sys.modules, "Small scene startup imported NumPy"
    comparisons = 5
    point = QtCore.QPointF
    for count in (64, 65, 127, 128, 129, 404, 1024):
        for offset in (point(), point(1e8, -1e8)):
            walls = MakeWalls(count)
            for wall in walls:
                wall.firstVertex += offset
                wall.secondVertex += offset
            walls += [kind(offset, offset + point(1000, 0), 500)
                      for kind in (Stair, Arrow, MeasurementGuide, Railing)]
            view.walls = walls
            Compare(view, walls)
            Compare(view, list(reversed(walls)))
            Compare(view, walls[::2])
            # Warm cache invalidation for geometry, membership and ordering.
            walls[1].width *= 2
            walls[2].firstVertex += point(17, -29)
            Compare(view, walls)
            walls.append(Wall(offset + point(-10000, 0), offset + point(10000, 0), 10000))
            Compare(view, walls)
            walls.pop(3)
            Compare(view, walls)
            comparisons += 6
    # Exercise tolerance boundaries, duplicate ownership and bounds-contained
    # diagonal shapes that must still fail the precise polygon test.
    for offset in (point(), point(1e8, -1e8)):
        for delta in (0, .009999, .01, .010001, -.01):
            walls = MakeWalls(128)
            for wall in walls:
                wall.firstVertex += offset + point(40000, 40000)
                wall.secondVertex += offset + point(40000, 40000)
            outer = Wall(offset + point(-1000, -1000), offset + point(1000, 1000), 400)
            inner = Wall(offset + point(-300, -300), offset + point(300, 300), 120)
            crossing = Wall(offset + point(-200, 200), offset + point(200, -200), 120)
            aligned = Wall(offset + point(-900, 100 + delta), offset + point(900, 100 + delta), 200)
            duplicate = Wall(point(outer.secondVertex), point(outer.firstVertex), outer.width)
            walls.extend((outer, inner, crossing, aligned, duplicate))
            result = Compare(view, walls)
            assert inner in result and duplicate in result and crossing not in result
            comparisons += 1
    # Conservative fallback preserves Qt's semantics even for unusual rectangles.
    walls = MakeWalls(65)
    original = view.ObjectFootprint
    for unusual in (QtCore.QRectF(30, 40, -10, -20), QtCore.QRectF(float("nan"), 0, 10, 20)):
        def Footprint(wall):
            bounds, corners, axes = original(wall)
            return (unusual, corners, axes) if wall is walls[1] else (bounds, corners, axes)
        with patch.object(view, "ObjectFootprint", Footprint):
            Compare(view, walls)
        comparisons += 1
    view.close()
    assert QtWidgets.QApplication.instance() is app
    print(f"{comparisons} containment matrices match frozen results, ordering, cache reuse and invalidation")


if __name__ == "__main__":
    Main()
