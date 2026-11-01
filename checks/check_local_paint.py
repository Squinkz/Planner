"""Exact structural-neighborhood validation against frozen full preparation."""
from contextlib import ExitStack, contextmanager
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "tools")]
from PySide6 import QtCore, QtGui, QtWidgets
from fixtures.editor_interactions import PrepareScene, BeginEndpoint, wallCases
from fixtures.local_paint_reference_20261101 import ReferencePlacement
from planner_app.viewport.placement import PlacementMixin
from fixtures.parity_examples import ExampleWindow
from check_drag_fitting_preparation import Snapshot
from planner_app.models import Wall, Pillar, Column, Counter, Stair, Railing, Elevator, Door, Window, CasementWindow, PocketDoor, Furnishing
from planner_app.viewport.widget import DrawingViewport


@contextmanager
def Baseline(enabled):
    with ExitStack() as stack:
        if enabled:
            for name in ("InvalidArchitecturalObjects", "RefreshArchitecturalValidation", "PlacementBlockers"):
                stack.enter_context(patch.object(PlacementMixin, name, getattr(ReferencePlacement, name)))
        yield


def Compare(view, reference):
    for name in ("walls", "windows", "furnishings", "labels", "visibility", "hiddenObjectIds", "collisionSettings"):
        setattr(reference, name, getattr(view, name))
    actual = view.InvalidArchitecturalObjects()
    with Baseline(True):
        expected = reference.InvalidArchitecturalObjects()
    assert actual == expected, ("invalid architecture", actual ^ expected)


def CheckDependencies():
    point = QtCore.QPointF
    randomizer = random.Random(20261101)
    comparisons = 0
    for case in range(4):
        view, reference = DrawingViewport(furnishingDefinitions = {}), DrawingViewport(furnishingDefinitions = {})
        offset = point(1e8, -1e8) if case == 3 else point()
        source = Wall(offset, offset + point(6000, 0), 200)
        neighbor = Wall(offset + point(6000, 0), offset + point(6000, 4000), 300)
        acute = Wall(offset + point(6000, 0), offset + point(10000, .1), 150)
        walls = [source, neighbor, acute] + [Wall(offset + point(index * 2000, 6000),
            offset + point(index * 2000 + 1500, 6500), 180) for index in range(30)]
        walls += [Counter(offset + point(2000, 500), offset + point(4000, 500), 600),
                  Stair(offset + point(4500, 1000), offset + point(4500, 4000), 1000),
                  Railing(offset + point(0, 1500), offset + point(3000, 1500), 100),
                  Elevator(offset + point(8000, 3000), offset + point(8000, 5000), 1500)]
        if case == 1:
            walls += [Pillar(offset + point(3000, -100), offset + point(3000, 700), 500),
                      Column(offset + point(6500, 1500), offset + point(6500, 2500), 600)]
        definition = dict(key = "test", width = 600, length = 600)
        desk = Furnishing(definition, offset + point(12000, 3000))
        view.walls = walls
        view.windows = [Door(source, .2, .35), CasementWindow(neighbor, .2, .4)]
        view.windows += [Window(wall, .2, .4) for wall in walls[3:15]]
        if case == 2:
            view.windows.append(PocketDoor(source, .6, .8))
        view.furnishings = [desk]
        view.collisionSettings = dict(walls = True, architectural = True, furnishings = True)
        Compare(view, reference)
        assert "wallFootprints" not in view.architecturalValidation[3], "Static views retained wall-edit snapshots"
        assert "bounds" not in view.architecturalValidation[3]["scope"]
        if case == 3:
            for distance in (.0099999, .0100001, .00999998, .01000002):
                source.secondVertex = offset + point(6000, distance)
                Compare(view, reference)
                comparisons += 1
        for endpoint in (offset, offset + point(6000, 0)):
            source.secondVertex = endpoint
            Compare(view, reference)
            comparisons += 1
        reusedIndices = 0
        for frame in range(48):
            oldIndex = view.architecturalValidation[3]["scope"]["index"]
            if frame % 12 == 0:
                mask = frame // 12
                view.collisionSettings = dict(walls = bool(mask & 1), architectural = True, furnishings = bool(mask & 2))
            endpoint = offset + point(4500 + randomizer.uniform(-800, 2000), randomizer.uniform(-500, 1500))
            if frame % 2:
                source.secondVertex.setX(endpoint.x())
                source.secondVertex.setY(endpoint.y())
            else:
                source.secondVertex = endpoint
            if frame % 7 == 0:
                source.firstMiter = 1 + randomizer.random() * 2
                source.width = randomizer.uniform(120, 420)
            if frame % 11 == 0:
                view.windows[0].centerFraction = randomizer.uniform(.1, .8)
            Compare(view, reference)
            if oldIndex is not None and view.architecturalValidation[3]["scope"]["index"] is oldIndex:
                reusedIndices += 1
            comparisons += 1
            # A furnishing must query the current structural overlay, even if
            # the original spatial index stored this wall somewhere else.
            if frame % 4 == 1:
                delta = (source.firstVertex + source.secondVertex) / 2 - (desk.firstVertex + desk.secondVertex) / 2
                desk.firstVertex += delta
                desk.secondVertex += delta
                Compare(view, reference)
                comparisons += 1
            if frame % 9 == 0:
                walls[-1].secondVertex += point(10, 20)
                Compare(view, reference)
                comparisons += 1
        if case != 2:
            assert reusedIndices > 0, ("No structural incremental commits exercised", case)
        # A failed incremental predicate may not publish new bounds or discard
        # the edit journal. The retry must still query both old and new areas.
        if case == 0:
            isolated = walls[10]
            isolated.firstVertex += point(100000, 100000)
            isolated.secondVertex += point(100000, 100000)
            view.collisionSettings = dict(walls = True, architectural = True, furnishings = True)
            Compare(view, reference)
            # Seed at the original index location, then move the wall under
            # unchanged policy so only the overlay knows its current position.
            isolated.firstVertex += point(100000, 100000)
            isolated.secondVertex += point(100000, 100000)
            Compare(view, reference)
            delta = (isolated.firstVertex + isolated.secondVertex) / 2 - (desk.firstVertex + desk.secondVertex) / 2
            desk.firstVertex += delta
            desk.secondVertex += delta
            Compare(view, reference)
            comparisons += 3
            source.secondVertex += point(25, 15)
            previous = view.architecturalValidation
            events = view.renderChanges.placementChanges["events"]
            with patch.object(view, "ArchitecturalPlacementFits", side_effect = RuntimeError("fixture")):
                try:
                    view.InvalidArchitecturalObjects()
                except RuntimeError as error:
                    assert str(error) == "fixture"
                else:
                    raise AssertionError("Failure fixture did not exercise validation")
            assert view.architecturalValidation is previous
            assert view.renderChanges.placementChanges["events"] == events
            Compare(view, reference)
            comparisons += 1
        view.ClearGeometryCaches()
        reference.ClearGeometryCaches()
        view.deleteLater()
        reference.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    return comparisons


