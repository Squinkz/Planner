"""Exact numeric junction/trace parity, incremental histories and headless use."""
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
    from check_geometry_core import CheckWithoutQt as CheckPrimitives
    CheckPrimitives()
    from planner_app.geometry.junctions import BuildWallJunction
    from planner_app.geometry.boundaries import GroupContourBounds, TraceBoundaryContours
    polygons, joins, transitions, cuts, chamfers = BuildWallJunction((0, 0), [((1, 0), 2, "a"), ((0, 1), 2, "b")], [0, 0], .0001)
    assert polygons and joins and cuts.keys() == {"a", "b"}
    contour = (0, 0, 4, 4, ((0, 0, 4, 0), (4, 0, 4, 4), (4, 4, 0, 4), (0, 4, 0, 0)))
    cache = {}
    rings, state = TraceBoundaryContours([contour], (4, 4), edgeCache = cache)
    assert rings == [[(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)]]
    repeated, nextState = TraceBoundaryContours([contour], (4, 4), state = state, edgeCache = cache)
    assert rings == repeated
    assert all(nextState[2][edge] is segments for edge, segments in state[2].items())
    assert GroupContourBounds([(0, 0, 2, 2), (1, 1, 3, 3), (5, 5, 7, 7)]) == [[0, 1], [2]]
    print("PASS: junctions and incremental boundaries run without Qt or scene objects")


def JunctionValues(result):
    polygons, joins, transitions, cuts = result[:4]
    return ([[tuple(point.toTuple()) for point in polygon] for polygon in polygons],
            [(id(owner), [tuple(point.toTuple()) for point in polygon]) for owner, polygon in joins],
            [(id(owner), [tuple(point.toTuple()) for point in polygon]) for owner, polygon in transitions],
            {owner: [(tuple(joint.toTuple()), tuple(boundary.toTuple()), side) for joint, boundary, side in entries]
             for owner, entries in cuts.items()})


