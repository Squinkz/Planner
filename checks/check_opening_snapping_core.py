"""Frozen exact snapping/placement parity, junction lookup and cache lifetimes."""
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
    from planner_app.geometry.snapping import GridIntervals, PrepareTargetIndex, NearbyTargetIndices, SnapPoint
    assert GridIntervals(.2, False) == (500, 100)
    targets = [(0, 0, True), (100, 0, True), (0, 100, False)]
    index = PrepareTargetIndex(targets)
    assert NearbyTargetIndices((0, 0), 1, index) == [0, 1, 2]
    assert SnapPoint((1, 1), targets, 1, 10, True, 20) == ((0, 0), True, 0, [])
    assert SnapPoint((40, 40), [], 1, 10, True, 20) == ((40, 40), True, 2, [])
    print("PASS: numeric snapping without Qt/site packages")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtWidgets
    from planner_app.models import (Wall, Pillar, Column, Furnishing, Window, Door, SlidingDoor, PocketDoor,
        BarnDoor, BifoldDoor, SilledWindow, CasementWindow, Fireplace, OpenDoorway)
    from planner_app.viewport.widget import DrawingViewport
    from planner_app.viewport.geometry import CollisionPass
    from planner_app.geometry.snapping import PrepareTargetIndex
    from fixtures.qt_opening_snapping_reference_20261016 import ReferencePlacement, ReferenceSnapping, ReferenceGeometry

    class ReferenceViewport(DrawingViewport):
        FindWindowPlacement = ReferencePlacement.FindWindowPlacement
        FindFireplacePlacement = ReferencePlacement.FindFireplacePlacement
        OpeningFits = ReferencePlacement.OpeningFits
        SnapPosition = ReferenceSnapping.SnapPosition
        SnapObjectMovement = ReferenceSnapping.SnapObjectMovement
        GridSteps = ReferenceSnapping.GridSteps
        JoinedObjectBounds = ReferenceGeometry.JoinedObjectBounds

    def Point(value):
        return value.x(), value.y()

    def Placement(value):
        return None if value is None else (type(value), id(value.parentWall), value.centerFraction, value.length,
            getattr(value, "hingeAtSecond", None), getattr(value, "swingsOutwards", None),
            (value.depth, value.depthOffset) if isinstance(value, Fireplace) else None)

    app = QtWidgets.QApplication([])
    p = QtCore.QPointF
    modifier = QtCore.Qt.KeyboardModifier
    actual, reference = DrawingViewport(), ReferenceViewport()
    randomizer = random.Random(218716)
    for case in range(1200):
        offset = 1e8 if case % 7 == 0 else 0
        position = p(offset + randomizer.uniform(-400, 400), -offset + randomizer.uniform(-400, 400))
        targets = [p(offset + randomizer.uniform(-500, 500), -offset + randomizer.uniform(-500, 500)) for i in range(case % 97)]
        if case % 3 == 0:
            targets.extend([position + p(5, 0), position - p(5, 0), position + p(5, 0)])
        prepared = [(value.x(), value.y(), value, bool(i % 3)) for i, value in enumerate(targets)]
        angle = case * .173
        direction = p(math.cos(angle), math.sin(angle)) if case % 2 else None
        anchor = p(offset, -offset) if direction is not None else None
        index = PrepareTargetIndex(prepared) if case % 4 else None
        outputs = []
        for view in (actual, reference):
            view.zoom = (.13, .6, 2, 17)[case % 4]
            view.snapEnabled = bool(case % 5)
            view.vertexSnapEnabled, view.alignmentSnapEnabled, view.gridSnapEnabled = bool(case % 2), bool(case % 3), bool(case % 4)
            view.cornerSnapEnabled = view.vertexSnapEnabled
            view.unitsMode = ("Millimeters", "Centimeters", "Meters", "Feet and Inches", "Inches")[case % 5]
            value = view.SnapPosition(position, modifier.AltModifier if case % 6 == 0 else modifier.NoModifier,
                anchor, direction, preparedTargets = prepared, preparedTargetIndex = index)
            outputs.append((Point(value), view.snapApplied, view.snapPriority, view.alignmentGuides))
        assert outputs[0] == outputs[1], ("snap", case, outputs)
        assert actual.GridSteps() == reference.GridSteps(), ("grid", case)
        if case % 4 == 0:
            values = []
            for view in (actual, reference):
                # The frozen collector predates removal of disabled alignment
                # targets. Compare enabled pools here; option filtering has its
                # independent control/corner/midpoint regression checks.
                view.vertexSnapEnabled = view.cornerSnapEnabled = True
                value = view.SnapPosition(position, modifier.NoModifier, anchor, direction,
                                          snapTargets = targets, alignmentTargets = targets[::4])
                values.append((Point(value), view.snapApplied, view.snapPriority, view.alignmentGuides))
            assert values[0] == values[1], ("collected targets", case, values)

    # Grid boundaries, ties, constrained rays, and individual option combinations.
    for case in range(64):
        walls = [Wall(p(0, 0), p(5000, 0), 240), Wall(p(0, 0), p(0, 3000), 240),
                 Wall(p(5000, 0), p(5000, 3000), 240)]
        for view in (actual, reference):
            view.walls, view.windows, view.furnishings = walls, [Door(walls[0], .1, .25)], []
            view.zoom, view.snapEnabled = .6, True
            view.vertexSnapEnabled, view.alignmentSnapEnabled, view.gridSnapEnabled = bool(case & 1), bool(case & 2), bool(case & 4)
            view.vertexSnapEnabled = view.cornerSnapEnabled = True
            view.midpointSnapEnabled = bool(case & 8)
            view.selectedWall = walls[0]
            view.dragStart = p(20, 20) if case & 16 else None
            view.dragVertices = (p(walls[0].firstVertex), p(walls[0].secondVertex))
            view.connectedEnabled = False
            view.unitsMode = "Feet and Inches" if case & 32 else "Millimeters"
        anchors = [p(30, 80), p(1000, 80), p(2000, 80)]
        values = []
        for view in (actual, reference):
            result = view.SnapObjectMovement(anchors, p(51, -23), modifier.ControlModifier if case % 3 else modifier.NoModifier)
            values.append((Point(result), view.snapApplied, view.snapPriority, view.alignmentGuides))
        assert values[0] == values[1], ("movement", case, values)

    # Native conservative junction bounds, including miter extensions and
    # near-coincident vertices at the exact legacy weld tolerance.
    for case in range(32):
        offset = p(1e8, -1e8) if case % 4 == 0 else p()
        walls = [Wall(offset, offset + p(4000, 0), 240)]
        for index in range(12):
            angle = index * .27 + .001
            first = offset + p((.019999, .02000001, .020001)[index % 3], 0)
            walls.append(Wall(first, first + p(math.cos(angle), math.sin(angle)) * 3000, 100 + index * 50))
            walls[-1].firstMiter = (0, 1, 2)[index % 3]
        for view in (actual, reference):
            view.walls = walls
        excluded = {id(walls[case % len(walls)])}
        @CollisionPass
        def Bounds(view):
            return [tuple(getattr(view.JoinedObjectBounds(wall, excluded), key)() for key in ("x", "y", "width", "height")) for wall in walls]
        assert Bounds(actual) == Bounds(reference), ("bounds", case)
        assert actual.collisionPassCache is None

    placementCount = 0
    classes = (Window, Door, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, OpenDoorway, Fireplace)
    for case in range(160):
        offset = p(1e8, -1e8) if case % 9 == 0 else p()
        walls = [Wall(offset + p(0, 0), offset + p(5000, 0), 240),
                 Wall(offset + p(0, 0), offset + p(0, 3000), 240),
                 Wall(offset + p(5000, 0), offset + p(5000, 3000), 400),
                 Wall(offset + p(2000, -1500), offset + p(2400, 1800), 150),
                 Pillar(offset + p(700, 500), offset + p(700, 900), 350),
                 Column(offset + p(4000, 400), offset + p(4000, 900), 400)]
        openings = [Door(walls[0], .12, .27), Window(walls[2], .1, .2)]
        for view in (actual, reference):
            view.CancelInteraction()
            view.walls, view.windows, view.furnishings, view.labels = walls, openings, [], []
            view.snapEnabled, view.midpointSnapEnabled = bool(case % 4), bool(case % 3)
            view.vertexSnapEnabled, view.alignmentSnapEnabled, view.gridSnapEnabled = bool(case % 2), bool(case % 5), bool(case % 6)
            view.vertexSnapEnabled = view.cornerSnapEnabled = True
            view.zoom = (.2, .6, 2)[case % 3]
            view.panOffset = p(case * 3, -case * 2)
            view.hiddenObjectIds = {id(walls[1])} if case % 3 == 0 else set()
            view.unitsMode = "Feet and Inches" if case % 2 else "Millimeters"
            view.collisionSettings = {"walls": bool(case % 5), "architectural": True, "furnishings": True}
        for mutation in range(3):
            if mutation == 1:
                walls[0].secondVertex += p(1.7, .3)
                walls[3].width += 12
                openings[0].centerFraction += .005
            elif mutation == 2:
                walls[1].firstMiter = 0
                walls.reverse()
                for view in (actual, reference):
                    view.walls = list(walls)
            kind = classes[case % len(classes)]
            location = offset + p(3000 + math.sin(case) * 600, 15)
            values = []
            for view in (actual, reference):
                value = view.FindWindowPlacement(view.WorldToViewport(location), length = 1200,
                    preferredWall = walls[0] if case % 3 else None, openingType = kind,
                    exclude = openings[0] if case % 4 else None,
                    modifiers = modifier.AltModifier if case % 7 == 0 else modifier.NoModifier)
                values.append((Placement(value), view.alignmentGuides))
            assert values[0] == values[1], ("placement", case, mutation, values)
            assert actual.collisionPassCache is None
            placementCount += 1
    print(f"PASS: 1200 raw snap/grid cases, 300 collected-target cases, 64 movement cases, 32 native junction scenes, {placementCount} exact placements and cache refreshes")
    actual.close()
    reference.close()


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
