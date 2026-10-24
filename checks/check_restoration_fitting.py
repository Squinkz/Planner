"""Frozen restoration, fitting, validation and repeated group-preview parity."""
import math
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))


def Main():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtWidgets
    from planner_app.models import (Wall, Door, Window, Fireplace, Furnishing, Stair, SlidingDoor,
        PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, OpenDoorway)
    from planner_app.viewport.widget import DrawingViewport
    from fixtures.qt_restoration_fitting_reference_20261016 import ReferenceRestorationFitting

    class ReferenceViewport(DrawingViewport):
        UpdateGroupDrag = ReferenceRestorationFitting.UpdateGroupDrag
        RestoreOpeningStates = ReferenceRestorationFitting.RestoreOpeningStates
        RestoreFurnishingStates = ReferenceRestorationFitting.RestoreFurnishingStates
        RestoreLabelStates = ReferenceRestorationFitting.RestoreLabelStates
        FitWallOpenings = ReferenceRestorationFitting.FitWallOpenings
        MinimumOpeningLength = ReferenceRestorationFitting.MinimumOpeningLength
        OpeningsValid = ReferenceRestorationFitting.OpeningsValid

    app = QtWidgets.QApplication([])
    p = QtCore.QPointF
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
    print(f"PASS: {frameCount} frozen group-drag frames, including copies, handles, blockers, mixed parents and cache refreshes")
    for case in range(240):
        for view in (actual, reference):
            Setup(view, case)
            view.CancelInteraction()
            view.connectedEnabled = bool(case % 2)
            view.connectedObjectsEnabled = bool(case % 3)
            if case % 4 == 0:
                view.windows.reverse()
            if case % 11 == 0:
                view.windows.append(view.windows[0])
            view.interactionBefore = view.CaptureState()
            wall = view.walls[0]
            if case % 5 == 0:
                wall.secondVertex = wall.firstVertex + p(20, 0)
            elif case % 5 == 1:
                wall.secondVertex += p(340, 210)
            elif case % 5 == 2:
                wall.firstVertex += p(-340, 210)
            elif case % 5 == 3:
                wall.firstVertex += p(120, -60)
                wall.secondVertex += p(120, -60)
            if case % 7 == 0:
                view.windows[-1].parentWall = view.walls[1]
        results = [view.FitWallOpenings(view.interactionBefore, validateScene = False)
                   for view in (actual, reference)]
        assert results[0] == results[1], ("fit-result", case)
        assert Snapshot(actual) == Snapshot(reference), ("fit-state", case)
        results = [view.OpeningsValid(validateFurnishings = False, before = view.interactionBefore if case % 2 else None)
                   for view in (actual, reference)]
        assert results[0] == results[1], ("valid", case)
    # Restore tiny coordinate changes exactly; Qt point equality can consider
    # these equal. Retain list ordering and fireplace setter normalization.
    from planner_app.models import Label
    for view in (actual, reference):
        view.CancelInteraction()
        view.labels = [Label(p(1e8, 1e8), "Restore")]
        saved = view.CaptureState()
        view.labels[0].firstVertex.setX(view.labels[0].firstVertex.x() + 1e-7)
        view.furnishings[0].secondVertex.setY(view.furnishings[0].secondVertex.y() + 1e-7)
        view.RestoreLabelStates(saved[8])
        view.RestoreFurnishingStates(saved[5])
        view.RestoreOpeningStates(saved[3])
        assert view.labels[0].firstVertex.x() == saved[8][0][1].x()
        assert view.furnishings[0].secondVertex.y() == saved[5][0][2].y()
        # A repeated unchanged restore must still rebuild requested lists.
        view.RestoreLabelStates(saved[8])
        view.RestoreFurnishingStates(saved[5])
        assert len(view.labels) == len(saved[8]) and len(view.furnishings) == len(saved[5])
    print("PASS: 240 frozen fitting/validation cases and exact coordinate/list restoration")
    def RestoredValues(view):
        objects = view.walls + view.windows + view.furnishings + view.labels
        identities = {id(obj): index for index, obj in enumerate(objects)}
        def Convert(value):
            if isinstance(value, QtCore.QPointF):
                return value.x(), value.y()
            if isinstance(value, (list, tuple)):
                return tuple(Convert(item) for item in value)
            if id(value) in identities:
                return ("object", identities[id(value)])
            return value
        return Convert(view.CaptureState()), [(obj.manualDepth, obj.manualDepthOffset, obj.material)
            for obj in view.windows if isinstance(obj, Fireplace)]

    for case in range(20):
        for view in (actual, reference):
            view.CancelInteraction()
            walls = [Wall(p(0, 0), p(20000, 0), 240), Wall(p(0, 3000), p(20000, 3000), 900)]
            view.walls = walls
            view.windows = [kind(walls[0], .03 + i * .08, .07 + i * .08) for i, kind in enumerate(classes)]
            view.furnishings = [Furnishing({"key": "restore", "name": "Restore", "width": 500, "length": 600})]
            view.labels = [Label(p(1e8, 1e8), "Restore")]
            view.SetSelection([])
            saved = view.CaptureState()
            for opening in view.windows:
                opening.parentWall = walls[1]
                opening.centerFraction += .01
                opening.length += 10
                opening.measurementFlipped = opening.measurementHidden = True
                if hasattr(opening, "hingeAtSecond"):
                    opening.hingeAtSecond = not opening.hingeAtSecond
                if hasattr(opening, "swingsOutwards"):
                    opening.swingsOutwards = not opening.swingsOutwards
                if isinstance(opening, SlidingDoor):
                    opening.panelsFlipped = not opening.panelsFlipped
                if isinstance(opening, SilledWindow):
                    opening.sillDepth += 12
                if isinstance(opening, Fireplace):
                    opening.depth, opening.depthOffset, opening.material = 1400, 100, "Changed"
            view.furnishings[0].behindCounters = view.furnishings[0].measurementHidden = True
            view.furnishings[0].width += 10
            view.labels[0].text, view.labels[0].intensity = "Changed", .2
            for obj in view.furnishings + view.labels:
                obj.firstVertex.setX(obj.firstVertex.x() + 1e-7)
            view.RestoreOpeningStates(saved[3])
            view.RestoreFurnishingStates(saved[5], restoreList = bool(case % 2))
            view.RestoreLabelStates(saved[8], restoreList = bool(case % 2))
            # Old short opening records retain the established false defaults.
            view.RestoreOpeningStates([state[:7] for state in saved[3]])
            # Repeated restoration and hidden fireplace normalization also agree.
            view.windows[-1].manualDepthOffset = 1e6
            view.RestoreOpeningStates(saved[3])
            view.RestoreOpeningStates(saved[3])
        assert RestoredValues(actual) == RestoredValues(reference), ("restore-fields", case)
    from planner_app.viewport.scene import SnapshotPointMatches
    assert SnapshotPointMatches(p(-0.0, 0.0), -0.0, 0.0)
    assert not SnapshotPointMatches(p(0.0, 0.0), -0.0, 0.0)
    for view in (actual, reference):
        view.CancelInteraction()
        view.walls = [Wall(p(-0.0, -0.0), p(8000, -0.0), 240), Wall(p(0, 3000), p(8000, 3000), 240)]
        view.windows = []
        view.SetSelection([(view.walls[1], None)])
        view.interactionBefore = view.CaptureState()
        view.dragStart, view.isDragging = p(100, 100), True
        view.StartGroupDrag()
        view.walls[0].firstVertex = p(0.0, 0.0)
        view.walls[0].secondVertex = p(8000, 0.0)
        view.UpdateGroupDrag(p(130, 100), QtCore.Qt.KeyboardModifier.NoModifier)
        assert math.copysign(1, view.walls[0].firstVertex.x()) == -1
        assert math.copysign(1, view.walls[0].secondVertex.y()) == -1
    print("PASS: all opening types, changed parents/flags/materials, short records and fireplace stored-value normalization")
    actual.close()
    reference.close()


if __name__ == "__main__":
    Main()
