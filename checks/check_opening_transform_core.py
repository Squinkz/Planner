"""Exact frozen placement/edit parity and platform-free numeric edit operations."""
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
    from planner_app.geometry.opening_placement import (ProjectOpening, OpeningGap, BlockedOpeningIntervals,
        OpeningPlacementSpan, OpeningVertexFraction, CenteredOpeningSpan, FireplaceCenter)
    from planner_app.geometry.editing import (TransformPoint, OpeningTransformTarget, ReattachTransformedOpening, RebaseMergedOpening,
        AngleEndpoints, ResizeHandleDimensions, ResizedHandleCenter, PrepareSelectionMembers, SelectionSpan,
        FitSelectionScale, TransformSelectionMembers, ChooseWallSplit)
    assert ProjectOpening((0, 0), (10, 0), (20, 1)) == ((10, 0), 100, 1.0, (10, 0))
    assert OpeningGap(.5, [(.1, .3), (.7, .9)]) == (.3, .7)
    assert OpeningPlacementSpan(2, 10, .5, .3, .7) == (.2, .4, .6, .5)
    assert OpeningVertexFraction((0, 0), (10, 0), (3, 1), 0, .8) == .3
    span = CenteredOpeningSpan((0, 0), (100, 0), (10, 1), 0, .3, 0, 1)
    assert math.isclose(span[0], .1) and span[1] == .5
    assert CenteredOpeningSpan((0, 0), (100, 0), (-20, 0), 0, .3, 0, 1) == (0, .6)
    assert CenteredOpeningSpan((0, 0), (100, 0), (20, 0), 1, .5, 0, 1) == (.495, .505)
    assert FireplaceCenter((0, 0), (1, 0), (0, 1), 10, 2, (5, 3)) == (.5, 3)
    blocked = BlockedOpeningIntervals([(0, -1), (10, -1), (10, 1), (0, 1)], (0, 0), (10, 0), 100,
                                      [[(4, -2), (6, -2), (6, 2), (4, 2)]])
    assert blocked == [(.4, .6)], blocked
    assert TransformPoint((2, 0), (1, 0), (3, 4), 0, 1) == (4, 5)
    assert OpeningTransformTarget((0, 0), (10, 0), (0, 0), (0, 0), 1, 0) == ((5, 0), (10, 0))
    assert ReattachTransformedOpening((5, 0), (-10, 0), (0, 0), (10, 0)) == (.5, True)
    assert RebaseMergedOpening((5, 0), (-10, 0), (0, 0), (10, 0), 10, 2) == (.5, True, True)
    assert AngleEndpoints((0, -2), (0, 2), 4, 0) == ((0, -2), (0, 2))
    assert ResizeHandleDimensions((0, 1), 10, 20, (2, 0), "width", 1, False, 1) == (12, 20)
    assert ResizedHandleCenter((0, 0), (0, 1), 10, 20, 12, 20, "width", 1, False) == (1, 0)
    members = PrepareSelectionMembers([(1, (0, -10), (0, 10), 10, 0, 20)], (0, 0))
    assert SelectionSpan(members, 2, 1, 0) == 20
    assert FitSelectionScale(members, 2, 1, 0, 20) == (2, 1)
    assert TransformSelectionMembers(members, (5, 0), 2, 1, 0) == [(1, (5, -10), (5, 10), 20, 0)]
    assert ChooseWallSplit((0, 0), (10, 0), [], [(.4, .6)]) == .4
    print("PASS: opening placement, rotation, resize, selection fitting and subdivision without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtGui, QtWidgets
    from planner_app.models import (Wall, Pillar, Column, Furnishing, Window, Door, SlidingDoor, PocketDoor,
        BarnDoor, BifoldDoor, SilledWindow, CasementWindow, Fireplace, OpenDoorway)
    from planner_app.viewport.widget import DrawingViewport
    from fixtures.qt_opening_transform_reference_20261016 import (ReferencePlacement, ReferenceScene,
        ReferenceHandles, ReferenceWindow, ReferenceFireplace, ReferenceFurnishing)

    class ReferenceViewport(DrawingViewport):
        FindWindowPlacement = ReferencePlacement.FindWindowPlacement
        FindFireplacePlacement = ReferencePlacement.FindFireplacePlacement
        OrientDoor = ReferencePlacement.OrientDoor
        InactiveOpening = ReferencePlacement.InactiveOpening
        MoveSpecial = ReferenceScene.MoveSpecial
        SubdivideWalls = ReferenceScene.SubdivideWalls
        DissolveWalls = ReferenceScene.DissolveWalls
        UpdateFurnishingHandleDrag = ReferenceHandles.UpdateFurnishingHandleDrag
        TransformFurnishingSelection = ReferenceHandles.TransformFurnishingSelection
        FurnishingSelectionSpan = ReferenceHandles.FurnishingSelectionSpan

    def Values(value):
        if isinstance(value, QtCore.QPointF):
            return value.x(), value.y()
        if isinstance(value, QtCore.QLineF):
            return Values(value.p1()), Values(value.p2())
        if isinstance(value, (list, tuple)):
            return tuple(Values(entry) for entry in value)
        return value

    def Geometry(view):
        return ([(type(obj), Values(obj.firstVertex), Values(obj.secondVertex), obj.width) for obj in view.walls + view.furnishings],
                [(type(obj), view.walls.index(obj.parentWall), obj.centerFraction, obj.length,
                  getattr(obj, "hingeAtSecond", None), getattr(obj, "swingsOutwards", None), getattr(obj, "panelsFlipped", None))
                 for obj in view.windows])

    def Placement(opening):
        return None if opening is None else (type(opening), id(opening.parentWall), opening.centerFraction, opening.length,
            getattr(opening, "hingeAtSecond", None), getattr(opening, "swingsOutwards", None), getattr(opening, "panelsFlipped", None),
            (opening.depth, opening.depthOffset) if isinstance(opening, Fireplace) else None)

    app = QtWidgets.QApplication([])
    point = QtCore.QPointF
    randomizer = random.Random(20261016)
    definition = {"key": "test", "name": "Test", "width": 600, "length": 800}
    actual, reference = DrawingViewport(), ReferenceViewport()
    for case in range(1000):
        offset = point(1e8, -1e8) if case % 4 == 0 else point()
        first = offset + point(randomizer.uniform(-1000, 1000), randomizer.uniform(-1000, 1000))
        second = first + point(randomizer.uniform(1, 2000), randomizer.uniform(1, 2000))
        angle = randomizer.uniform(-1080, 1080)
        objects = [Furnishing(definition), Furnishing(definition)]
        for obj in objects:
            obj.firstVertex, obj.secondVertex = point(first), point(second)
        objects[0].angle = angle
        ReferenceFurnishing.SetAngle(objects[1], angle)
        assert Values((objects[0].firstVertex, objects[0].secondVertex)) == Values((objects[1].firstVertex, objects[1].secondVertex)), ("angle", case)
        parent = Wall(first, second, 240)
        openings = [Window(parent, .2, .7), Window(parent, .2, .7)]
        position = offset + point(randomizer.uniform(-3000, 3000), randomizer.uniform(-3000, 3000))
        openings[0].SetVertex(case % 2, position)
        ReferenceWindow.SetVertex(openings[1], case % 2, position)
        assert (openings[0].centerFraction, openings[0].length) == (openings[1].centerFraction, openings[1].length), ("vertex", case)
        fireplaces = [Fireplace(parent, .2, .6), Fireplace(parent, .2, .6)]
        for fireplace in fireplaces:
            fireplace.depth = 1000
        fireplaces[0].SetCenter(position)
        ReferenceFireplace.SetCenter(fireplaces[1], position)
        assert (fireplaces[0].centerFraction, fireplaces[0].depthOffset) == (fireplaces[1].centerFraction, fireplaces[1].depthOffset), ("fireplace", case)

    walls = [Wall(point(-2500, 0), point(2500, 0), 240), Wall(point(-2500, 1800), point(2500, 1800), 400),
             Wall(point(400, -800), point(400, 800), 300), Column(point(-1000, -200), point(-1000, 200), 600)]
    openings = [Door(walls[0], .05, .2), Window(walls[0], .7, .85)]
    classes = (Window, Door, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, OpenDoorway, Fireplace)
    placementCases = 0
    for case in range(180):
        cls = classes[case % len(classes)]
        for view in (actual, reference):
            view.resize(1000, 800)
            view.walls, view.windows, view.furnishings = walls, openings, []
            view.zoom = (.15, .6, 1.7)[case % 3]
            view.panOffset = point(.37, .71)
            view.snapEnabled = bool(case % 2)
        worldPosition = point(-2300 + (case % 30) * 160, (0, 15, 1800, 1900)[case % 4])
        position = actual.WorldToViewport(worldPosition)
        modifier = QtCore.Qt.KeyboardModifier.AltModifier if case % 5 == 0 else QtCore.Qt.KeyboardModifier.NoModifier
        preferred = walls[1] if case % 6 == 0 else None
        exclude = openings[0] if case % 7 == 0 else None
        computed = actual.FindWindowPlacement(position, length = 1200 if cls is Fireplace else None, preferredWall = preferred, openingType = cls, exclude = exclude, modifiers = modifier)
        expected = reference.FindWindowPlacement(position, length = 1200 if cls is Fireplace else None, preferredWall = preferred, openingType = cls, exclude = exclude, modifiers = modifier)
        assert Placement(computed) == Placement(expected), ("placement", case, Placement(computed), Placement(expected))
        assert Values(actual.alignmentGuides) == Values(reference.alignmentGuides), ("guides", case)
        if case % 9 == 0:
            walls[2].firstVertex += point(.1, .2)
        placementCases += 1

    groupCases = 0
    for case in range(24):
        objects = []
        for index in range(8):
            obj = Furnishing(definition, point(index * 900, index % 3 * 1200))
            obj.angle = (index * 23 + case * 1.3) % 360
            objects.append(obj)
        states = []
        for view in (actual, reference):
            members = [(obj.Clone(), point(obj.firstVertex), point(obj.secondVertex), obj.width, obj.angle) for obj in objects]
            box = Furnishing(definition, point(1800, 800))
            box.width = 7000
            box.firstVertex, box.secondVertex = point(1800, -1000), point(1800, 2600)
            state = {"object": box, "center": point(1800, 800), "width": 6000, "length": 3200,
                     "angle": 0, "handle": ("resize", "width" if case % 2 else "length", 1),
                     "members": members, "centeredResize": bool(case % 3)}
            states.append(state)
        for axis in (0, 1):
            computed = actual.FurnishingSelectionSpan(states[0], .3 + case * .1, .8, axis)
            expected = reference.FurnishingSelectionSpan(states[1], .3 + case * .1, .8, axis)
            assert computed == expected, ("span", case, axis, computed, expected)
        actual.TransformFurnishingSelection(states[0])
        reference.TransformFurnishingSelection(states[1])
        assert [(Values(obj.firstVertex), Values(obj.secondVertex), obj.width) for obj, *rest in states[0]["members"]] == [
                (Values(obj.firstVertex), Values(obj.secondVertex), obj.width) for obj, *rest in states[1]["members"]], ("group", case)
        assert actual.PreparedFurnishingMembers(states[0]) is actual.PreparedFurnishingMembers(states[0])
        groupCases += 1

    handleCases = 0
    for case in range(48):
        for view in (actual, reference):
            view.CancelInteraction()
            obj = Furnishing(definition, point(100, 200))
            obj.angle = case * 7.3
            view.walls, view.windows, view.furnishings, view.labels = [], [], [obj], []
            view.snapEnabled = False
            view.SetSelection([(obj, None)])
            view.rotationPivot = point(-200, -100)
            mode = "rotate" if case % 4 == 0 else "resize"
            field = None if mode == "rotate" else ("width", "length", "corner")[case % 3]
            sign = None if mode == "rotate" else (1, -1) if field == "corner" else 1
            start = view.WorldToViewport(point(100, 200)) + point(70, 80)
            view.BeginFurnishingHandleDrag(obj, (mode, field, sign, start, point()), start)
            modifiers = QtCore.Qt.KeyboardModifier.ShiftModifier if case % 2 else QtCore.Qt.KeyboardModifier.NoModifier
            view.UpdateFurnishingHandleDrag(start + point(30, -20), modifiers)
        assert Geometry(actual) == Geometry(reference), ("handle", case)
        assert Values(actual.rotationPivot) == Values(reference.rotationPivot), ("pivot", case)
        handleCases += 1

    for case in range(24):
        for view in (actual, reference):
            view.CancelInteraction()
            view.walls = [Wall(point(-2000, 0), point(2000, 0), 240), Pillar(point(300, -200), point(300, 200), 300)]
            view.windows = [Door(view.walls[0], .2, .4)]
            view.furnishings = [Furnishing(definition, point(5000, 0))]
            view.connectedEnabled = False
            entries = ([(view.furnishings[0], None)] if case % 3 == 0 else
                       [(view.walls[0], None), (view.windows[0], None)] if case % 3 == 1 else [(view.windows[0], None)])
            view.SetSelection(entries)
            view.rotationPivot = None if case % 3 == 2 else point(100, -300)
        computed = actual.MoveSpecial(10 + case, 0 if case % 3 == 2 else 20, (180 if case % 2 else 0) if case % 3 == 2 else case * 13, bool(case % 2))
        expected = reference.MoveSpecial(10 + case, 0 if case % 3 == 2 else 20, (180 if case % 2 else 0) if case % 3 == 2 else case * 13, bool(case % 2))
        assert computed == expected and Geometry(actual) == Geometry(reference), ("move", case)
        computed = actual.SubdivideWalls([actual.walls[0]])
        expected = reference.SubdivideWalls([reference.walls[0]])
        assert computed == expected and Geometry(actual) == Geometry(reference), ("subdivide", case)
        computed = actual.DissolveWalls(actual.walls[0].secondVertex)
        expected = reference.DissolveWalls(reference.walls[0].secondVertex)
        assert computed == expected and Geometry(actual) == Geometry(reference), ("dissolve", case)
    print(f"PASS: 1000 exact model edits, {placementCases} placements/guides, {groupCases} group transforms, {handleCases} handle drags, 24 moves/subdivisions/merges; headless kernels")


if __name__ == "__main__":
    if "--without-qt" in sys.argv:
        CheckWithoutQt()
    else:
        Main()
