"""Mathematical counterexamples for joined geometry, tolerances and distant origins."""
import copy
import math
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))

from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.export_bounds import AutomaticBounds
from planner_app.furnishing_parts import FurnishingCollisionFootprints
from planner_app.geometry.attachments import OpeningWithinWall, OpeningIntervalsOverlap
from planner_app.geometry.collisions import FootprintsOverlap, SignificantPathOverlap
from planner_app.geometry.compound_furnishings import PlanCompoundFootprints
from planner_app.geometry.footprints import PolygonAxes
from planner_app.geometry.polygons import PolygonTwiceArea, SubtractConvexPolygon
from planner_app.geometry.reserved_doors import ReservedDoorWithinHost
from planner_app.geometry_recovery import OpeningProblem, PrepareGeometryValidation
from planner_app.models import Wall, Pillar, Column, Stair, Counter, Railing, Furnishing, Window
from planner_app.project_codec import DecodeProject


def CheckChamferCollision(main):
    v = main.viewport
    p = QtCore.QPointF
    first = Wall(p(), p(2000, 0), 200, 1, 0)
    second = Wall(p(), p(0, 2000), 1000, 1, 0)
    furnishing = Furnishing(v.furnishingDefinitions["null"], p(-700, -150))
    furnishing.width = 500
    furnishing.firstVertex, furnishing.secondVertex = p(-700, -400), p(-700, 100)
    InstallScene(main, [first, second, furnishing])
    assert v.ObjectsOverlap(second, furnishing, 1), "Counterexample must intersect the untrimmed body"
    assert not v.JoinedObjectsOverlap(second, furnishing, 1)
    assert not v.JoinedObjectsOverlap(furnishing, second, 1)
    assert v.FurnishingFits(furnishing)
    # Warm drawing/collision caches must translate the cut planes with the walls.
    for delta in (p(), p(5000, -1234), p(-5000, 1234)):
        for obj in (first, second, furnishing):
            obj.firstVertex += delta
            obj.secondVertex += delta
        v.ConnectedWallPath(v.walls)
        assert not v.JoinedObjectsOverlap(second, furnishing, 1)
        assert v.FurnishingFits(furnishing)
    # Removing the cut restores the physical collision and invalidates caches.
    first.firstMiter = second.firstMiter = 0
    assert v.JoinedObjectsOverlap(second, furnishing, 1)
    assert not v.FurnishingFits(furnishing)


def CheckMiterExportBounds(main):
    v = main.viewport
    p = QtCore.QPointF
    angle = math.radians(5)
    for kind in (Wall, Stair, Counter, Railing):
        first = kind(p(), p(5000, 0), 200)
        second = kind(p(), p(5000 * math.cos(angle), 5000 * math.sin(angle)), 200)
        InstallScene(main, [first, second])
        v.ConnectedWallPath([first, second])
        retainedKey, retainedPath = v.wallGeometryKey, v.wallGeometryPath
        bounds = AutomaticBounds(v)
        expectedLeft = -100 / math.tan(angle / 2) - 1000
        assert math.isclose(bounds[0], expectedLeft, rel_tol = 0, abs_tol = 1e-7), (kind, bounds)
        assert v.wallGeometryKey == retainedKey and v.wallGeometryPath is retainedPath
        oldZoom = v.zoom
        v.zoom *= 3
        assert AutomaticBounds(v) == bounds, "World export bounds changed with viewport zoom"
        v.zoom = oldZoom


def CheckMiterClearance(main):
    v = main.viewport
    p = QtCore.QPointF
    for intrusion in (0, .5, 1, 3, 5):
        first = Wall(p(), p(2000, 0), 200)
        second = Wall(p(), p(0, 2000), 200)
        coordinate = -350 + intrusion
        furnishing = Furnishing(v.furnishingDefinitions["null"], p(coordinate, coordinate))
        furnishing.width = 500
        furnishing.firstVertex = p(coordinate, coordinate - 250)
        furnishing.secondVertex = p(coordinate, coordinate + 250)
        InstallScene(main, [first, second, furnishing])
        assert not v.ObjectsOverlap(first, furnishing, 1) and not v.ObjectsOverlap(second, furnishing, 1)
        expected = intrusion >= 3
        for wall in (first, second):
            assert v.JoinedObjectsOverlap(wall, furnishing, 1) == expected, intrusion
            assert v.JoinedObjectsOverlap(furnishing, wall, 1) == expected, intrusion
        assert v.FurnishingFits(furnishing) != expected


def CheckContainmentOrder(main):
    v = main.viewport
    p = QtCore.QPointF
    column = Column(p(0, -500), p(0, 500), 1000)
    pillar = Pillar(p(0, -500), p(0, 500), 1000)
    for objects in ([column, pillar], [pillar, column]):
        InstallScene(main, objects)
        assert [id(obj) for obj in v.ContainedWalls()] == [id(column)]
    duplicate = Pillar(p(0, -500), p(0, 500), 1000)
    for objects in ([pillar, duplicate], [duplicate, pillar]):
        InstallScene(main, objects)
        assert [id(obj) for obj in v.ContainedWalls()] == [id(objects[1])]


