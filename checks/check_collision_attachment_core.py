"""Frozen collision/attachment parity, cache invalidation and headless kernels."""
import itertools
import math
import os
from pathlib import Path
import random
import subprocess
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))


def CheckWithoutQt():
    from check_geometry_core import CheckWithoutQt as CheckPrimitives
    CheckPrimitives()
    from planner_app.geometry.collisions import (AllowsCollision, ExcludesFootprintCollision, FootprintsOverlap,
        FootprintContainment, SignificantPathOverlap, JunctionReach, RigidTranslation, northFlag, openingFlag)
    from planner_app.geometry.attachments import (AttachedVertexIndices, ConnectedAttachments, FitOpeningCenters,
        OpeningWithinWall, OpeningIntervalsOverlap)
    settings = dict.fromkeys(("walls", "architectural", "furnishings"), False)
    assert AllowsCollision(openingFlag, 0, settings)
    assert not AllowsCollision(northFlag, openingFlag, settings)
    assert not ExcludesFootprintCollision(0, 0)
    corners = ((0, 0), (10, 0), (10, 10), (0, 10))
    axes = ((1, 0), (0, 1))
    assert FootprintsOverlap(corners, axes, corners, axes, .01)
    assert FootprintContainment(corners, corners, axes, .01) == (True, True)
    assert SignificantPathOverlap([corners], .01)
    assert JunctionReach([(1, 0, 2, 1), (0, 1, 2, 1)], .2) == 8.04
    assert RigidTranslation([(1, 0, 0, 10, 0, 2)], [(1, 3, 4, 13, 4, 2)]) == (3, 4)
    assert AttachedVertexIndices((0, 0), (10, 0), 2, [(5, 1), (5, 2), (10, 0)]) == [0, 2]
    records = [(1, (0, 0), (10, 0)), (3, (20, 0), (30, 0)), (2, (10, 0), (20, 0))]
    assert ConnectedAttachments(records[0], records) == [2, 3]
    calls = []
    def Contacts(first, second):
        calls.append((first, second))
        return abs(first - second) == 1
    assert ConnectedAttachments(records[0], records, Contacts) == [2, 3]
    assert calls == [(1, 3), (1, 2), (2, 3)]
    assert FitOpeningCenters((0, 0), (100, 0), 100, [(1, .1, 20, .1), (2, .1, 20, .1)], 40) == [(1, .1), (2, .3)]
    assert FitOpeningCenters((0, 0), (10, 0), 10, [(1, .5, 20, .5)], 20) is None
    assert OpeningWithinWall(100, 20, .1)
    assert not OpeningWithinWall(100, 20, .09)
    assert not OpeningIntervalsOverlap(0, .5, .5, 1)
    assert OpeningIntervalsOverlap(0, .6, .5, 1)
    print("PASS: collision policy, predicates, lazy attachments and opening fitting without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtWidgets
    from planner_app.models import (Wall, Pillar, Column, Elevator, Counter, Stair, Railing, Furnishing,
        NorthArrow, Label, Arrow, MeasurementGuide, Window, Door, Fireplace, PocketDoor)
    from planner_app.viewport.widget import DrawingViewport
    from fixtures.qt_collision_attachment_reference_20261016 import ReferenceGeometry, ReferenceScene, ReferencePlacement

    class ReferenceViewport(DrawingViewport):
        CollisionEnabled = ReferenceGeometry.CollisionEnabled
        ObjectsOverlap = ReferenceGeometry.ObjectsOverlap
        JoinedObjectsOverlap = ReferenceGeometry.JoinedObjectsOverlap
        JoinedObjectBounds = ReferenceGeometry.JoinedObjectBounds
        ContainedWalls = ReferenceGeometry.ContainedWalls
        WallTranslation = ReferenceGeometry.WallTranslation
        AttachedVertices = ReferenceScene.AttachedVertices
        ActiveAttachments = ReferenceScene.ActiveAttachments
        FitWallOpenings = ReferencePlacement.FitWallOpenings
        OpeningFits = ReferencePlacement.OpeningFits
        OpeningsOverlap = ReferencePlacement.OpeningsOverlap

    class DerivedWall(Wall):
        pass

    app = QtWidgets.QApplication([])
    actual, reference = DrawingViewport(), ReferenceViewport()
    point = QtCore.QPointF
    definition = {"key": "test", "name": "Test", "width": 500, "length": 700}
    parent = Wall(point(-2000, 0), point(2000, 0), 240)
    objects = [cls(point(-500, 0), point(500, 0), 200) for cls in
               (Wall, Pillar, Column, Elevator, Stair, Counter, Railing, Arrow, MeasurementGuide, DerivedWall)]
    objects += [Furnishing(definition), NorthArrow(), Label(point(), "test"),
                Window(parent, .2, .4), Door(parent, .4, .6), Fireplace(parent, .6, .8)]
    policies = 0
    for switches in itertools.product((False, True), repeat = 3):
        for view in (actual, reference):
            view.collisionSettings = dict(zip(("walls", "architectural", "furnishings"), switches))
        for first in objects:
            for second in objects:
                assert actual.CollisionEnabled(first, second) == reference.CollisionEnabled(first, second)
                assert actual.ObjectsOverlap(first, second) == reference.ObjectsOverlap(first, second)
                policies += 1
    for view in (actual, reference):
        view.collisionSettings = dict.fromkeys(("walls", "architectural", "furnishings"), True)
    randomizer = random.Random(20261016)
    for case in range(1200):
        offset = point(1e8, -1e8) if case % 4 == 0 else point()
        first = (Wall, Pillar, Column)[case % 3](offset, offset + point(randomizer.uniform(-500, 500), randomizer.uniform(-500, 500)), 100)
        center = offset + point(randomizer.uniform(-250, 250), randomizer.uniform(-250, 250))
        second = Wall(center, center + point(randomizer.uniform(-500, 500), randomizer.uniform(-500, 500)), 200)
        tolerance = (0, .01, 1, 50)[case % 4]
        assert actual.ObjectsOverlap(first, second, tolerance) == reference.ObjectsOverlap(first, second, tolerance), case
        mirror = getattr(first, "numericCollisionFootprint", None)
        actual.ObjectsOverlap(first, second, tolerance)
        if mirror is not None:
            assert first.numericCollisionFootprint is mirror
        first.firstVertex += point(25, 30)
        assert actual.ObjectsOverlap(first, second, tolerance) == reference.ObjectsOverlap(first, second, tolerance), ("edit", case)

    joinedCases = 0
    for case in range(12):
        walls = [Wall(point(-2000, 0), point(0, 0), 240), Wall(point(), point(2000, case * 10 + .001), 340),
                 Wall(point(), point(100 + case, 2000), 180), Column(point(50, -100), point(50, 100), 500),
                 Pillar(point(-800, -100), point(-800, 100), 200)]
        furnishings = [Furnishing(definition, point(300, 100)), Furnishing(definition, point(300, 800))]
        openings = [Door(walls[0], .2, .5), Fireplace(walls[1], .3, .6)]
        for view in (actual, reference):
            view.walls, view.windows, view.furnishings = walls, openings, furnishings
            view.collisionPassCache = {}
        entries = walls + openings + furnishings
        for first, second in itertools.combinations(entries, 2):
            assert actual.JoinedObjectBounds(first).getRect() == reference.JoinedObjectBounds(first).getRect()
            for excluded in ((), (id(walls[1]),)):
                assert actual.JoinedObjectsOverlap(first, second, excludedWalls = excluded) == reference.JoinedObjectsOverlap(
                    first, second, excludedWalls = excluded), ("joined", case)
                joinedCases += 1
        assert [id(obj) for obj in actual.ContainedWalls(walls)] == [id(obj) for obj in reference.ContainedWalls(walls)]
        for view in (actual, reference):
            view.collisionPassCache = None

    attachmentCases = 0
    for case in range(72):
        objects = [Wall(point(), point(1000, 0), 240), Wall(point(1000, 0), point(1000, 1000), 240),
                   Wall(point(1000, 1000), point(0, 1000), 240), Wall(point(500, 100), point(500, 800), 150),
                   Column(point(0, 0), point(0, 200), 300), Counter(point(), point(1000, 0), 300),
                   Stair(point(), point(1000, 0), 500), Railing(point(1000, 0), point(2000, 0), 50),
                   Elevator(point(), point(1000, 0), 1000), Arrow(point(), point(1000, 0))]
        furniture = [Furnishing(definition, point(index * 500, 0)) for index in range(5)]
        if case >= 36:
            for obj in objects + furniture:
                obj.firstVertex += point(1e8, -1e8)
                obj.secondVertex += point(1e8, -1e8)
        source = furniture[0] if case % 4 == 0 else objects[case % len(objects)]
        for view in (actual, reference):
            view.walls, view.furnishings, view.windows = objects, furniture, []
            view.selectedWall = source
            view.selectedVertex = (None, 0, 1)[case % 3]
            view.connectedObjectsEnabled = bool(case % 2)
            view.connectedVerticesEnabled = bool(case % 3)
            view.connectedEnabled = True
            view.groupDrag = False
            view.dragVertices = point(source.firstVertex), point(source.secondVertex)
            view.dragAttachments = view.AttachedVertices(source, captureAll = True)
        def Entries(values):
            return [(id(obj), index, vertex.x(), vertex.y()) for obj, index, vertex in values]
        assert Entries(actual.dragAttachments) == Entries(reference.dragAttachments), ("attached", case)
        assert actual.dragObjectAttachmentKeys == reference.dragObjectAttachmentKeys
        assert Entries(actual.ActiveAttachments()) == Entries(reference.ActiveAttachments()), ("active", case)
        expectedDirect = reference.AttachedVertices(source, captureAll = False)
        actualDirect = actual.AttachedVertices(source, captureAll = False)
        assert Entries(actualDirect) == Entries(expectedDirect), ("direct", case)
        attachmentCases += 1

    fittingCases = 0
    for case in range(96):
        wall = Wall(point(1e8, -1e8), point(1e8 + 4000 + case * .37, -1e8 + case * .19), 240)
        openings = [Door(wall, .1, .25), PocketDoor(wall, .3, .55), Fireplace(wall, .6, .9)]
        for view in (actual, reference):
            view.walls, view.windows, view.furnishings = [wall], openings, []
            view.connectedEnabled = bool(case % 2)
            view.connectedObjectsEnabled = bool(case % 3)
        before = actual.CaptureState()
        if case % 4 == 0:
            wall.secondVertex += point(300, 200)
        elif case % 4 == 1:
            wall.firstVertex += point(-300, -200)
        elif case % 4 == 2:
            wall.firstVertex += point(-200, 100)
            wall.secondVertex += point(400, 50)
        else:
            wall.secondVertex = wall.firstVertex + point(1200, 0)
        originals = [opening.centerFraction for opening in openings]
        actualResult = actual.FitWallOpenings(before, validateScene = False)
        computed = [opening.centerFraction for opening in openings]
        for opening, center in zip(openings, originals):
            opening.centerFraction = center
        expectedResult = reference.FitWallOpenings(before, validateScene = False)
        assert actualResult == expectedResult and computed == [opening.centerFraction for opening in openings], ("fit", case)
        fittingCases += 1
    print(f"PASS: {policies} policy pairs, 1200 edited SAT pairs, {joinedCases} joined pairs, {attachmentCases} attachment scenes, {fittingCases} opening fits; headless kernels")


if __name__ == "__main__":
    if "--without-qt" in sys.argv:
        CheckWithoutQt()
    else:
        Main()
