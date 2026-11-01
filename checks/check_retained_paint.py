"""Exact duplicate ordering, membership invalidation and frozen editor pixels."""
from contextlib import ExitStack, contextmanager
import gc
import os
import random
from pathlib import Path
import sys
import weakref
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "tools")]
from PySide6 import QtCore, QtWidgets
from planner_app.models import Wall, Counter, Pillar, Column, Furnishing, Label, Door
from planner_app.viewport.widget import DrawingViewport
from planner_app.viewport.geometry import GeometryMixin
from planner_app.viewport import geometry
from planner_app.viewport.rendering import RenderingMixin
from planner_app.viewport.edit_cache import EditPaintCacheMixin
from fixtures.retained_paint_reference_20261101 import ReferenceGeometry, ReferenceRendering, ReferenceEditCache
import check_local_paint


@contextmanager
def Baseline(enabled):
    with ExitStack() as stack:
        if enabled:
            for cls, reference, names in (
                    (GeometryMixin, ReferenceGeometry, ("DuplicateFurnishings", "CoincidentObjectGroups", "ContainedWalls")),
                    (RenderingMixin, ReferenceRendering, ("DrawOpaqueScene",)),
                    (EditPaintCacheMixin, ReferenceEditCache, ("EditSceneSnapshot",))):
                for name in names:
                    stack.enter_context(patch.object(cls, name, getattr(reference, name)))
        yield


def CheckPreparation():
    view = DrawingViewport(furnishingDefinitions = {})
    point = QtCore.QPointF
    definition = dict(key = "test", width = 600, length = 600)
    first, second = Wall(point(), point(2000, 0)), Wall(point(), point(2000, 0))
    first.objectId, second.objectId = 1, 2
    view.walls = [first, second, Counter(point(4000, 0), point(6000, 0), 400)]
    view.windows = [Door(first, .2, .4), Door(first, .2, .4)]
    objects = [Furnishing(definition, point(index % 3 * 1000, 1000)) for index in range(12)]
    view.furnishings = objects
    view.labels = [Label(), Label()]
    comparisons = 0

    def Compare():
        nonlocal comparisons
        members = view.VisibleSceneObjects()
        for name, actual in members.items():
            assert actual == [obj for obj in getattr(view, name) if view.IsObjectVisible(obj)], name
        for includeHidden in (False, True, False):
            assert view.DuplicateFurnishings(includeHidden) == ReferenceGeometry.DuplicateFurnishings(view, includeHidden)
            assert view.CoincidentObjectGroups(includeHidden) == ReferenceGeometry.CoincidentObjectGroups(view, includeHidden)
        comparisons += 1

    Compare()
    previousMembers = view.VisibleSceneObjects()
    previousDuplicates = view.furnishingDuplicatePreparation
    for frame in range(24):
        duplicateResult = view.PreparedFurnishingDuplicates()
        first.secondVertex.setX(2000 + frame)
        assert view.PreparedFurnishingDuplicates() is duplicateResult
        Compare()
        assert view.VisibleSceneObjects() is previousMembers
        assert view.furnishingDuplicatePreparation[1] == previousDuplicates[1]
    # Visibility, ordering and repeated object references all affect the output.
    view.hiddenObjectIds.add(id(objects[0]))
    Compare()
    view.visibility["Furnishings"] = False
    Compare()
    view.visibility["Furnishings"] = True
    view.hiddenObjectIds.clear()
    view.furnishings.reverse()
    Compare()
    view.furnishings.extend([objects[2], objects[0]])
    Compare()
    view.walls.insert(0, first)
    Compare()
    for frame, obj in enumerate(objects):
        obj.behindCounters = frame % 2 == 0
        obj.firstVertex += point(frame % 3, 0)
        obj.flipHorizontal = frame % 3 == 0
        Compare()
    # These metadata/definition edits are intentionally read as values, even
    # where they do not emit scene notifications.
    definition["key"] = "changed"
    Compare()
    first.originalMaterial = "original"
    Compare()
    del first.originalMaterial
    view.windows[1].parentWall = second
    Compare()
    view.windows.reverse()
    Compare()
    view.labels[1].text = "different"
    Compare()
    view.visibility["World"] = False
    Compare()
    view.visibility["World"] = True
    Compare()
    # Within one read-only paint, grouping and front-copy warnings share work.
    view.collisionPassCache = {}
    one = view.PreparedFurnishingDuplicates()
    assert view.PreparedFurnishingDuplicates() is one
    objects[0].width += 10
    assert view.PreparedFurnishingDuplicates() is not one
    view.collisionPassCache = None
    Compare()
    view.ClearGeometryCaches()
    assert "visiblePaintObjects" not in view.__dict__
    assert "furnishingDuplicatePreparation" not in view.__dict__
    Compare()
    del previousMembers, previousDuplicates, one, duplicateResult
    reference = weakref.ref(objects[0])
    view.walls, view.windows, view.furnishings, view.labels = [], [], [], []
    view.ClearGeometryCaches()
    del objects, obj
    gc.collect()
    assert reference() is None, "Retained paint preparation kept a replaced scene alive"
    view.deleteLater()
    return comparisons


