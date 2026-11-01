"""Regression checks for the six confirmed correctness-audit reproductions."""
import copy
import json
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))

from PySide6 import QtCore, QtWidgets, QtTest
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Window, PocketDoor, BarnDoor, Fireplace, Furnishing, Label, RoomLabel, NorthArrow
from planner_app.project_codec import DecodeProject, EncodeScene
from planner_app.geometry.collisions import SignificantPathOverlap


def CheckDissolve(main):
    v = main.viewport
    p = QtCore.QPointF
    first = Wall(p(), p(4000, 0), 240)
    second = Wall(p(4000, 0), p(4000, 4000), 240)
    blocker = Wall(p(1000, 1000), p(1000, 2500), 240)
    window = Window(first, .4, .6)
    InstallScene(main, [first, second, blocker, window])
    before = EncodeScene(v)
    assert v.OpeningFits(window)
    assert not v.DissolveWalls(p(4000, 0))
    assert EncodeScene(v) == before and not v.undoHistory
    assert window.parentWall is first and v.OpeningFits(window)
    DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)

    # Removing the obstruction allows the same edit and its persisted journal.
    InstallScene(main, [first, second, window])
    assert v.DissolveWalls(p(4000, 0)) and v.OpeningFits(window)
    assert len(v.undoHistory) == 1
    decoded = DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)
    assert len(decoded[5]["history"]["undo"]) == 1
    v.Undo()
    assert window.parentWall is first
    v.Redo()
    assert v.OpeningFits(window)


def CheckPocketSide(main):
    v = main.viewport
    p = QtCore.QPointF
    for kind in (PocketDoor, BarnDoor):
        parent = Wall(p(), p(2000, 0), 240)
        support = Wall(p(2000, 0), p(4000, 0), 240)
        door = kind(parent, .25, 1.25)
        InstallScene(main, [parent, support, door])
        v.SetSelection([(door, None)])
        before = EncodeScene(v)
        assert v.OpeningFits(door)
        assert main.EditDoorProperty("hinge") is False
        assert EncodeScene(v) == before and not v.undoHistory
        assert v.ApplyObjectContextAction([door], "hingeAtSecond") is False
        assert EncodeScene(v) == before and not v.undoHistory

        # The context-menu batch must roll back all members when one fails.
        otherParent = Wall(p(0, 5000), p(4000, 5000), 240)
        otherDoor = kind(otherParent, .25, .75)
        InstallScene(main, [parent, support, otherParent, door, otherDoor])
        before = EncodeScene(v)
        assert v.ApplyObjectContextAction([otherDoor, door], "hingeAtSecond") is False
        assert EncodeScene(v) == before and not v.undoHistory
        v.ApplyObjectContextAction([otherDoor], "hingeAtSecond")
        assert otherDoor.hingeAtSecond and v.OpeningFits(otherDoor)
        v.Undo()
        assert not otherDoor.hingeAtSecond
        v.Redo()
        assert otherDoor.hingeAtSecond


def CheckFireplaceHistory(main):
    v = main.viewport
    p = QtCore.QPointF
    for replay, reopen in ((False, False), (True, False), (True, True)):
        parent = Wall(p(), p(4000, 0), 240)
        fireplace = Fireplace(parent, .25, .75)
        fireplace.depth, fireplace.depthOffset = 400, 50
        InstallScene(main, [parent, fireplace])
        v.unitsMode = "Millimeters"
        v.SetSelection([(parent, None)])
        main.sizeLinkButton.setChecked(False)
        main.EditProperty("width", 600)
        assert (fireplace.depth, fireplace.depthOffset) == (600, 0)
        assert (fireplace.manualDepth, fireplace.manualDepthOffset) == (400, 50)
        v.RestoreOpeningStates(v.CaptureOpeningStates())
        clone = v.CloneOpening(fireplace, parent)
        assert (clone.manualDepth, clone.manualDepthOffset) == (400, 50)
        if reopen:
            data = main.BuildProjectData()
            record = data["scene"]["objects"][1]
            assert (record["manualDepth"], record["manualDepthOffset"]) == (400, 50)
            malformed = copy.deepcopy(data)
            malformed["scene"]["objects"][1]["manualDepth"] = 700
            try:
                DecodeProject(malformed, v.furnishingDefinitions)
            except ValueError:
                pass
            else:
                raise AssertionError("Inconsistent stored fireplace geometry was accepted")
            decoded = DecodeProject(data, v.furnishingDefinitions)
            assert len(decoded[5]["history"]["undo"]) == 1
            main.ApplyProject(decoded, None)
            parent, fireplace = v.walls[0], v.windows[0]
        if replay:
            v.Undo()
            assert (parent.width, fireplace.depth, fireplace.depthOffset) == (240, 400, 50)
            v.Redo()
            assert (fireplace.manualDepth, fireplace.manualDepthOffset) == (400, 50)
        v.SetSelection([(parent, None)])
        main.sizeLinkButton.setChecked(False)
        main.EditProperty("width", 240)
        assert (fireplace.depth, fireplace.depthOffset) == (400, 50)


