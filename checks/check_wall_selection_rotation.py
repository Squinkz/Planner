"""Wall/mixed selection rotation preserves junctions, children, copies and history."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Door, Window, Fireplace, Furnishing
from check_rotation_pivots import Mouse


def RotatePoint(point, pivot, degrees):
    radians = math.radians(degrees)
    offset = point - pivot
    return pivot + QtCore.QPointF(offset.x() * math.cos(radians) - offset.y() * math.sin(radians),
                                 offset.x() * math.sin(radians) + offset.y() * math.cos(radians))


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        point = QtCore.QPointF
        none, shift = QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.KeyboardModifier.ShiftModifier
        release = QtCore.QEvent.Type.MouseButtonRelease

        def Fixture(connectedObjects = False):
            first = Wall(point(-1600, 0), point(400, 0), 200, material = "Brick")
            second = Wall(point(400, 0), point(400, 1800), 120)
            neighbor = Wall(point(400, 1800), point(2400, 1800), 150)
            door = Door(first, .15, .40)
            window = Window(second, .25, .50)
            fireplace = Fireplace(first, .65, .95)
            fireplace.depth = 400
            furnishing = Furnishing(v.furnishingDefinitions["desk"], point(-1200, 2400))
            furnishing.width = 300
            furnishing.secondVertex = furnishing.firstVertex + point(0, 300)
            InstallScene(main, [first, second, neighbor, door, window, fireplace, furnishing])
            v.snapEnabled = False
            v.connectedEnabled = v.connectedVerticesEnabled = True
            v.connectedObjectsEnabled = connectedObjects
            v.zoom = .5
            v.SetSelection([(first, None), (second, None), (furnishing, None), (door, None)])
            v.rotationPivot = point(-800, 900)
            v.undoHistory, v.redoHistory = [], []
            return first, second, neighbor, door, window, fireplace, furnishing

        def Begin():
            visible = v.VisibleFurnishingHandles()
            assert len(visible) == 1 and {handle[0] for obj, handles in visible for handle in handles} == {"rotate", "pivot"}
            box, handles = visible[0]
            handle = next(handle for handle in handles if handle[0] == "rotate")
            Mouse(v, QtCore.QEvent.Type.MouseButtonPress, handle[3])
            assert v.furnishingHandleDrag is not None
            return point(v.furnishingHandleDrag["pivot"]), v.ViewportToWorld(handle[3])

        for connectedObjects in (False, True):
            first, second, neighbor, door, window, fireplace, furnishing = Fixture(connectedObjects)
            if not connectedObjects:
                v.rotationPivot = None
            before = v.CaptureState()
            originalVertices = [(obj, point(obj.firstVertex), point(obj.secondVertex)) for obj in (first, second, neighbor, furnishing)]
            openingValues = [(obj, obj.parentWall, obj.centerFraction, obj.length) for obj in (door, window, fireplace)]
            pivot, start = Begin()
            for degrees in (15, 45, 90, 180, 270, 360, 37):
                end = v.WorldToViewport(RotatePoint(start, pivot, degrees))
                v.UpdateFurnishingHandleDrag(end, none)
                for obj, a, b in originalVertices:
                    expectedFirst = RotatePoint(a, pivot, degrees)
                    expectedSecond = b if obj is neighbor and not connectedObjects else RotatePoint(b, pivot, degrees)
                    assert QtCore.QLineF(obj.firstVertex, expectedFirst).length() < 1e-6
                    assert QtCore.QLineF(obj.secondVertex, expectedSecond).length() < 1e-6
                assert first.secondVertex == second.firstVertex and second.secondVertex == neighbor.firstVertex
                for obj, parent, fraction, length in openingValues:
                    assert obj.parentWall is parent and math.isclose(obj.centerFraction, fraction, abs_tol = 1e-8)
                    assert math.isclose(obj.length, length, abs_tol = 1e-8)
                assert v.rotationPivot == pivot
                v.grab()  # Preview painting must accept walls and read-only opening vertices.
            Mouse(v, release, end)
            assert len(v.undoHistory) == 1
            nextPivot, nextStart = Begin()
            assert nextPivot == pivot
            v.CancelInteraction()
            v.Undo()
            assert v.CaptureState()[0] == before[0] and v.CaptureState()[3] == before[3]
            v.Redo()
            assert QtCore.QLineF(first.firstVertex, RotatePoint(originalVertices[0][1], pivot, 37)).length() < 1e-6

        # Shift copies selected walls and all their children, never the attached
        # unselected neighbor; modifier toggles restore original geometry first.
        first, second, neighbor, door, window, fireplace, furnishing = Fixture(True)
        v.objectGroups = [(first, second, furnishing)]
        v.rotationPivot = point(-6000, -6000)
        before = v.CaptureState()
        pivot, start = Begin()
        end = v.WorldToViewport(RotatePoint(start, pivot, 90))
        for modifiers in (none, shift, none, shift):
            v.UpdateFurnishingHandleDrag(end, modifiers)
            assert v.furnishingHandleDrag["rotationValid"], modifiers
            if modifiers == shift:
                assert len(v.walls) == 5 and len(v.windows) == 6 and len(v.furnishings) == 2
                assert v.CaptureState()[0][:3] == before[0]
                copies = [obj for obj, index in v.SelectionEntries()]
                copiedFirst = next(obj for obj in copies if type(obj) is Wall and obj.width == first.width)
                copiedSecond = next(obj for obj in copies if type(obj) is Wall and obj.width == second.width)
                assert copiedFirst.secondVertex == copiedSecond.firstVertex
                for child in v.windows[3:]:
                    assert child.parentWall in (copiedFirst, copiedSecond)
                    original = next(obj for obj in (door, window, fireplace) if type(obj) is type(child))
                    assert math.isclose(child.length, original.length) and child.centerFraction == original.centerFraction
                    assert child.measurementHidden == original.measurementHidden
                    if isinstance(child, Fireplace):
                        assert (child.depth, child.depthOffset, child.material) == (original.depth, original.depthOffset, original.material)
                assert len(v.objectGroups) == 2
            else:
                assert len(v.walls) == 3 and len(v.windows) == 3 and len(v.furnishings) == 1
        Mouse(v, release, end, shift)
        assert v.rotationPivot == pivot and len(v.undoHistory) == 1
        assert len(v.SelectionEntries()) == 4
        v.Undo()
        assert v.CaptureState()[0] == before[0] and v.CaptureState()[3] == before[3]
        v.Redo()
        assert len(v.walls) == 5 and len(v.windows) == 6

        # Pure wall selections expose the same handles without a furnishing or
        # explicit rotation-mode toggle; vertex selections still use vertex edits.
        first, second, neighbor, door, window, fireplace, furnishing = Fixture(True)
        v.SetSelection([(first, None), (second, None), (neighbor, None)])
        v.rotationPivot = None
        before = v.CaptureState()
        pivot, start = Begin()
        end = v.WorldToViewport(RotatePoint(start, pivot, 90))
        v.UpdateFurnishingHandleDrag(end, none)
        Mouse(v, release, end)
        assert len(v.undoHistory) == 1 and v.rotationPivot == pivot
        v.Undo()
        assert v.CaptureState()[0] == before[0] and v.CaptureState()[3] == before[3]
        v.SetSelection([(first, 0), (second, 1)])
        assert v.FurnishingSelectionBox() is None

        for modifiers in (none, shift):
            Fixture()
            before = v.CaptureState()
            pivot, start = Begin()
            v.UpdateFurnishingHandleDrag(v.WorldToViewport(RotatePoint(start, pivot, 63)), modifiers)
            v.CancelInteraction()
            assert v.CaptureState() == before and not v.undoHistory

        # Turning off both connection options leaves the neighboring wall alone.
        first, second, neighbor, door, window, fireplace, furnishing = Fixture()
        v.connectedVerticesEnabled = v.connectedObjectsEnabled = False
        originalNeighbor = (point(neighbor.firstVertex), point(neighbor.secondVertex))
        pivot, start = Begin()
        v.snapEnabled = True
        v.UpdateFurnishingHandleDrag(v.WorldToViewport(RotatePoint(start, pivot, 37)), none)
        assert (neighbor.firstVertex, neighbor.secondVertex) == originalNeighbor
        assert QtCore.QLineF(first.firstVertex, RotatePoint(point(-1600, 0), pivot, 30)).length() < 1e-6
        v.UpdateFurnishingHandleDrag(v.WorldToViewport(RotatePoint(start, pivot, 37)), QtCore.Qt.KeyboardModifier.AltModifier)
        assert QtCore.QLineF(first.firstVertex, RotatePoint(point(-1600, 0), pivot, 37)).length() < 1e-6
        v.CancelInteraction()

        # Obstructing an attached door rejects the whole edit, including copies.
        for modifiers in (none, shift):
            first, second, neighbor, door, window, fireplace, furnishing = Fixture(True)
            v.rotationPivot = point(-6000, -6000)
            pivot = point(v.rotationPivot)
            blocker = Wall(RotatePoint(door.firstVertex, pivot, 90), RotatePoint(door.secondVertex, pivot, 90), 500)
            v.walls.append(blocker)
            before = v.CaptureState()
            pivot, start = Begin()
            end = v.WorldToViewport(RotatePoint(start, pivot, 90))
            v.UpdateFurnishingHandleDrag(end, modifiers)
            assert not v.furnishingHandleDrag["rotationValid"]
            v.grab()
            Mouse(v, release, end, modifiers)
            assert v.CaptureState() == before and not v.undoHistory

        # A selected opening on a stationary wall cannot be rotated off it.
        first, second, neighbor, door, window, fireplace, furnishing = Fixture()
        v.connectedEnabled = False
        v.SetSelection([(second, None), (door, None)])
        before = v.CaptureState()
        pivot, start = Begin()
        end = v.WorldToViewport(RotatePoint(start, pivot, 45))
        v.UpdateFurnishingHandleDrag(end, none)
        assert not v.furnishingHandleDrag["rotationValid"]
        Mouse(v, release, end)
        assert v.CaptureState() == before and not v.undoHistory

    print("Wall selection rotation: full turns, mixed objects, connected vertices/objects, openings, Shift, undo/redo and cancellation passed")


if __name__ == "__main__":
    Main()
