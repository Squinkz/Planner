"""One pan scene key per frame, lazy collider keys and fresh queries after edits."""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner_app.models import Wall
from planner_app.viewport.geometry import CollisionPass
from planner_app.viewport.widget import DrawingViewport
from check_scene_render_cache import CompareDirect


@CollisionPass
def QueryPair(viewport, first, second):
    return viewport.JoinedObjectsOverlap(first, second)


@CollisionPass
def FootprintsOnly(viewport, objects):
    return [viewport.ObjectFootprint(obj) for obj in objects]


@CollisionPass
def NestedFootprints(viewport, objects):
    batch = viewport.collisionPassCache
    result = FootprintsOnly(viewport, objects)
    assert viewport.collisionPassCache is batch
    return result


def Main():
    app = QtWidgets.QApplication([])
    viewport = DrawingViewport()
    viewport.resize(1200, 900)
    viewport.performanceTimer.stop()
    point = QtCore.QPointF
    first = Wall(point(-1800, 0), point(1800, 0))
    second = Wall(point(-1800, 100), point(1800, 100))
    viewport.walls = [first, second]
    assert len(NestedFootprints(viewport, viewport.walls)) == 2
    assert viewport.collisionPassCache is None
    assert not hasattr(viewport, "collisionResultKey"), "Footprint-only work scanned collider geometry"
    expected = viewport.JoinedObjectsOverlap(first, second)
    assert QueryPair(viewport, first, second) == expected
    collisionKey = viewport.collisionResultKey
    viewport.show()
    app.processEvents()
    viewport.performanceLabel.hide()
    viewport.grab()
    assert viewport.collisionResultKey is collisionKey
    with patch.object(viewport, "SceneRenderKey", wraps = viewport.SceneRenderKey) as sceneKey:
        for frame in range(20):
            viewport.hoverPosition = point(100 + frame, 150)
            viewport.grab()
        assert sceneKey.call_count == 20
        assert viewport.collisionResultKey is collisionKey, "Warm hover rebuilt collider keys"
    viewport.isPanning = True
    viewport.grab()
    with patch.object(viewport, "SceneRenderKey", wraps = viewport.SceneRenderKey) as sceneKey, \
         patch.object(viewport, "DrawGridBackground", wraps = viewport.DrawGridBackground) as grid:
        for frame in range(20):
            viewport.panOffset += point(3, 1)
            viewport.grab()
        assert sceneKey.call_count == 20, "Pan calculated its scene key more than once per frame"
        assert sum(call.kwargs.get("gridOnly", False) for call in grid.call_args_list) == 20
        assert viewport.collisionResultKey is collisionKey, "Narrow-strip pan rebuilt collider keys"
    viewport.isPanning = False
    CompareDirect(viewport)

    # Direct edits can happen while no collision query runs. The first later
    # query must detect them, even though no committed scene revision changes.
    revision = viewport.sceneRevision
    for mutation in (lambda: setattr(second, "width", 950),
                     lambda: setattr(second, "firstVertex", point(-1800, 2000)),
                     lambda: second.secondVertex.setY(2000),
                     lambda: setattr(second, "firstMiter", .5)):
        oldKey = viewport.collisionResultKey
        mutation()
        CompareDirect(viewport)
        assert viewport.sceneRevision == revision and viewport.collisionResultKey is oldKey
        expected = viewport.JoinedObjectsOverlap(first, second)
        assert QueryPair(viewport, first, second) == expected
        assert viewport.collisionResultKey is not oldKey
    replacement = Wall(point(second.firstVertex), point(second.secondVertex), second.width)
    viewport.walls[1] = replacement
    expected = viewport.JoinedObjectsOverlap(first, replacement)
    assert QueryPair(viewport, first, replacement) == expected
    assert all(id(second) not in pair[:2] for pair in viewport.collisionResults)
    viewport.close()
    report = {"hoverFrames": 20, "panFrames": 20, "panSceneKeyCalls": 20,
              "hoverColliderKeyRebuilds": 0, "panColliderKeyRebuilds": 0,
              "directGeometryMutationsChecked": 4}
    (Path(__file__).resolve().parent.parent / "diagnostics/scene-validation-20261008.json").write_text(
        json.dumps(report, indent = 2) + "\n", encoding = "utf-8")
    print("PASS: single pan key, lazy collider validation, nested footprint passes and deferred mutation detection.")


if __name__ == "__main__":
    Main()