def CheckTranslatedAreas(main):
    v = main.viewport
    p = QtCore.QPointF
    for offset in (0, 1e9, 1e12 - 1000):
        subject = [(offset + x, offset + y) for x, y in ((0, 0), (100, 0), (100, 100), (0, 100))]
        cutter = [(offset + x, offset + y) for x, y in ((20, 20), (30, 20), (30, 30), (20, 30))]
        for reverse in (False, True):
            polygon = list(reversed(cutter)) if reverse else cutter
            fragments = SubtractConvexPolygon(subject, polygon)
            assert math.isclose(sum(abs(PolygonTwiceArea(piece)) / 2 for piece in fragments), 9900,
                                rel_tol = 0, abs_tol = 1e-7)
            assert abs(PolygonTwiceArea(polygon)) == 200
            assert SignificantPathOverlap([subject], 1)
            assert SignificantPathOverlap([list(reversed(subject))], 1)
            normalized = v.PreparedWallPolygon(QtGui.QPolygonF([p(*point) for point in reversed(subject)]))[2]
            assert PolygonTwiceArea([(point.x(), point.y()) for point in normalized]) > 0
    assert not SignificantPathOverlap([[], [(0, 0), (1, 1)]], 1)


def CheckPositionEdit(main):
    v = main.viewport
    p = QtCore.QPointF
    coordinate = 1e12 - 1000
    furnishing = Furnishing(v.furnishingDefinitions["null"], p(coordinate, 0))
    InstallScene(main, [furnishing])
    v.unitsMode = "Millimeters"
    v.SetSelection([(furnishing, None)])
    main.EditObjectPosition("x", coordinate + 100)
    assert ((furnishing.firstVertex + furnishing.secondVertex) / 2).x() == coordinate + 100
    assert len(v.undoHistory) == 1
    v.Undo()
    assert ((furnishing.firstVertex + furnishing.secondVertex) / 2).x() == coordinate
    v.Redo()
    assert ((furnishing.firstVertex + furnishing.secondVertex) / 2).x() == coordinate + 100


def CheckOpeningClearance(main):
    v = main.viewport
    p = QtCore.QPointF
    for parentLength, firstStart, firstEnd, secondEnd in ((1000, 100, 300, 495), (1e9, 1000, 1900, 2795)):
        parent = Wall(p(), p(parentLength, 0), 200)
        first = Window(parent, firstStart / parentLength, firstEnd / parentLength)
        second = Window(parent, (firstEnd - 5) / parentLength, secondEnd / parentLength)
        InstallScene(main, [parent, first, second])
        assert v.OpeningsOverlap(first, second) and not v.OpeningFits(second)
        data = main.BuildProjectData()
        assert OpeningProblem(2, data)[0] == "opening_overlap"
        assert OpeningProblem(2, data, prepared = PrepareGeometryValidation(data))[0] == "opening_overlap"
        try:
            DecodeProject(copy.deepcopy(data), v.furnishingDefinitions)
        except ValueError as error:
            assert "overlap" in str(error).lower()
        else:
            raise AssertionError("Project decoding accepted physically overlapping openings")
        second.SetFractions(firstEnd / parentLength, (secondEnd + 5) / parentLength)
        assert not v.OpeningsOverlap(first, second) and v.OpeningFits(second)
        DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)
        assert not OpeningWithinWall(parentLength, 200, 95 / parentLength)
        assert OpeningWithinWall(parentLength, 200, 100 / parentLength)
        assert not ReservedDoorWithinHost(parentLength, 400, 195 / parentLength, False, (0, 1))
        assert ReservedDoorWithinHost(parentLength, 400, 200 / parentLength, False, (0, 1))
        assert not OpeningIntervalsOverlap(0, .5, .5, 1, parentLength)


def CheckCollapsedComponents(main):
    v = main.viewport
    p = QtCore.QPointF
    leaf = v.furnishingDefinitions["null"]
    definition = dict(key = "audit-compound", width = 10000, length = 10000, compoundCenter = (0, 0),
        components = [dict(definition = leaf, x = 0, y = 0, angle = 0, width = size, length = size)
                      for size in (10000, 1)])
    for coordinate in (0, 1e9, 1e12 - 1000):
        furnishing = Furnishing(definition, p(coordinate, 0))
        furnishing.width = 1
        furnishing.firstVertex, furnishing.secondVertex = p(coordinate, -.5), p(coordinate, .5)
        footprints = FurnishingCollisionFootprints(furnishing)
        assert len(footprints) == (1 if coordinate > 1e11 else 2)
        for bounds, corners, axes in footprints:
            assert abs(PolygonTwiceArea(corners)) > 0
            assert all(math.isfinite(value) for axis in axes for value in axis)
            assert all(math.isclose(math.hypot(*axis), 1, rel_tol = 0, abs_tol = 1e-12) for axis in axes)
    assert not list(PlanCompoundFootprints(definition, (0, 0, 0, 1, 0, 0)))
    assert len(PolygonAxes([(0, 0), (1, 0), (1, 0), (1, 1), (0, 1), (0, 0)])) == 4
    assert not FootprintsOverlap([(0, 0)], [], [(0, 0)], [], 0)


def Main():
    with ExampleWindow() as (main, folder):
        for check in (CheckChamferCollision, CheckMiterExportBounds, CheckMiterClearance, CheckContainmentOrder,
                      CheckTranslatedAreas, CheckPositionEdit, CheckOpeningClearance, CheckCollapsedComponents):
            check(main)
            print("PASS:", check.__name__)


if __name__ == "__main__":
    Main()
