"""Headless numeric geometry and exact parity with frozen Qt primitives."""
import importlib.abc
import math
import os
from pathlib import Path
import random
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))


def CheckWithoutQt():
    class CoreImportsOnly(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path = None, target = None):
            isCore = fullname in ("planner_app", "planner_app.geometry") or fullname.startswith("planner_app.geometry.")
            if not isCore and fullname.split(".")[0] not in sys.stdlib_module_names:
                raise AssertionError("Numeric geometry imported a platform dependency: " + fullname)
    sys.meta_path.insert(0, CoreImportsOnly())
    from planner_app.geometry.polygons import SplitPolygon, SubtractConvexPolygon
    from planner_app.geometry.spatial_index import BoundsIndex

    subject = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    cutter = [(2.0, -1.0), (5.0, -1.0), (5.0, 5.0), (2.0, 5.0)]
    assert SubtractConvexPolygon(subject, cutter) == [[(0.0, 0.0), (2.0, 0.0), (2.0, 4.0), (0.0, 4.0)]]
    assert SplitPolygon(subject, (2.0, -1.0), (2.0, 5.0), 1)[0] == [
        (0.0, 0.0), (2.0, 0.0), (2.0, 4.0), (0.0, 4.0)]
    assert subject == [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    index = BoundsIndex(10)
    index.Insert((-1e8, -1e8, 1e8, 1e8), "large")
    index.Insert((0, 0, 4, 4), "first")
    index.Insert((2, 2, 6, 6), "second")
    index.Insert((4, 0, 4, 4), "empty")
    assert index.Query((1, 1, 5, 5)) == ["large", "first", "second"]
    assert index.Query((4, 0, 5, 1)) == ["large"]
    assert len(index.buckets) <= 4
    assert not any(name.startswith(("PySide", "PyQt")) for name in sys.modules)
    print("PASS: numeric geometry runs without Qt, models, widgets or rendering")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore
    from planner_app.geometry.polygons import SplitPolygon as SplitCoordinates, SubtractConvexPolygon as SubtractCoordinates
    from planner_app.geometry.spatial_index import BoundsIndex as CoordinateIndex
    from planner_app.viewport.polygon_clipping import SplitPolygon, SubtractConvexPolygon
    from planner_app.viewport.spatial_index import BoundsIndex
    from fixtures.qt_geometry_primitives_20261016 import SplitPolygon as OriginalSplit, SubtractConvexPolygon as OriginalSubtract
    from fixtures.qt_geometry_primitives_20261016 import BoundsIndex as OriginalIndex

    randomizer = random.Random(20261016)
    examples = [([], []), ([(0, 0)], [(0, 0), (2, 0), (0, 2)]),
                ([(0, 0), (1, 0), (2, 0)], [(0, 0), (1, 0), (2, 0)]),
                ([(0, 0), (2, 0), (2, 2), (0, 2)], [(2, 0), (4, 0), (4, 2), (2, 2)]),
                ([(0, 0), (2, 0), (2, 2), (0, 2)], [(0, 0), (2, 0), (2, 2), (0, 2)]),
                ([(-1e16, -1.0), (1.0, -1.0), (1.0, 1.0), (-1e16, 1.0)],
                 [(.5, -2.0), (2.0, -2.0), (2.0, 2.0), (.5, 2.0)])]
    for index in range(1500):
        factor = (1e-5, .2, 1, 1e7)[index % 4]
        offset = (1e8, -1e8) if index % 5 == 0 else (0, 0)
        centerX, centerY = randomizer.uniform(-10, 10) * factor + offset[0], randomizer.uniform(-10, 10) * factor + offset[1]
        shapes = []
        for count in (4, 3 + index % 7):
            angle = randomizer.uniform(0, math.tau)
            width, height = randomizer.uniform(.01, 10) * factor, randomizer.uniform(.01, 10) * factor
            x, y = centerX + randomizer.uniform(-2, 2) * factor, centerY + randomizer.uniform(-2, 2) * factor
            vertices = [(x + math.cos(angle + vertex * math.tau / count) * width,
                         y + math.sin(angle + vertex * math.tau / count) * height) for vertex in range(count)]
            shapes.append(vertices if index % 2 else list(reversed(vertices)))
        examples.append(shapes)
    for subject, cutter in examples:
        points = [QtCore.QPointF(x, y) for x, y in subject]
        clip = [QtCore.QPointF(x, y) for x, y in cutter]
        expected = OriginalSubtract(points, clip)
        actual = SubtractConvexPolygon(points, clip)
        numeric = SubtractCoordinates(subject, cutter)
        assert actual == expected, (subject, cutter)
        assert numeric == [[(point.x(), point.y()) for point in polygon] for polygon in expected]
        if len(expected) == 1 and expected[0] is points:
            assert actual[0] is points
            assert numeric[0] is subject
        if cutter:
            for orientation in (-1, 0, 1):
                expected = OriginalSplit(points, clip[0], clip[-1], orientation)
                assert SplitPolygon(points, clip[0], clip[-1], orientation) == expected
                assert SplitCoordinates(subject, cutter[0], cutter[-1], orientation) == tuple(
                    [(point.x(), point.y()) for point in polygon] for polygon in expected)

    queries = [QtCore.QRectF(0, 0, 0, 0), QtCore.QRectF(-1e8, -1e8, 2e8, 2e8),
               QtCore.QRectF(0, 0, 4, 4), QtCore.QRectF(4, 0, 4, 4)]
    queries.extend(QtCore.QRectF(randomizer.uniform(-500, 500), randomizer.uniform(-500, 500),
                                randomizer.uniform(-120, 120), randomizer.uniform(-120, 120)) for index in range(300))
    assert CoordinateIndex(-1).cellSize == OriginalIndex(-1).cellSize == 1e-5
    for cellSize in (.1, 1, 17, 1000):
        original, adapter, numeric = OriginalIndex(cellSize), BoundsIndex(cellSize), CoordinateIndex(cellSize)
        for index, bounds in enumerate(queries):
            original.Insert(bounds.normalized(), index)
            adapter.Insert(bounds, index)
            numeric.Insert((bounds.left(), bounds.top(), bounds.right(), bounds.bottom()), index)
        assert adapter.buckets == numeric.buckets == original.buckets
        assert adapter.largeEntries == numeric.largeEntries == original.largeEntries
        for bounds in queries:
            expected = original.Query(bounds.normalized())
            assert adapter.Query(bounds) == expected
            assert numeric.Query((bounds.left(), bounds.top(), bounds.right(), bounds.bottom())) == expected
    print("PASS: headless execution, 1,506 polygon cases, split parity, ordered spatial queries and bounded oversized entries")


if __name__ == "__main__":
    if "--without-qt" in sys.argv:
        CheckWithoutQt()
    else:
        Main()
