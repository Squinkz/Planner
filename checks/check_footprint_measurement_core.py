"""Exact numeric construction parity, cache identity and platform-free measurements."""
import importlib.abc
import itertools
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
from unittest.mock import patch

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))


def CheckWithoutQt():
    class CoreImportsOnly(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path = None, target = None):
            isCore = fullname in ("planner_app", "planner_app.geometry") or fullname.startswith("planner_app.geometry.")
            if not isCore and fullname.split(".")[0] not in sys.stdlib_module_names:
                raise AssertionError("Platform dependency: " + fullname)
    sys.meta_path.insert(0, CoreImportsOnly())
    from planner_app.geometry.footprints import WallBody, RectangleFootprint, ColumnPolygon, ColumnContains, FireplacePolygon, ColumnHandleCorners, PolygonAxes, FireplaceFootprint
    from planner_app.geometry.measurements import (MergeMeasurementSegments, FindMeasurementOwners,
        PrepareMeasurementPolygons, CoveredMeasurementSpans, OpeningProjection, BuildMeasurementSpan, ExposedMeasurementSpans, OpeningOnMeasuredSide)
    assert WallBody((0, 0), (10, 0), 2) == ((0, 1), (10, 1), (10, -1), (0, -1))
    assert RectangleFootprint((0, 0), (10, 0), 2)[0] == (0, -1, 10, 2)
    assert ColumnHandleCorners((0, 0), (10, 0), 2) == ((0, 1), (10, 1), (10, -1), (0, -1))
    assert PolygonAxes([(0, 0), (1, 0), (0, 1)])[0] == (0, 1)
    assert FireplaceFootprint((0, 0), (10, 0), (0, 1), 10, 4, 0)[0] == (0, -2, 10, 4)
    assert OpeningOnMeasuredSide((1, 1), (0, 0), (10, 0), False)
    assert not OpeningOnMeasuredSide((1, 1), (0, 0), (10, 0), True)
    assert len(ColumnPolygon((0, 10), 20)) >= 16
    assert ColumnContains((0, -10), (0, 10), 20, (0, 0))
    assert not ColumnContains((0, -10), (0, 10), 20, (11, 0))
    assert len(FireplacePolygon((0, 0), (10, 0), (1, 0), (0, 1), 10, 5, 0, False)) == 8
    assert len(MergeMeasurementSegments([(0, 0), (5, 0), (10, 0)])) == 1
    assert FindMeasurementOwners((0, 1), (10, 1), (1, 0), [(7, 0, 0, 1, 0, 10, 1, False)]) == [7]
    polygons = PrepareMeasurementPolygons([[(4, -2), (6, -2), (6, 2), (4, 2)]])
    covered = CoveredMeasurementSpans((0, 0), (1, 0), 10, polygons, .02)
    assert covered == [(3.99, 6.01)], covered
    assert ExposedMeasurementSpans((0, 0), (10, 0), polygons) == [((0, 0), (3.99, 0)), ((6.01, 0), (10, 0))]
    assert OpeningProjection((0, 0), (1, 0), (2, 0), (6, 0), True, True) == (4, 6)
    spans = BuildMeasurementSpan((0, 1), (10, 1), (1, 0), [1], [(2, 6)], [(2, 2, 6)],
                                 [(2, 6, 0, 1, 4, 0, 6, 0)])
    assert spans == [((0, 1), (2, 1), [1]), ((2, 3), (6, 3), [2]), ((6, 1), (10, 1), [1])]
    assert not any(name.startswith(("PySide", "PyQt")) for name in sys.modules)
    print("PASS: footprints and measurement calculations run with only the standard library")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtGui, QtWidgets
    from planner_app.models import (Wall, Pillar, Column, Fireplace, Door, PocketDoor, BarnDoor,
        SlidingDoor, BifoldDoor, Window, SilledWindow, CasementWindow, OpenDoorway)
    from planner_app.viewport.geometry import GeometryMixin, FootprintGeometry
    from planner_app.viewport.widget import DrawingViewport
    from planner_app.graphics.column import ColumnPolygon, ColumnContains, ColumnPath
    from planner_app.graphics.fireplace import FireplacePath
    from planner_app.geometry.footprints import WallBody
    from planner_app.catalog import LoadFurnishings
    from planner_app.project_codec import DecodeProject
    from fixtures import qt_footprint_measurement_reference_20261016 as frozen

    def Values(value):
        if isinstance(value, QtCore.QPointF):
            return value.x(), value.y()
        if isinstance(value, QtCore.QRectF):
            return value.getRect()
        if isinstance(value, QtGui.QPainterPath):
            return (value.fillRule(), tuple((value.elementAt(index).x, value.elementAt(index).y,
                                            value.elementAt(index).type) for index in range(value.elementCount())))
        if isinstance(value, (QtGui.QPolygonF, tuple, list)):
            return tuple(Values(entry) for entry in value)
        return value

    app = QtWidgets.QApplication([])
    point = QtCore.QPointF
    randomizer = random.Random(16102026)
    geometry = FootprintGeometry(.2)
    shapes = 0
    for index in range(1200):
        offset = point(1e8, -1e8) if index % 4 == 0 else point()
        first = offset + point(randomizer.uniform(-5000, 5000), randomizer.uniform(-5000, 5000))
        second = first + point(randomizer.uniform(-3000, 3000), randomizer.uniform(-3000, 3000))
        if index % 17 == 0:
            second = point(first)
        width = (0, -5, .00001, 100, 2500)[index % 5]
        scale = (.001, .2, 1.5)[index % 3]
        bodyFirst = point(first.x(), -first.y()) * scale
        bodySecond = point(second.x(), -second.y()) * scale
        delta = bodySecond - bodyFirst
        length = math.hypot(delta.x(), delta.y())
        expectedBody = ()
        if length >= 1e-10:
            normal = point(-delta.y(), delta.x()) * (width * scale / (2 * length))
            expectedBody = tuple(Values(vertex) for vertex in
                                 (bodyFirst + normal, bodySecond + normal, bodySecond - normal, bodyFirst - normal))
        assert WallBody(Values(bodyFirst), Values(bodySecond), width * scale) == expectedBody, ("wall body", index)
        shape = (Wall, Pillar, Column)[index % 3](first, second, width)
        if index % 7 == 0:
            shape = Fireplace(Wall(first, second, 240), .2, .7, bool(index % 2))
            shape.depth = 500
            shape.depthOffset = (index % 3 - 1) * 100
        for attribute in ("footprintCache", "ellipsePolygonCache"):
            if hasattr(shape, attribute):
                delattr(shape, attribute)
        with patch.object(GeometryMixin, "ObjectFootprint", frozen.ReferenceGeometry.ObjectFootprint):
            expected = geometry.ObjectFootprint(shape)
            expectedCorners = frozen.ReferenceGeometry.ObjectCorners(geometry, shape)
        if hasattr(shape, "footprintCache"):
            del shape.footprintCache
        actual = geometry.ObjectFootprint(shape)
        assert Values(actual) == Values(expected), ("footprint", index, actual, expected)
        assert geometry.ObjectFootprint(shape) is actual, ("warm identity", index)
        assert Values(geometry.ObjectCorners(shape)) == Values(expectedCorners), ("handles", index)
        if isinstance(shape, Column):
            for tolerance in (.1, .5, 5):
                if hasattr(shape, "ellipsePolygonCache"):
                    del shape.ellipsePolygonCache
                expected = frozen.ColumnPolygon(shape, tolerance)
                if hasattr(shape, "ellipsePolygonCache"):
                    del shape.ellipsePolygonCache
                assert Values(ColumnPolygon(shape, tolerance)) == Values(expected), ("ellipse", index, tolerance)
            assert Values(ColumnPath(shape)) == Values(frozen.ColumnPath(shape))
            for position in (first, second, (first + second) / 2, first + point(width, 0)):
                assert ColumnContains(shape, position) == frozen.ColumnContains(shape, position), ("contains", index)
        if isinstance(shape, Fireplace):
            assert Values(FireplacePath(shape)) == Values(frozen.FireplacePath(shape)), ("fireplace", index)
        shapes += 1

    definitions = {entry["key"]: entry for entry in LoadFurnishings()}
    actual, reference = DrawingViewport(), DrawingViewport()
    junctionCases = 0
    for degrees, widths, amount in itertools.product((30, 90, 135), ((120, 120), (120, 360)), (0, .5, 1)):
        radians = math.radians(degrees)
        walls = [Wall(point(), point(5000, 0), widths[0], amount, 0),
                 Wall(point(), point(math.cos(radians), math.sin(radians)) * 5000, widths[1], amount, 0)]
        for view in (actual, reference):
            view.walls, view.windows = walls, []
        with patch.object(GeometryMixin, "BuildWallComponent", frozen.ReferenceGeometry.BuildWallComponent):
            expectedPath = reference.ConnectedWallPath(walls)
        computed = actual.ConnectedWallPath(walls)
        assert Values(computed) == Values(expectedPath), ("junction API", degrees, widths, amount)
        assert [(id(owner), Values(polygon)) for owner, polygon in actual.wallFillPolygons] == [
                (id(owner), Values(polygon)) for owner, polygon in reference.wallFillPolygons], ("junction ownership", degrees, widths, amount)
        assert actual.ConnectedWallPath(walls) == computed
        junctionCases += 1
    frames = 0
    for name in ("rectangular_rooms", "angled_rooms", "dense_furnishings"):
        data = json.loads((root / "checks/fixtures/plans" / (name + ".plan")).read_text(encoding = "utf-8-sig"))
        objects, openings = DecodeProject(data, definitions)[:2]
        walls = [wall for wall in objects if type(wall) in (Wall, Pillar, Column)]
        moving = next(wall for wall in walls if type(wall) is Wall)
        origin = point(moving.firstVertex)
        for frame in range(8):
            moving.firstVertex = origin + point(frame * 17, frame * 11)
            for view in (actual, reference):
                view.walls, view.windows = walls, openings
                view.zoom = .4 + frame * .1
                view.panOffset = point(.37, .71)
                view.measurementSettings["doors"] = frame % 3
                view.measurementSettings["windows"] = (frame // 3) % 3
            with patch.object(GeometryMixin, "BuildWallComponent", frozen.ReferenceGeometry.BuildWallComponent):
                expectedPath = reference.ConnectedWallPath(walls)
            computed = actual.ConnectedWallPath(walls)
            assert Values(computed) == Values(expectedPath), ("body", name, frame)
            assert [(id(owner), Values(polygon)) for owner, polygon in actual.wallFillPolygons] == [
                    (id(owner), Values(polygon)) for owner, polygon in reference.wallFillPolygons], ("body owners", name, frame)
            expected = frozen.ReferenceGeometry.BuildWallDimensions(reference, walls, expectedPath, openings)
            dimensions = actual.BuildWallDimensions(walls, computed, openings)
            assert Values(dimensions) == Values(expected), ("dimensions", name, frame)
            assert [[id(owner) for owner in owners] for first, second, owners in dimensions] == [
                    [id(owner) for owner in owners] for first, second, owners in expected]
            assert actual.BuildWallDimensions(walls, computed, openings) is dimensions
            frames += 1
    # Rotated scenes, large offsets, all opening classes and side/selection policies.
    mixedCases = 0
    for case in range(48):
        transform = QtGui.QTransform().translate(1e8 if case % 2 else 0, -1e8 if case % 2 else 0).rotate(case * 7.3)
        corners = [transform.map(point(x, y)) for x, y in ((-2500, -1800), (2500, -1800), (2500, 1800), (-2500, 1800))]
        walls = [Wall(corners[index], corners[(index + 1) % 4], 200 + case) for index in range(4)]
        openings = [Door(walls[0], .05, .2), PocketDoor(walls[0], .3, .5),
                    BarnDoor(walls[1], .1, .3), SlidingDoor(walls[1], .5, .7),
                    Fireplace(walls[2], .2, .45), BifoldDoor(walls[2], .5, .7),
                    Window(walls[3], .05, .2), SilledWindow(walls[3], .35, .5),
                    CasementWindow(walls[3], .65, .85), OpenDoorway(walls[0], .75, .9)]
        openings[0].swingsOutwards = bool(case % 2)
        openings[1].hingeAtSecond = bool(case % 2)
        openings[2].measurementFlipped = bool(case % 2)
        openings[3].panelsFlipped = bool(case % 2)
        openings[4].depth = 800
        openings[4].depthOffset = (case % 3 - 1) * 200
        selection = [(walls[0], None)] if case % 3 == 1 else [(openings[4], None)] if case % 3 == 2 else []
        for view in (actual, reference):
            view.walls, view.windows = walls, openings
            # Selection overlays no longer alter world measurement geometry.
            view.SetSelection(selection if view is actual else [])
            view.zoom = (.003, .2, 1.5)[case % 3]
            view.panOffset = point(.37, .71)
            view.measurementSettings["doors"] = case % 3
            view.measurementSettings["windows"] = (case // 3) % 3
        boundary = actual.ConnectedWallPath(walls)
        cutters = [transform.map(QtGui.QPolygonF([point(-1500, -2000), point(-1000, -2000),
                                                point(-1000, -1500), point(-1500, -1500)]))]
        blockers = [transform.map(QtGui.QPolygonF([point(-3000, -1200), point(-2200, -1200),
                                                 point(-2200, -800), point(-3000, -800)]))]
        expected = frozen.ReferenceGeometry.BuildWallDimensions(reference, walls, boundary, openings,
            measureCaps = bool(case % 2), blockers = blockers, cutters = cutters)
        computed = actual.BuildWallDimensions(walls, boundary, openings,
            measureCaps = bool(case % 2), blockers = blockers, cutters = cutters)
        assert Values(computed) == Values(expected), ("mixed dimensions", case)
        assert [[id(owner) for owner in owners] for first, second, owners in computed] == [
                [id(owner) for owner in owners] for first, second, owners in expected]
        mixedCases += 1
    print(f"PASS: {shapes} exact footprints, handles and curves; {junctionCases} junction API cases; {frames} saved frames; {mixedCases} mixed measurement scenes; headless kernels")


if __name__ == "__main__":
    if "--without-qt" in sys.argv:
        CheckWithoutQt()
    else:
        Main()
