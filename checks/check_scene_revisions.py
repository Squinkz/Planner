"""Revision reuse detects property, point, container and history mutations."""
import copy
import gc
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner_app.models import Wall, Door, Window, Stair, Railing, Arrow, Label, Furnishing
from planner_app.viewport.widget import DrawingViewport
from check_scene_render_cache import CompareDirect


def Main():
    app = QtWidgets.QApplication([])
    v = DrawingViewport()
    v.resize(1200, 800)
    point = QtCore.QPointF
    wall = Wall(point(-1200, 0), point(1200, 0))
    stair = Stair(point(0, 500), point(1000, 500))
    railing = Railing(point(0, -500), point(1000, -500))
    arrow = Arrow(point(0, 1000), point(1000, 1000))
    door = Door(wall, .1, .3)
    window = Window(wall, .5, .7)
    v.walls = [wall, stair, railing, arrow]
    v.windows = [door, window]
    v.labels = [Label(point(0, 1500), "Revision")]
    v.EnsureObjectIds()
    v.verifyRenderRevisions = True
    v.show()
    app.processEvents()
    edits = ((wall, "width", 350), (wall, "material", "Brick"), (wall, "firstMiter", .8),
             (door, "hingeAtSecond", True), (door, "swingsOutwards", True),
             (window, "centerFraction", .75), (stair, "directionReversed", True),
             (stair, "manualStepCount", 10), (railing, "spacingBounds", (500, 800, 600)),
             (arrow, "solidTip", False), (arrow, "intensity", .5), (v.labels[0], "text", "Changed"))
    for obj, field, value in edits:
        old = v.SceneRenderKey(())
        setattr(obj, field, value)
        assert v.SceneRenderKey(()) != old, field
        CompareDirect(v)
    for edit in (lambda: wall.firstVertex.setY(20), lambda: wall.secondVertex.setX(1300),
                 lambda: wall.firstVertex.__iadd__(point(1, 2)), lambda: wall.firstVertex.__imul__(1.01),
                 lambda: v.walls.append(Wall(point(), point(0, 300))), lambda: v.walls.reverse(),
                 lambda: v.walls.__setitem__(slice(-1, None), [wall]),
                 lambda: v.objectGroups.append([wall, stair]), lambda: v.objectGroups[0].append(arrow),
                 lambda: v.hiddenObjectIds.add(arrow.objectId), lambda: v.hiddenObjectIds.clear()):
        old = v.SceneRenderKey(())
        edit()
        assert v.SceneRenderKey(()) != old
        CompareDirect(v)
    # Clones have owned coordinates and no observers copied from the old viewport.
    clone = copy.deepcopy(wall)
    old = v.SceneRenderKey(())
    clone.firstVertex.setX(123)
    assert v.SceneRenderKey(()) == old
    v.walls = [wall, stair, railing, arrow]
    v.verifyRenderRevisions = False
    with patch.object(v, "SceneRenderValueKey", side_effect = AssertionError("Camera frame scanned object values")):
        for frame in range(20):
            v.hoverPosition = point(100 + frame, 150)
            v.grab()
    v.isPanning = True
    v.grab()
    with patch.object(v, "ContainedWalls", wraps = v.ContainedWalls) as contained:
        for frame in range(20):
            v.panOffset += point(3, 1)
            v.grab()
        assert contained.call_count == 0, "Pan repeated containment preparation"
    v.isPanning = False
    before = v.CaptureState()
    wall.firstVertex.setY(200)
    v.RecordEdit(before)
    v.Undo()
    CompareDirect(v)
    v.Redo()
    CompareDirect(v)
    definition = next(iter(v.furnishingDefinitions.values()))
    furnishing = Furnishing(definition)
    v.furnishings = [furnishing]
    assert furnishing.definition is definition
    for index in range(100):
        furnishing.definition = dict(definition)
    assert len(v.renderChanges.DefinitionKeys()) == 1
    assert len(v.renderChanges.definitionOwners) == 1
    v.furnishings = []
    del furnishing
    gc.collect()
    assert v.renderChanges.DefinitionKeys() == ()
    assert not v.renderChanges.definitionOwners
    old = v.SceneRenderKey(())
    def PartialValues():
        yield Wall(point(), point(100, 0))
        raise ValueError("synthetic partial extend")
    try:
        v.walls.extend(PartialValues())
    except ValueError:
        pass
    assert v.SceneRenderKey(()) != old
    (Path(__file__).resolve().parent.parent / "diagnostics/scene-revisions-20261008.json").write_text(
        json.dumps({"warmFrames": 20, "valueKeyScans": 0, "panFrames": 20, "containmentPreparations": 0}) + "\n")
    v.close()


if __name__ == "__main__":
    Main()
