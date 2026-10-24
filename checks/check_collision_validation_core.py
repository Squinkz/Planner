"""Conservative opening candidates versus frozen native collision validation."""
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
    from planner_app.geometry.opening_collisions import OpeningCollisionIndex
    from planner_app.geometry.snapping import PrepareTargetIndex, NearbyPointIndices
    index = OpeningCollisionIndex([(0, 0, 2, 2)], [(1, (10, 10, 11, 11)), (2, (0, 0, 2, 2))])
    assert index.Query((0, 0, 1, 1), 1) == ([0], [0, 1])
    assert index.Query((10, 10, 10, 10), 1) == ([], [0])
    duplicates = OpeningCollisionIndex([(0, 0, 2, 2)] * 2, [(1, (0, 0, 2, 2))] * 2)
    assert duplicates.Query((0, 0, 1, 1), 1) == ([0, 1], [0, 1])
    assert NearbyPointIndices((0, 0), 1, PrepareTargetIndex([(0, 0), (0, 4), (5, 0)])) == [0]
    index = OpeningCollisionIndex([(float("nan"), 0, 2, 2)], [(1, (0, 0, float("inf"), 2))])
    assert index.Query((20, 20, 21, 21), 9) == ([0], [0])
    assert index.Query((float("nan"), 0, 1, 1), 9) == ([0], [0])
    print("PASS: opening candidate index and square endpoint query without Qt/site packages")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtWidgets
    from planner_app.models import (Wall, Pillar, Column, Window, Door, SlidingDoor, PocketDoor, BarnDoor,
        BifoldDoor, SilledWindow, CasementWindow, OpenDoorway, Fireplace)
    from planner_app.viewport.widget import DrawingViewport
    from planner_app.viewport.geometry import CollisionPass
    from planner_app.geometry.opening_collisions import OpeningCollisionIndex
    from planner_app.geometry.snapping import PrepareTargetIndex, NearbyPointIndices
    from fixtures.qt_collision_validation_reference_20261016 import ReferencePlacement, ReferenceScene, ReferenceGeometry

    class ReferenceViewport(DrawingViewport):
        OpeningFits = ReferencePlacement.OpeningFits
        OpeningsOverlap = ReferencePlacement.OpeningsOverlap
        OpeningsValid = ReferencePlacement.OpeningsValid
        GroupOpeningsFit = ReferenceScene.GroupOpeningsFit
        JoinedObjectBounds = ReferenceGeometry.JoinedObjectBounds

    app = QtWidgets.QApplication([])
    p = QtCore.QPointF
    r = random.Random(205517)
    # Match native QRectF edge behavior on empty/reversed/huge and random bounds.
    for case in range(600):
        offset = 1e8 if case % 5 == 0 else 0
        bounds = []
        for index in range(40):
            left, top = offset + r.uniform(-5000, 5000), -offset + r.uniform(-5000, 5000)
            width = 0 if index % 13 == 0 else r.uniform(-3000, 3000)
            height = 0 if index % 17 == 0 else r.uniform(-3000, 3000)
            if index == 39:
                width, height = 1e6, 1e6
            bounds.append((left, top, left + width, top + height))
        query = bounds[case % len(bounds)]
        parent = case % 7
        index = OpeningCollisionIndex(bounds, [(i % 7, value) for i, value in enumerate(bounds)])
        actualWalls, actualOpenings = index.Query(query, parent)
        native = QtCore.QRectF(p(query[0], query[1]), p(query[2], query[3])).normalized()
        expected = [i for i, value in enumerate(bounds) if native.intersects(
            QtCore.QRectF(p(value[0], value[1]), p(value[2], value[3])).normalized())]
        assert actualWalls == expected, ("bounds", case, actualWalls, expected)
        assert actualOpenings == sorted(set(expected).union(i for i in range(40) if i % 7 == parent))
        targets = [(value[0], value[1]) for value in bounds]
        expected = [i for i, value in enumerate(targets) if query[0] - 200 <= value[0] <= query[0] + 200 and query[1] - 200 <= value[1] <= query[1] + 200]
        assert NearbyPointIndices(query[:2], 200, PrepareTargetIndex(targets)) == expected

    actual, reference = DrawingViewport(), ReferenceViewport()
    classes = (Window, Door, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, OpenDoorway, Fireplace)
    comparisons = 0
    for case in range(80):
        offset = p(1e8, -1e8) if case % 7 == 0 else p()
        angle = case * .143
        axis, normal = p(math.cos(angle), math.sin(angle)), p(-math.sin(angle), math.cos(angle))
        walls = [Wall(offset + normal * i * 1800, offset + normal * i * 1800 + axis * 6000, 240) for i in range(6)]
        # Native miter extensions, elliptical columns, structural crossing, and
        # source ordering can all affect collision results.
        walls += [Wall(walls[0].firstVertex, walls[0].firstVertex + axis * 4000 + normal * (1 + case % 3), 480),
                  Pillar(offset + axis * 3300 + normal * 250, offset + axis * 3300 + normal * 650, 350),
                  Column(offset + axis * 4800 - normal * 200, offset + axis * 4800 + normal * 200, 500)]
        walls[6].firstMiter = (0, 1, 2)[case % 3]
        walls += [Wall(offset + p(20000, i * 1800), offset + p(25000, i * 1800), 120) for i in range(12)]
        openings = [classes[(case + i) % 10](wall, .3, .5) for i, wall in enumerate(walls[:6])]
        openings += [Door(wall, .7, .85) for wall in walls[:6]]
        openings += [Window(wall, .2, .4) for wall in walls[9:]]
        for view in (actual, reference):
            view.walls, view.windows, view.furnishings = walls, openings, []
            view.basePixelsPerMillimeter = (.05, .2, .6)[case % 3]
            view.hiddenObjectIds = {id(walls[6])} if case % 2 else set()
            view.collisionSettings = {"walls": bool(case % 4), "architectural": bool(case % 3), "furnishings": True}
        for mutation in range(3):
            before = actual.CaptureState()
            if mutation == 1:
                walls[6].secondVertex += normal * 1000
                walls[7].width += 700
                openings[6].centerFraction = .45
            elif mutation == 2:
                walls.reverse()
                openings.reverse()
                for view in (actual, reference):
                    view.walls, view.windows = list(walls), list(openings)
                openings[-1].length *= .7
            # Compare every single opening inside a shared candidate scope; the
            # frozen method performs its full original scan on the same objects.
            @CollisionPass
            def Individual(view):
                with view.OpeningCandidatePass(len(openings)):
                    return [view.OpeningFits(opening, exclude = openings[1] if i % 2 else None) for i, opening in enumerate(openings)]
            assert Individual(actual) == Individual(reference), ("individual", case, mutation)
            entries = [(opening, None) for opening in openings[:8]]
            assert actual.GroupOpeningsFit(entries) == reference.GroupOpeningsFit(entries), ("group", case, mutation)
            assert actual.OpeningsValid(validateFurnishings = False) == reference.OpeningsValid(validateFurnishings = False), ("full", case, mutation)
            assert actual.OpeningsValid(validateFurnishings = False, before = before) == reference.OpeningsValid(validateFurnishings = False, before = before), ("changed", case, mutation)
            assert actual.collisionPassCache is None
            comparisons += len(openings) + 3

    # Same-parent interval overlap must survive zero-area footprint filtering.
    parent = Wall(p(), p(5000, 0), 0)
    for view in (actual, reference):
        view.walls = [parent] + [Wall(p(10000, i * 2000), p(15000, i * 2000), 120) for i in range(20)]
        view.windows = [Window(parent, .1, .4), Door(parent, .2, .5), Window(parent, .6, .7), Door(parent, .8, .9)]
        view.collisionSettings = {"walls": True, "architectural": True, "furnishings": True}
    # Add enough scene records to exercise the bulk path even for this case.
    for view in (actual, reference):
        view.walls += [Wall(p(30000, i * 2000), p(35000, i * 2000), 120) for i in range(12)]
    assert actual.GroupOpeningsFit([(opening, None) for opening in actual.windows]) == False
    assert reference.GroupOpeningsFit([(opening, None) for opening in reference.windows]) == False

    # Early invalid dimensions avoid constructing an index; nested scope and
    # exception exit restore the outer state, without leaving a stale index.
    actual.windows[0].length = 6000
    @CollisionPass
    def Scope(view):
        with view.OpeningCandidatePass(4):
            assert view.OpeningFits(view.windows[0]) == False
            assert view.collisionPassCache["openingCandidates"] == {"primed": False, "prepared": None}
        assert "openingCandidates" not in view.collisionPassCache
        view.windows[0].length = 1200
        with view.OpeningCandidatePass(4):
            view.OpeningFits(view.windows[0])
            assert view.collisionPassCache["openingCandidates"]["prepared"] is None
            view.OpeningFits(view.windows[2])
            prepared = view.collisionPassCache["openingCandidates"]
            assert prepared["prepared"] is not None
            with view.OpeningCandidatePass(1):
                assert "openingCandidates" not in view.collisionPassCache
            assert view.collisionPassCache["openingCandidates"] is prepared
        try:
            with view.OpeningCandidatePass(4):
                view.OpeningFits(view.windows[0])
                view.OpeningFits(view.windows[2])
                assert view.collisionPassCache["openingCandidates"]["prepared"] is not None
                raise RuntimeError("scope fixture")
        except RuntimeError:
            assert "openingCandidates" not in view.collisionPassCache
    Scope(actual)
    assert actual.collisionPassCache is None
    parent = Wall(p(), p(1000000, 0), 240)
    for view in (actual, reference):
        view.walls = [parent]
        view.windows = [Door(parent, (i + 1) / 33 - .0006, (i + 1) / 33 + .0006) for i in range(32)]
    originalBuilder = actual.BuildOpeningCollisionIndex
    def NoSiblingIndex():
        raise AssertionError("All-sibling validation should not build an index")
    actual.BuildOpeningCollisionIndex = NoSiblingIndex
    assert actual.GroupOpeningsFit([(opening, None) for opening in actual.windows])
    assert reference.GroupOpeningsFit([(opening, None) for opening in reference.windows])
    actual.BuildOpeningCollisionIndex = originalBuilder
    print(f"PASS: 600 native bound/index scenes; {comparisons} frozen opening/group/full/changed validation results; zero-area siblings and scope lifetimes; Qt-free import")
    actual.close()
    reference.close()


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