def CheckProject():
    comparisons = 0
    movedWalls = set()
    modifier = QtCore.Qt.KeyboardModifier
    with ExitStack() as stack:
        windows = [stack.enter_context(ExampleWindow())[0] for variant in range(2)]
        for main in windows:
            main.hide()
        views = []
        for variant, main in enumerate(windows):
            with Baseline(variant == 0):
                views.append(PrepareScene(main, "drag", False, 1000, 800))
        cases = [(wallId, vertex, mask, modifier.NoModifier)
                 for wallId, vertex in wallCases for mask in range(8)]
        cases.extend((wallCases[0][0], 1, mask, modifiers) for mask in (0, 7)
                     for modifiers in (modifier.ControlModifier, modifier.AltModifier,
                                       modifier.ControlModifier | modifier.AltModifier))
        for wallId, vertex, mask, modifiers in cases:
            for variant, view in enumerate(views):
                with Baseline(variant == 0):
                    view.CancelInteraction()
                    for index, name in enumerate(("walls", "architectural", "furnishings")):
                        view.collisionSettings[name] = bool(mask & (1 << index))
                    BeginEndpoint(view, next(wall for wall in view.walls if wall.objectId == wallId), vertex)
            source = next(wall for wall in views[1].walls if wall.objectId == wallId)
            before = QtCore.QPointF(source.firstVertex), QtCore.QPointF(source.secondVertex)
            for frame in range(3):
                images, invalid = [], []
                for variant, view in enumerate(views):
                    with Baseline(variant == 0):
                        view.UpdateInteraction(view.dragStart + QtCore.QPointF(25 + frame * 7, 17 - frame * 11), modifiers)
                        images.append(view.grab().toImage())
                        bad = view.InvalidArchitecturalObjects()
                        invalid.append({obj.objectId for obj in view.walls + view.windows if id(obj) in bad})
                assert Snapshot(views[0]) == Snapshot(views[1]), ("model state", wallId, mask, frame)
                assert invalid[0] == invalid[1], ("validation", wallId, mask, frame)
                assert images[0] == images[1], ("pixels", wallId, mask, frame)
                if (source.firstVertex, source.secondVertex) != before:
                    movedWalls.add(wallId)
                comparisons += 1
        for view in views:
            view.CancelInteraction()
    assert movedWalls == {wallId for wallId, vertex in wallCases}, "Parity matrix never moved one of its wall fixtures"
    return comparisons


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    view = DrawingViewport(furnishingDefinitions = {})
    oversized = QtGui.QPainterPath()
    for index in range(40000):
        oversized.lineTo(index, index % 3)
    view.collisionPassCache = {}
    assert view.WallValidationKeys({1: oversized}, {}) is None
    assert not view.collisionPassCache, "Oversized snapshots retained element copies"
    view.deleteLater()
    dependencies = CheckDependencies()
    frames = CheckProject()
    print(f"PASS: {dependencies} exact full/incremental dependency comparisons with junctions, openings, pillars, columns, "
          f"pocket-door fallback, large coordinates, furnishing overlays and exception retry; {frames} exact synthetic frames.")


if __name__ == "__main__":
    Main()