def CheckReservedClipboard(main):
    v = main.viewport
    p = QtCore.QPointF
    for kind in (PocketDoor, BarnDoor):
        for reverse in (False, True):
            parent = Wall(p(), p(1000, 0), 240)
            support = Wall(p(1000, 0), p(2000, 0), 240)
            if reverse:
                parent.firstVertex, parent.secondVertex = p(parent.secondVertex), p(parent.firstVertex)
            door = kind(parent, -1 if reverse else 0, 1 if reverse else 2, hingeAtSecond = reverse)
            InstallScene(main, [parent, support, door])
            v.SetSelection([(parent, None), (support, None)])
            assert v.OpeningFits(door) and v.CopySelection()
            payload = v.ReadClipboardSelection()
            assert payload is not None
            # A missing or disconnected supporting segment must still reject.
            for displacement in (None, 100):
                invalid = copy.deepcopy(payload)
                if displacement is None:
                    invalid["objects"].pop(1)
                else:
                    for name in ("first", "second"):
                        invalid["objects"][1][name][0] += displacement
                assert v.ReadClipboardSelection(json.dumps(invalid).encode("utf-8")) is None
            InstallScene(main, [])
            assert v.PasteSelection(inPlace = True)
            assert len(v.walls) == 2 and len(v.windows) == 1
            pasted = v.windows[0]
            assert type(pasted) is kind and pasted.length == 2000 and v.OpeningFits(pasted)
            v.Undo()
            assert not v.walls and not v.windows
            v.Redo()
            assert v.OpeningFits(pasted)


def CheckCoordinateHistory(main):
    v = main.viewport
    p = QtCore.QPointF
    # Preserve the former noise/no-op behavior, including redo and dirty state.
    furnishing = Furnishing(v.furnishingDefinitions["null"], p(1e8, 1e8))
    InstallScene(main, [furnishing])
    v.SetSelection([(furnishing, None)])
    v.MoveSpecial(7, 0, 0)
    v.Undo()
    main.MarkProjectClean()
    before = v.CaptureState()
    signals = QtTest.QSignalSpy(v.sceneChanged)
    furnishing.firstVertex += p(1e-7, 0)
    furnishing.secondVertex += p(1e-7, 0)
    v.RecordEdit(before)
    main.RefreshProjectDirty()
    assert not v.undoHistory and len(v.redoHistory) == 1
    assert signals.count() == 0 and not main.projectDirty
    v.MoveSpecial(.5, 0, 0)
    main.RefreshProjectDirty()
    assert len(v.undoHistory) == 1 and not v.redoHistory
    assert signals.count() == 1 and main.projectDirty

    offset = p(1e12 - 2000, 1e12 - 2000)
    objects = [Furnishing(v.furnishingDefinitions["null"], offset), NorthArrow(offset), Label(offset), RoomLabel(offset)]
    for obj in objects:
        InstallScene(main, [obj])
        v.SetSelection([(obj, None)])
        main.MarkProjectClean()
        beforeX = obj.firstVertex.x()
        assert v.MoveSpecial(.5, .5, 0) is None
        assert obj.firstVertex.x() == beforeX + .5 and len(v.undoHistory) == 1
        main.RefreshProjectDirty()
        assert main.projectDirty
        edit = v.undoHistory[-1]
        state = v.CaptureState()
        obj.firstVertex += p(.25, 0)
        try:
            edit.Apply(v.CaptureState(), False, validate = True)
        except ValueError:
            pass
        else:
            raise AssertionError("History accepted a distinct coordinate as its source")
        v.RestoreState(state)
        v.Undo()
        assert obj.firstVertex.x() == beforeX
        v.Redo()
        assert obj.firstVertex.x() == beforeX + .5
        v.Undo()
        assert len(v.redoHistory) == 1
        v.MoveSpecial(.25, .25, 0)
        assert obj.firstVertex.x() == beforeX + .25 and not v.redoHistory
        decoded = DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)
        assert len(decoded[5]["history"]["undo"]) == 1


def CheckFarOriginCollisions(main):
    v = main.viewport
    p = QtCore.QPointF
    for offset in (0, 1e9, 1e12 - 5000):
        first = Wall(p(offset, offset), p(offset + 1000, offset), 240)
        second = Wall(p(offset + 1000, offset), p(offset + 1000, offset + 1000), 240)
        furnishing = Furnishing(v.furnishingDefinitions["null"], p(offset + 1070, offset - 70))
        furnishing.width = 50
        furnishing.secondVertex = furnishing.firstVertex + p(0, 50)
        center = (furnishing.firstVertex + furnishing.secondVertex) / 2
        delta = p(offset + 1070, offset - 70) - center
        furnishing.firstVertex += delta
        furnishing.secondVertex += delta
        InstallScene(main, [first, second, furnishing])
        assert not v.ObjectsOverlap(first, furnishing) and not v.ObjectsOverlap(second, furnishing)
        assert v.JoinedObjectsOverlap(first, furnishing) and v.JoinedObjectsOverlap(second, furnishing)
        assert not v.FurnishingFits(furnishing)
        polygon = [(offset, offset), (offset + 100, offset), (offset + 100, offset + 100), (offset, offset + 100)]
        assert SignificantPathOverlap([polygon], 1)
        assert SignificantPathOverlap([list(reversed(polygon))], 1)
        assert not SignificantPathOverlap([[], polygon[:2]], 1)


def Main():
    with ExampleWindow() as (main, folder):
        try:
            for check in (CheckDissolve, CheckPocketSide, CheckFireplaceHistory, CheckReservedClipboard,
                          CheckCoordinateHistory, CheckFarOriginCollisions):
                check(main)
                print("PASS:", check.__name__)
        finally:
            # Release native clipboard ownership before QApplication teardown.
            QtWidgets.QApplication.clipboard().clear()
            QtWidgets.QApplication.processEvents()


if __name__ == "__main__":
    Main()
