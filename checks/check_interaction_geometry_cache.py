"""Differential checks for collision batching and indexed snap candidates."""
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner_app.models import Wall, Stair, Counter
from planner_app.viewport.geometry import CollisionPass
from planner_app.viewport.widget import DrawingViewport


@CollisionPass
def BatchedPairs(viewport, pairs, excludedWalls = ()):
    return [viewport.JoinedObjectsOverlap(first, second, excludedWalls = excludedWalls) for first, second in pairs]


def Main():
    app = QtWidgets.QApplication([])
    viewport = DrawingViewport()
    viewport.performanceTimer.stop()
    point = QtCore.QPointF
    rng = random.Random(413)
    objects = [Wall(point(index * 300, 0), point(index * 300, 1200), 240) for index in range(12)]
    objects += [Wall(point(0, 1200), point(1800, 1200), 240),
                Stair(point(400, 400), point(1400, 400), 700),
                Counter(point(1900, 800), point(2900, 800), 600)]
    viewport.walls = objects
    pairs = [(first, second) for index, first in enumerate(objects) for second in objects[index + 1:]]
    expected = [viewport.JoinedObjectsOverlap(first, second) for first, second in pairs]
    assert BatchedPairs(viewport, pairs) == expected
    assert viewport.collisionPassCache is None
    with patch.object(viewport, "ObjectsOverlap", wraps = viewport.ObjectsOverlap) as overlap:
        assert BatchedPairs(viewport, pairs) == expected
        assert overlap.call_count == 0, "Unchanged pairs were recalculated"
        for obj in objects:
            obj.firstVertex += point(73.25, -91.5)
            obj.secondVertex += point(73.25, -91.5)
        assert BatchedPairs(viewport, pairs) == expected
        assert overlap.call_count == 0, "Rigid translation invalidated collision results"
        objects[0].width = 950
        BatchedPairs(viewport, pairs)
        assert overlap.call_count > 0, "A partial geometry edit reused stale pair results"
    for excludedWalls in ((), (id(objects[1]),), (id(objects[0]), id(objects[2]))):
        expected = [viewport.JoinedObjectsOverlap(first, second, excludedWalls = excludedWalls) for first, second in pairs]
        assert BatchedPairs(viewport, pairs, excludedWalls) == expected
    with patch.object(viewport, "JoinedObjectsOverlap", side_effect = RuntimeError("Interrupted validation")):
        try:
            BatchedPairs(viewport, pairs)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Expected interrupted validation")
    assert viewport.collisionPassCache is None, "Failed validation left a stale batch active"
    preview = Wall(point(900, 600), point(1600, 600), 300)
    previewPairs = [(preview, obj) for obj in objects]
    for offset in (point(), point(600, 0), point(-1000, 1000)):
        preview.firstVertex += offset
        preview.secondVertex += offset
        expected = [viewport.JoinedObjectsOverlap(first, second) for first, second in previewPairs]
        assert BatchedPairs(viewport, previewPairs) == expected
    objects.pop()
    assert BatchedPairs(viewport, pairs[:-1]) == [viewport.JoinedObjectsOverlap(first, second) for first, second in pairs[:-1]]

    # The indexed and full scan must agree on ties, axis strips, snapping flags,
    # constrained rays, and the metadata consumed by group movement.
    targets = [(rng.uniform(-9000, 9000), rng.uniform(-9000, 9000), None, bool(index % 3)) for index in range(160)]
    targets += [(100, 100, None, True), (100, 100, None, True), (100, -6000, None, False)]
    targets = [(x, y, point(x, y), direct) for x, y, unused, direct in targets]
    orderedX = sorted((target[0], index) for index, target in enumerate(targets))
    orderedY = sorted((target[1], index) for index, target in enumerate(targets))
    targetIndex = ([value for value, index in orderedX], [index for value, index in orderedX],
                   [value for value, index in orderedY], [index for value, index in orderedY])
    for zoom in (.08, .2, .7, 2.5):
        viewport.zoom = zoom
        for alignment in (False, True):
            viewport.alignmentSnapEnabled = alignment
            for grid in (False, True):
                viewport.gridSnapEnabled = grid
                for frame in range(100):
                    position = point(100, 100) if frame == 0 else point(rng.uniform(-10000, 10000), rng.uniform(-10000, 10000))
                    anchor = point() if frame % 7 == 0 else None
                    direction = point(1, 0) if anchor is not None else None
                    modifier = QtCore.Qt.KeyboardModifier.AltModifier if frame % 11 == 0 else QtCore.Qt.KeyboardModifier.NoModifier
                    direct = viewport.SnapPosition(position, modifier, angleAnchor = anchor, angleDirection = direction, preparedTargets = targets)
                    metadata = (viewport.snapApplied, viewport.snapPriority, list(viewport.alignmentGuides))
                    indexed = viewport.SnapPosition(position, modifier, angleAnchor = anchor, angleDirection = direction,
                                                    preparedTargets = targets, preparedTargetIndex = targetIndex)
                    assert direct == indexed
                    assert metadata == (viewport.snapApplied, viewport.snapPriority, viewport.alignmentGuides)
    viewport.close()
    print("PASS: collision reuse/invalidation, exclusions, previews, and 1,600 indexed/full snap comparisons.")


if __name__ == "__main__":
    Main()
