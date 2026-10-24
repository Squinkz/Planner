"""Exact pre-extraction group travel, mutations, copies and attachment parity."""
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
    from planner_app.geometry.group_movement import (ProjectGroupTravel, GroupOpeningLimits,
        BoundGroupTravel, TranslatedOpeningFraction, AttachedConstraintPoint)
    assert ProjectGroupTravel((4, 7), [(10, 0), (-10, 0)]) == ((4, 0), (-1, 0), False)
    assert ProjectGroupTravel((4, 7), [(10, 0), (0, 10)]) == ((0, 0), (1, 0), True)
    assert GroupOpeningLimits((1, 0), [(1, (10, 0), 10, .5, 2, None)], {}) == (-4, 4)
    assert BoundGroupTravel((6, 4), (1, 0), -4, 4) == (4, 0)
    assert TranslatedOpeningFraction(.5, (2, 4), (10, 0)) == .7
    assert TranslatedOpeningFraction(.5, (2, 4), (0, 0)) is None
    assert AttachedConstraintPoint((0, 0), (10, 0), .5, 2) == (5, 2)
    print("PASS: numeric group constraints without Qt/site packages")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtWidgets
    from planner_app.models import (Wall, Door, Window, Fireplace, Furnishing, Stair, SlidingDoor,
        PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, OpenDoorway)
    from planner_app.viewport.widget import DrawingViewport
    from planner_app.geometry.group_movement import (ProjectGroupTravel, GroupOpeningLimits,
        BoundGroupTravel, TranslatedOpeningFraction, AttachedConstraintPoint)
    from fixtures.qt_group_movement_reference_20261016 import ReferenceScene

    class ReferenceViewport(DrawingViewport):
        StartGroupDrag = ReferenceScene.StartGroupDrag
        UpdateGroupDrag = ReferenceScene.UpdateGroupDrag

    app = QtWidgets.QApplication([])
    p = QtCore.QPointF
    randomizer = random.Random(204024)
    for case in range(1200):
        delta = p(randomizer.uniform(-10000, 10000), randomizer.uniform(-10000, 10000))
        angle = randomizer.uniform(-math.pi, math.pi)
        directions = [p(math.cos(angle + index * (1e-8 if case % 3 else .1)),
                        math.sin(angle + index * (1e-8 if case % 3 else .1))) * (1000 + index) for index in range(case % 5)]
        travel, expected, blocked = None, p(delta), False
        for direction in directions:
            direction = p(direction)
            length = math.hypot(direction.x(), direction.y())
            if length > 1e-10:
                direction /= length
                if travel is not None and abs(travel.x() * direction.y() - travel.y() * direction.x()) > 1e-6:
                    expected, blocked = p(), True
                    break
                travel = direction
                expected = direction * QtCore.QPointF.dotProduct(expected, direction)
        computed = ProjectGroupTravel((delta.x(), delta.y()), [(value.x(), value.y()) for value in directions])
        assert computed == ((expected.x(), expected.y()), (travel.x(), travel.y()) if travel is not None else None, blocked), ("travel", case)
        offset = p(1e8, -1e8) if case % 4 == 0 else p()
        first, second = offset + p(case * .3, -case * .2), offset + p(case * .7 + 100, case * .4)
        direction = second - first
        length = math.hypot(direction.x(), direction.y())
        normal = p(-direction.y(), direction.x()) / length if length > 1e-10 else p()
        fraction, normalOffset = case * .001, case * .13
        expectedPoint = first + direction * fraction + normal * normalOffset
        assert AttachedConstraintPoint((first.x(), first.y()), (second.x(), second.y()), fraction, normalOffset) == (expectedPoint.x(), expectedPoint.y()), ("attachment", case)
        expectedFraction = fraction + QtCore.QPointF.dotProduct(delta, direction) / QtCore.QPointF.dotProduct(direction, direction)
        assert TranslatedOpeningFraction(fraction, (delta.x(), delta.y()), (direction.x(), direction.y())) == expectedFraction

    classes = (Window, Door, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, OpenDoorway, Fireplace)
    def Setup(view, case):
        view.CancelInteraction()
        offset = p(1e8, -1e8) if case % 7 == 0 else p()
        angle = case * .103
        axis = p(math.cos(angle), math.sin(angle))
        normal = p(-axis.y(), axis.x())
        kind = case % 10
        walls = [Wall(offset, offset + axis * 8000, 240),
                 Wall(offset + normal * 2200, offset + normal * 2200 + axis * 8000, 240)]
        if kind == 1:
            walls[1].firstVertex, walls[1].secondVertex = walls[1].secondVertex, walls[1].firstVertex
        elif kind == 2:
            walls[1].secondVertex = walls[1].firstVertex + normal * 8000
        elif kind == 3:
            walls[1].secondVertex += normal * .003
        openings = [classes[case % 10](walls[0], .35, .5), classes[(case + 1) % 10](walls[1], .35, .5),
                    Door(walls[0], .1, .22), Window(walls[0], .72, .85), Door(walls[1], .75, .9)]
        furnishing = Furnishing({"key": "test", "name": "Test", "width": 500, "length": 600}, offset + normal * 5000)
        view.furnishingDefinitions["test"] = furnishing.definition
        view.walls, view.windows, view.furnishings, view.labels = walls, openings, [furnishing], []
        view.connectedEnabled = bool(case % 4 == 0)
        view.connectedObjectsEnabled, view.connectedVerticesEnabled = bool(case % 3), bool(case % 2)
        view.snapEnabled, view.midpointSnapEnabled = bool(case % 2), bool(case % 3)
        view.unitsMode = "Feet and Inches" if case % 3 == 0 else "Millimeters"
        view.zoom = (.2, .6, 2)[case % 3]
        view.panOffset = p(case * 2, -case * 3)
        entries = [(openings[0], None), (openings[1], None)]
        if kind == 4:
            entries = [(walls[0], None), (openings[0], None), (openings[1], None)]
        elif kind == 5:
            entries = [(openings[0], 0), (openings[1], 1)]
        elif kind == 6:
            entries += [(openings[0], 0)]
        elif kind == 7:
            entries = [(walls[0], None), (walls[1], None)]
        elif kind == 8:
            entries += [(furnishing, None)]
        elif kind == 9:
            entries = [(walls[0], 1), (openings[1], None)]
        view.SetSelection(entries)
        view.dragVertices = None if isinstance(view.selectedWall, Window) else (p(view.selectedWall.firstVertex), p(view.selectedWall.secondVertex))
        view.dragSourceVertices = view.dragVertices
        view.interactionBefore = view.CaptureState()
        view.dragStart, view.isDragging = p(100, 100), True
        view.StartGroupDrag()
        if kind == 9:
            # The current attachment selector normally supplies rigid vertices.
            # Also preserve the legacy ordered constraint-loop contract.
            view.dragConstraints = [(walls[1], 0, walls[0], .3, 2200), (walls[1], 1, walls[0], .8, 2200)]

    def Snapshot(view):
        objects = view.walls + view.windows + view.furnishings + view.labels
        ids = {id(obj): index for index, obj in enumerate(objects)}
        def Ref(obj):
            return ids.get(id(obj))
        def Points(obj):
            return obj.firstVertex.x(), obj.firstVertex.y(), obj.secondVertex.x(), obj.secondVertex.y()
        return ([tuple([type(obj).__name__, *Points(obj), obj.width]) for obj in view.walls + view.furnishings],
                [(type(obj).__name__, Ref(obj.parentWall), obj.centerFraction, obj.length,
                  getattr(obj, "swingsOutwards", None), getattr(obj, "hingeAtSecond", None),
                  (obj.depth, obj.depthOffset) if isinstance(obj, Fireplace) else None) for obj in view.windows],
                [(Ref(obj), index) for obj, index in view.SelectionEntries()],
                [(Ref(obj), index) for obj, index in view.groupMovedOpenings],
                list(view.alignmentGuides), view.snapApplied, view.snapPriority)

    actual, reference = DrawingViewport(), ReferenceViewport()
    frameCount = 0
    for case in range(120):
        for view in (actual, reference):
            Setup(view, case)
        for frame in range(4):
            modifiers = QtCore.Qt.KeyboardModifier.NoModifier
            if frame == 1 and case % 3 == 0:
                modifiers |= QtCore.Qt.KeyboardModifier.ShiftModifier
            if frame == 2 and case % 4 == 0:
                modifiers |= QtCore.Qt.KeyboardModifier.ControlModifier
            if frame == 3 and case % 5 == 0:
                modifiers |= QtCore.Qt.KeyboardModifier.AltModifier
            for view in (actual, reference):
                if frame == 2 and case % 6 == 0:
                    view.connectedEnabled = not view.connectedEnabled
                if frame == 3:
                    view.windows[-1].centerFraction += .01
                delta = p(500 + frame * 2400, -130 + frame * 80)
                position = view.WorldToViewport(view.ViewportToWorld(view.dragStart) + delta)
                view.UpdateGroupDrag(position, modifiers)
            assert Snapshot(actual) == Snapshot(reference), ("group", case, frame, Snapshot(actual), Snapshot(reference))
            assert actual.collisionPassCache is None
            frameCount += 1
    print(f"PASS: 1200 exact travel/fraction/attachment cases and {frameCount} frozen group-drag frames, including copies, handles, blockers, mixed parents and cache refreshes")
    actual.close()
    reference.close()


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