def PathValues(path):
    return (path.fillRule(), tuple((path.elementAt(index).x, path.elementAt(index).y, path.elementAt(index).type)
                                  for index in range(path.elementCount())))


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtGui, QtWidgets
    from planner_app.viewport.geometry import FootprintGeometry
    from fixtures.qt_junction_tracing_reference_20261016 import ReferenceGeometry
    from planner_app.geometry.boundaries import GroupContourBounds

    correctedJunction = FootprintGeometry.BuildWallJunction
    def LegacyJunction(self, joint, rays, chamfers):
        result = ReferenceGeometry.BuildWallJunction(self, joint, rays, [1 - value for value in chamfers])
        # Preserve the frozen patch/sector construction and tracing oracle.
        # The new fixed cap cuts deliberately correct the old unequal-width
        # footprint; their geometry has independent edge-intersection tests.
        footprintPlanes = correctedJunction(self, joint, list(rays), chamfers)[4]
        return (*result, footprintPlanes)

    class ReferenceWorkspace(FootprintGeometry):
        BuildWallJunction = LegacyJunction
        TraceWallBoundary = ReferenceGeometry.TraceWallBoundary
        TraceWallComponent = ReferenceGeometry.TraceWallComponent

    app = QtWidgets.QApplication([])
    point = QtCore.QPointF
    randomizer = random.Random(2026101602)
    angles = [(0, math.pi), (0, math.pi / 2), (0, math.pi, math.pi / 2),
              (0, math.pi - 1e-7), (0, math.pi + 1e-7), (0, math.pi, math.pi / 2, -math.pi / 2)]
    # Probe both sides of the local-transition distance cutoff for widths 10/20.
    critical = math.acos((-400 - math.sqrt(151200000)) / 12800)
    angles.extend((0, critical + delta) for delta in (-1e-12, -1e-14, 0, 1e-14, 1e-12))
    angles.extend(tuple(randomizer.uniform(-math.pi, math.pi) for ray in range(2 + index % 7)) for index in range(1000))
    for index, directions in enumerate(angles):
        scale = (.001, .2, 1.5)[index % 3]
        workspace = FootprintGeometry(scale)
        joint = point(1e8, -1e8) if index % 5 == 0 else point(20.3, -40.7)
        rays = [(point(math.cos(angle), math.sin(angle)), (10, 20, 50, 120)[ray % 4] * scale, object())
                for ray, angle in enumerate(directions)]
        # Zero chamfer must retain the frozen sharp-join geometry. Intermediate
        # chamfers deliberately differ and have independent analytic tests.
        miters = [0] * len(rays)
        expected = ReferenceGeometry.BuildWallJunction(workspace, joint, list(rays), [1] * len(rays))
        actualRays = list(rays)
        actual = workspace.BuildWallJunction(joint, actualRays, miters)
        assert JunctionValues(actual) == JunctionValues(expected), ("Junction", index)
        assert [id(ray[2]) for ray in actualRays] == [id(ray[2]) for ray in sorted(rays, key = lambda ray: math.atan2(ray[0].y(), ray[0].x()))]

    frames = 0
    for offset in (0, 1e8):
        for factor in (.001, 1, 100):
            actual, reference = FootprintGeometry(.2), ReferenceWorkspace(.2)
            for frame in range(24):
                source = [QtGui.QPolygonF([point(0, 0), point(400 + frame * 7, 0), point(400, 120), point(0, 120)]),
                          QtGui.QPolygonF([point(80, -120), point(170, -120), point(110 + frame, 300)]),
                          QtGui.QPolygonF([point(800, 100), point(920, 100), point(920, 220), point(800, 220)]),
                          QtGui.QPolygonF([point(20, 20), point(20, 80), point(80, 80), point(80, 20)])]
                if frame % 3 == 1:
                    source[1] = QtGui.QPolygonF(list(reversed(source[1])))
                if frame % 4 == 1:
                    source.pop()
                if frame % 4 == 2:
                    source.append(source[0])  # Duplicate winding and multiplicity.
                transform = QtGui.QTransform().translate(offset, -offset).scale(factor, factor)
                filled = QtGui.QPainterPath()
                filled.setFillRule(QtCore.Qt.FillRule.WindingFill if frame % 2 else QtCore.Qt.FillRule.OddEvenFill)
                polygons = [transform.map(polygon) for polygon in source]
                for polygon in polygons:
                    filled.addPolygon(polygon)
                    filled.closeSubpath()
                for joined in (False, True):
                    for traceKey in (None, ("frame", frame % 3)):
                        expected = reference.TraceWallComponent(filled, joined, traceKey = traceKey)
                        computed = actual.TraceWallComponent(filled, joined, traceKey = traceKey)
                        assert PathValues(computed) == PathValues(expected), ("Trace", offset, factor, frame, joined, traceKey)
                        frames += 1
                    expected = reference.TraceWallBoundary(filled, joined, traceKey = "grouped", sourcePolygons = polygons)
                    computed = actual.TraceWallBoundary(filled, joined, traceKey = "grouped", sourcePolygons = polygons)
                    assert PathValues(computed) == PathValues(expected), ("Groups", offset, factor, frame, joined)
                assert actual.wallTraceContextPoints == reference.wallTraceContextPoints
                assert len(actual.wallTraceContexts) <= 8 and actual.wallTraceContextPoints <= 32768

    for frame in range(100):
        bounds = [QtCore.QRectF(randomizer.uniform(-20, 20), randomizer.uniform(-20, 20),
                               randomizer.choice((0, 1, 4, 10)), randomizer.choice((0, 1, 4, 10))) for index in range(20)]
        # The numeric grouping must agree with the exact Qt intersection graph.
        groups = GroupContourBounds([(rect.left(), rect.top(), rect.right(), rect.bottom()) for rect in bounds])
        for first in range(len(bounds)):
            reachable, pending = {first}, [first]
            while pending:
                source = pending.pop()
                for second, rect in enumerate(bounds):
                    if second not in reachable and bounds[source].intersects(rect):
                        reachable.add(second)
                        pending.append(second)
            assert set(next(group for group in groups if first in group)) == reachable
    # Whole saved constructions also exercise nested column workspaces,
    # ownership ordering and warm component reuse across repeated edits.
    import json
    from contextlib import ExitStack
    from planner_app.catalog import LoadFurnishings
    from planner_app.project_codec import DecodeProject
    from planner_app.models import Wall, Pillar, Column
    from planner_app.viewport.geometry import GeometryMixin
    definitions = {item["key"]: item for item in LoadFurnishings()}
    for name in ("rectangular_rooms", "angled_rooms", "dense_furnishings"):
        data = json.loads((root / "checks/fixtures/plans" / (name + ".plan")).read_text(encoding = "utf-8-sig"))
        walls = [wall for wall in DecodeProject(data, definitions)[0] if type(wall) in (Wall, Pillar, Column)]
        moving = next(wall for wall in walls if type(wall) is Wall)
        origin = point(moving.firstVertex)
        actual, reference = FootprintGeometry(.2), ReferenceWorkspace(.2)
        for frame in range(8):
            moving.firstVertex = origin + point(frame * 17, frame * 11)
            with ExitStack() as overrides:
                for method in ("BuildWallJunction", "TraceWallBoundary", "TraceWallComponent"):
                    overrides.enter_context(patch.object(GeometryMixin, method,
                        LegacyJunction if method == "BuildWallJunction" else getattr(ReferenceGeometry, method)))
                expected = reference.ConnectedWallPath(walls)
            computed = actual.ConnectedWallPath(walls)
            assert PathValues(computed) == PathValues(expected), ("Saved outline", name, frame)
            expectedOwners = [(id(owner), [point.toTuple() for point in polygon]) for owner, polygon in reference.wallFillPolygons]
            actualOwners = [(id(owner), [point.toTuple() for point in polygon]) for owner, polygon in actual.wallFillPolygons]
            assert actualOwners == expectedOwners, ("Saved ownership", name, frame)
    print(f"PASS: {len(angles)} exact junctions, {frames} incremental trace comparisons, grouped paths, saved-scene ownership and headless cache reuse")


if __name__ == "__main__":
    if "--without-qt" in sys.argv:
        CheckWithoutQt()
    else:
        Main()
