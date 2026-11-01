"""Local paint validation and exact cached coincident-record behavior."""
import copy
import gc
import json
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch
import weakref

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import (Wall, Pillar, Column, Counter, Stair, Railing, Elevator,
    Window, Door, PocketDoor, Fireplace, Furnishing, Label, NorthArrow)
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.viewport.widget import DrawingViewport
from planner_app.project_codec import EncodeObjectRecord
from fixtures.paint_preparation_reference_20261031 import ReferenceViewport
from fixtures.parity_examples import CreateObject, objectTypes


def Compare(view, reference, paint = False):
    for name in ("walls", "windows", "furnishings", "labels", "hiddenObjectIds", "visibility", "collisionSettings"):
        setattr(reference, name, getattr(view, name))
    assert view.InvalidArchitecturalObjects() == reference.InvalidArchitecturalObjects()
    for includeHidden in (False, True):
        actual = view.CoincidentObjectGroups(includeHidden)
        expected = reference.CoincidentObjectGroups(includeHidden)
        assert [[id(obj) for obj in group] for group in actual] == [[id(obj) for obj in group] for group in expected]
    assert view.collisionPassCache is None
    if paint:
        images = []
        for viewport in (view, reference):
            image = QtGui.QImage(viewport.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QtCore.Qt.GlobalColor.transparent)
            viewport.render(image)
            images.append(image)
        assert images[0] == images[1], "Paint preparation changed exact editor pixels"


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyle("Fusion")
    LoadApplicationFonts(app)
    view, reference = DrawingViewport(), ReferenceViewport()
    point = QtCore.QPointF
    for viewport in (view, reference):
        viewport.resize(1000, 800)
        viewport.showMeasurements = viewport.showTips = False
        viewport.performanceTimer.stop()
    view.walls = [Wall(point(index * 6000, 0), point(index * 6000 + 4000, 0), 200) for index in range(128)]
    desk = Furnishing(view.furnishingDefinitions["desk"], point(0, 6000))
    label = Label(point(0, 8000), "Label")
    view.furnishings, view.labels = [desk], [label]
    Compare(view, reference)
    with patch.object(view, "ArchitecturalPlacementFits", wraps = view.ArchitecturalPlacementFits) as fits, \
         patch.object(view, "JoinedObjectBounds", wraps = view.JoinedObjectBounds) as bounds:
        for frame in range(8):
            desk.firstVertex += point(3, 0)
            desk.secondVertex += point(3, 0)
            view.InvalidArchitecturalObjects()
        assert fits.call_count == 0 and bounds.call_count == 8
        bounds.reset_mock()
        label.firstVertex += point(4, 2)
        label.secondVertex += point(4, 2)
        view.InvalidArchitecturalObjects()
        assert bounds.call_count == 0 and fits.call_count == 0
    for x, y in ((1000, 0), (7000, 0), (13000, 0), (13000, 6000), (1000, 0)):
        center = (desk.firstVertex + desk.secondVertex) / 2
        delta = point(x, y) - center
        desk.firstVertex += delta
        desk.secondVertex += delta
        with patch.object(view, "ArchitecturalPlacementFits", wraps = view.ArchitecturalPlacementFits) as fits:
            Compare(view, reference)
            assert fits.call_count <= 2, fits.call_count
    # Failure must not advance old bounds or discard the dirty notifications.
    center = (desk.firstVertex + desk.secondVertex) / 2
    desk.firstVertex += point(7000, 0) - center
    desk.secondVertex += point(7000, 0) - center
    previous = view.architecturalValidation
    with patch.object(view, "ArchitecturalPlacementFits", side_effect = RuntimeError("probe")):
        try:
            view.InvalidArchitecturalObjects()
        except RuntimeError:
            pass
        else:
            raise AssertionError("Expected validation failure")
    assert view.architecturalValidation is previous and view.collisionPassCache is None
    Compare(view, reference)
    view.renderChanges.Bump("geometry")
    with patch.object(view, "PlacementBlockers", wraps = view.PlacementBlockers) as blockers:
        Compare(view, reference)
        assert blockers.call_count >= len(view.walls), "Unknown geometry edits must retain full validation"

    host = Wall(point(-2500, 0), point(2500, 0), 240)
    view.walls = [host, Wall(point(2500, 0), point(2500, 2200), 600, firstMiter = 2),
                  Pillar(point(-1700, 1300), point(-1700, 2000), 500),
                  Column(point(800, 1000), point(800, 1600), 600),
                  Counter(point(-1800, -1000), point(1800, -1000), 500),
                  Stair(point(-1700, 1700), point(1200, 1700), 600),
                  Railing(point(-1500, -1800), point(1600, -1800), 120),
                  Elevator(point(1900, 1000), point(1900, 2000), 700)]
    view.windows = [Door(host, .1, .25), Window(host, .35, .5), PocketDoor(host, .55, .9), Fireplace(host, .92, .97)]
    other = Furnishing(next(definition for definition in view.furnishingDefinitions.values() if definition.get("components")))
    # Ordinary and compound furnishing geometry use the same collision predicates.
    view.furnishings = [desk, other, NorthArrow(point(3000, 4000))]
    view.labels = [label]
    Compare(view, reference)
    randomizer = random.Random(20261031)
    for frame in range(100):
        moving = desk if frame % 2 else other
        center = (moving.firstVertex + moving.secondVertex) / 2
        delta = point(randomizer.uniform(-3000, 3000), randomizer.uniform(-2200, 2200)) - center
        moving.firstVertex += delta
        moving.secondVertex += delta
        if frame % 7 == 0:
            moving.width = randomizer.uniform(200, 2200)
        if frame % 11 == 0:
            moving.angle += 21
        Compare(view, reference, paint = frame % 10 == 0)
    for category in view.collisionSettings:
        view.collisionSettings[category] = False
        Compare(view, reference)
        view.collisionSettings[category] = True
    view.hiddenObjectIds = {id(view.walls[2]), id(desk)}
    Compare(view, reference)
    view.visibility["Walls"] = False
    Compare(view, reference)
    view.visibility["Walls"] = True
    for obj, name, value in ((host, "width", 400), (view.windows[0], "length", 6000),
                             (view.walls[1], "firstMiter", .4)):
        setattr(obj, name, value)
        Compare(view, reference)

    view.walls = [Wall(point(), point(3000, 0))]
    view.windows, view.labels = [], []
    view.hiddenObjectIds = set()
    view.furnishings = [Furnishing(view.furnishingDefinitions["desk"], point(index * 4000, 6000)) for index in range(258)]
    view.InvalidArchitecturalObjects()
    for index, obj in enumerate(view.furnishings):
        obj.firstVertex += point(1, 0)
        obj.secondVertex += point(1, 0)
        view.InvalidArchitecturalObjects()
        if index in (0, 127, 255, 256, 257):
            Compare(view, reference)
    assert len(view.architecturalValidation[3]["scope"]["movingBounds"]) <= 256

    # Every supported object type retains the exact persistence-derived key.
    objects = [CreateObject(view, name) for name in objectTypes]
    duplicates = []
    for obj in objects:
        duplicate = CreateObject(view, type(obj).__name__)
        if isinstance(obj, Window):
            duplicate.parentWall = obj.parentWall
        duplicates.append(duplicate)
    view.walls = [obj for obj in objects + duplicates if isinstance(obj, Wall)]
    view.walls.extend(obj.parentWall for obj in objects if isinstance(obj, Window))
    view.windows = [obj for obj in objects + duplicates if isinstance(obj, Window)]
    view.furnishings = [obj for obj in objects + duplicates if isinstance(obj, Furnishing) and not isinstance(obj, Label)]
    view.labels = [obj for obj in objects + duplicates if isinstance(obj, Label)]
    reference.walls, reference.windows, reference.furnishings, reference.labels = view.walls, view.windows, view.furnishings, view.labels
    def CompareGroups():
        for hidden in (False, True):
            assert [[id(obj) for obj in group] for group in view.CoincidentObjectGroups(hidden)] == [
                [id(obj) for obj in group] for group in reference.CoincidentObjectGroups(hidden)]
        ordered = view.walls + view.windows + sorted(view.furnishings, key = lambda obj: not obj.behindCounters) + view.labels
        indices = {id(obj): index for index, obj in enumerate(ordered)}
        for obj in ordered:
            cached = obj.__dict__.get("_coincidentRecordCache")
            if cached is not None:
                record = EncodeObjectRecord(obj, indices)
                for name in ("id", "measurementHidden", "measurementFlipped", "geometryIssues"):
                    record.pop(name, None)
                assert cached[1] == json.dumps(record, sort_keys = True, separators = (",", ":")), type(obj).__name__
    CompareGroups()
    with patch("planner_app.object_schema.EncodeObjectRecord", wraps = EncodeObjectRecord) as encode:
        view.CoincidentObjectGroups()
        assert encode.call_count == 0, "Unchanged objects were serialized again"
        objects[0].firstVertex.setX(objects[0].firstVertex.x() + .125)
        view.CoincidentObjectGroups()
        assert encode.call_count == 1
    fields = ("width", "material", "firstMiter", "secondMiter", "centerFraction", "length", "text", "intensity",
              "hingeAtSecond", "swingsOutwards", "panelsFlipped", "sillDepth", "windowWell", "wellDepth", "wellDashed",
              "solidTip", "tipSize", "directionReversed", "autosize", "manualStepCount", "manualPostCount", "unitsOverride")
    mutations = 0
    for obj in objects:
        for name in fields:
            if name not in obj.__dict__:
                continue
            old = getattr(obj, name)
            if type(old) is bool:
                value = not old
            elif type(old) in (int, float):
                value = old + 1
            elif type(old) is str:
                value = old + " changed"
            else:
                continue
            setattr(obj, name, value)
            CompareGroups()
            mutations += 1
    wall = objects[0]
    for value in (100, 100.0, 0.0, -0.0):
        wall.width = value
        CompareGroups()
    for value in (None, "Brick", 1, 1.0, 0.0, -0.0, {"nested": [1]}):
        wall.originalMaterial = value
        CompareGroups()
    wall.originalMaterial["nested"].append(2)
    CompareGroups()
    fireplace = next(obj for obj in objects if type(obj) is Fireplace)
    fireplace.parentWall.width += 1000
    CompareGroups()
    fireplace.manualDepth = 100
    fireplace.geometryIssues = ["fireplace_bounds"]
    CompareGroups()
    fireplace.geometryIssues.clear()
    CompareGroups()
    view.walls.reverse()
    reference.walls = view.walls
    CompareGroups()
    label = next(obj for obj in objects if type(obj) is Label)
    label.text = "x" * 10000
    CompareGroups()
    assert "_coincidentRecordCache" not in label.__dict__
    assert "_coincidentRecordCache" not in copy.deepcopy(wall).__dict__
    assert "_coincidentRecordCache" not in wall.__getstate__()

    # Clear project-owned references, including the stationary broad phase.
    view.walls = [Wall(point(), point(2000, 0))]
    view.windows, view.labels, view.furnishings = [], [], []
    view.InvalidArchitecturalObjects()
    oldWall = weakref.ref(view.walls[0])
    view.walls = []
    view.ClearGeometryCaches()
    gc.collect()
    assert oldWall() is None and view.renderChanges.placementChanges is None
    assert not hasattr(view, "architecturalValidation")
    for viewport in (view, reference):
        viewport.close()
    print(f"PASS: local validation, failure recovery, bounded overlay, exact pixels, all object types and {mutations} comparison mutations.")


if __name__ == "__main__":
    Main()