def CheckContainment():
    point = QtCore.QPointF
    randomizer = random.Random(20261101)
    comparisons = 0
    for count in (20, 80):
        view = DrawingViewport(furnishingDefinitions = {})
        walls = [Wall(point(index * 1200, 0), point(index * 1200 + 900, 0), 200) for index in range(count)]
        walls += [Wall(point(), point(900, 0), 200), walls[0],
                  Counter(point(0, 0), point(900, 0), 400),
                  Pillar(point(2400, -200), point(2400, 200), 300),
                  Column(point(3600, -200), point(3600, 200), 400)]
        view.walls = walls
        subsets = [view.walls, [wall for wall in walls if type(wall) in (Wall, Pillar, Column)]]
        for frame in range(100):
            wall = walls[frame % len(walls)]
            if frame % 10 == 0:
                # Collapse, duplicate, expand over a stationary subject, then
                # move away: both old and new container regions are required.
                wall.firstVertex = point()
                wall.secondVertex = point(0 if frame % 20 == 0 else 2400, 0)
                wall.width = 500
            else:
                wall.firstVertex = point(randomizer.randrange(count) * 1200, randomizer.choice((0, .0099999, .0100001, 150)))
                wall.secondVertex = wall.firstVertex + point(randomizer.choice((900, 1600, -900)), randomizer.choice((0, 250)))
                wall.width = randomizer.choice((200, 400, 800))
            for subset in subsets:
                actual = view.ContainedWalls(subset)
                # Force the frozen implementation through its full predicate;
                # it must not accidentally consume a current cached result.
                view.containedWallKey = None
                view.containedSceneCache = None
                expected = ReferenceGeometry.ContainedWalls(view, subset)
                assert actual == expected, (count, frame, "containment")
                comparisons += 1
        # Reordering/membership, broad edits and a nonfinite key must retain
        # the frozen fallback behavior. Recovering to finite input must too.
        for mode in ("reorder", "broad", "nonfinite", "recover"):
            if mode == "reorder":
                view.walls.reverse()
                subsets = [view.walls, list(reversed(subsets[1]))]
            elif mode == "broad":
                for wall in view.walls:
                    wall.firstVertex += point(10, 15)
            else:
                walls[0].width = float("nan") if mode == "nonfinite" else 200
            for subset in subsets:
                actual = view.ContainedWalls(subset)
                view.containedWallKey = None
                view.containedSceneCache = None
                expected = ReferenceGeometry.ContainedWalls(view, subset)
                assert actual == expected, (count, mode)
                comparisons += 1
        assert len(view.containedPaintPreparation[1]) <= 2
        view.ClearGeometryCaches()
        assert "containedPaintPreparation" not in view.__dict__
        view.deleteLater()
    # Prove unaffected exact predicates are skipped, not just that the final
    # lists agree. A stationary nested pair keeps a real containment result.
    view = DrawingViewport(furnishingDefinitions = {})
    view.walls = [Wall(point(index * 2000, 0), point(index * 2000 + 1000, 0), 200) for index in range(20)]
    view.walls.append(Wall(point(100, 0), point(900, 0), 100))
    view.ContainedWalls()
    view.walls[10].secondVertex += point(20, 30)
    with patch.object(geometry, "FootprintContainment", wraps = geometry.FootprintContainment) as predicate:
        actual = view.ContainedWalls()
        assert predicate.call_count == 0, "Unchanged containment was recomputed"
    view.containedWallKey = None
    view.containedSceneCache = None
    assert actual == ReferenceGeometry.ContainedWalls(view)
    # Throw inside an affected exact predicate; the previous retained entry
    # must survive intact for a later successful retry.
    previous = dict(view.containedPaintPreparation[1])
    view.walls[-1].firstVertex += point(10, 0)
    with patch.object(geometry, "FootprintContainment", side_effect = RuntimeError("fixture")):
        try:
            view.ContainedWalls()
        except RuntimeError as error:
            assert str(error) == "fixture"
        else:
            raise AssertionError("Expected an affected containment predicate")
    assert view.containedPaintPreparation[1] == previous
    actual = view.ContainedWalls()
    view.containedWallKey = None
    view.containedSceneCache = None
    assert actual == ReferenceGeometry.ContainedWalls(view)
    view.ClearGeometryCaches()
    view.deleteLater()
    comparisons += 2
    return comparisons


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    preparations = CheckPreparation()
    containment = CheckContainment()
    with patch.object(check_local_paint, "Baseline", Baseline):
        frames = check_local_paint.CheckProject()
    print(f"PASS: {preparations} ordered membership/duplicate comparisons, {containment} frozen containment comparisons, cache invalidation/lifetime, "
          f"and {frames} exact frozen synthetic model/validation/pixel frames.")


if __name__ == "__main__":
    Main()
