"""Complete gesture, document replacement, dependency and pivot history regressions."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner_app.ui.main_window import MainWindow
from planner_app.models import Arrow, BarnDoor, Furnishing, PocketDoor, Wall
from planner_app.project_codec import DecodeProject, EncodeScene
from planner_app.geometry_recovery import GeometryLoadCancelled


def Reset(main):
    main.FinishProjectInteraction()
    main.ApplyProject(DecodeProject(main.defaultProjectData, main.viewport.furnishingDefinitions), None)
    main.viewport.snapEnabled = False
    main.viewport.connectedVerticesEnabled = False
    main.viewport.connectedObjectsEnabled = False
    main.viewport.unitsMode = "Millimeters"
    main.sessionTimer.stop()
    main.sessionPollTimer.stop()


def RoundTrip(main, path):
    v = main.viewport
    expected = EncodeScene(v)
    counts = len(v.undoHistory), len(v.redoHistory)
    assert main.SaveProject(path)
    assert not main.projectDirty
    assert main.OpenProject(path)
    assert EncodeScene(v) == expected
    assert (len(v.undoHistory), len(v.redoHistory)) == counts, "Save/load discarded valid history"
    assert not main.projectDirty
    return expected


def CheckSelectionDuringDrag(main, folder):
    Reset(main)
    v = main.viewport
    before = v.CaptureState()
    first = Wall(QtCore.QPointF(-1500, 500), QtCore.QPointF(-500, 500))
    second = Wall(QtCore.QPointF(1000, -500), QtCore.QPointF(2000, -500))
    v.walls = [first, second]
    v.SetSelection([(first, None)])
    v.RecordEdit(before)
    assert main.SaveProject(folder / "selection.plan")
    original = EncodeScene(v)
    revision = v.sceneRevision
    history = list(v.undoHistory)
    start = v.WorldToViewport((first.firstVertex + first.secondVertex) / 2).toPoint()
    end = start + QtCore.QPoint(50, 0)
    QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = start)
    move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(end),
        QtCore.QPointF(v.mapToGlobal(end)), QtCore.Qt.MouseButton.NoButton,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(v, move)
    assert first.firstVertex.x() != -1500
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_A, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert v.dragStart is None and len(v.SelectionEntries()) == 2
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Escape)
    QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = end)
    assert EncodeScene(v) == original, "Select All / Escape changed wall geometry"
    assert v.undoHistory == history and v.sceneRevision == revision
    main.RefreshProjectDirty()
    assert not main.projectDirty
    v.Undo()
    assert not v.walls
    v.Redo()
    assert EncodeScene(v) == original
    RoundTrip(main, folder / "selection.plan")


def CheckPropertyHistoryOverlap(main, folder):
    for forward in (False, True):
        Reset(main)
        v = main.viewport
        before = v.CaptureState()
        arrow = Arrow(QtCore.QPointF(0, 0), QtCore.QPointF(1000, 0))
        v.walls = [arrow]
        v.SetSelection([(arrow, None)])
        v.RecordEdit(before)
        main.EditArrowProperty("length", 2000)
        assert arrow.secondVertex.x() == 2000 and len(v.undoHistory) == 2
        if forward:
            v.Undo()
        v.setFocus()
        QtWidgets.QApplication.processEvents()
        slider = main.arrowFields["intensity"]
        position = QtCore.QPoint(slider.width() // 2, slider.height() // 2)
        QtTest.QTest.mousePress(slider, QtCore.Qt.MouseButton.LeftButton, pos = position)
        assert main.propertyDragBefore is not None and arrow.intensity != 1
        modifiers = QtCore.Qt.KeyboardModifier.ControlModifier
        if forward:
            modifiers |= QtCore.Qt.KeyboardModifier.ShiftModifier
        QtTest.QTest.keyClick(slider, QtCore.Qt.Key.Key_Z, modifiers)
        assert main.propertyDragBefore is None and not slider.isSliderDown()
        assert slider.dragOffset is None and arrow.intensity == 1
        assert arrow.secondVertex.x() == (2000 if forward else 1000)
        counts = len(v.undoHistory), len(v.redoHistory)
        QtTest.QTest.mouseRelease(slider, QtCore.Qt.MouseButton.LeftButton, pos = position)
        assert (len(v.undoHistory), len(v.redoHistory)) == counts
        assert arrow.intensity == 1
        expected = RoundTrip(main, folder / "property.plan")
        v.Undo() if forward else v.Redo()
        assert v.walls[0].secondVertex.x() == (1000 if forward else 2000)
        v.Redo() if forward else v.Undo()
        assert EncodeScene(v) == expected


def CheckFailedOpen(main, folder):
    Reset(main)
    v = main.viewport
    before = v.CaptureState()
    parent = Wall(QtCore.QPointF(0, 0), QtCore.QPointF(3000, 0))
    support = Wall(QtCore.QPointF(3000, 0), QtCore.QPointF(6000, 0))
    door = PocketDoor(parent, .6, 1.2)
    v.walls, v.windows = [parent, support], [door]
    v.SetSelection([(support, None)])
    v.RecordEdit(before)
    assert main.SaveProject(folder / "previous.plan")
    # Reproduce a pre-fix session with missing reserved-space support. Such
    # editable scenes must remain recoverable even though strict imports fail.
    before = v.CaptureState()
    v.walls = [parent]
    v.SetSelection([(parent, None)])
    v.RecordEdit(before)
    previous = EncodeScene(v)
    history = list(v.undoHistory), list(v.redoHistory)
    identities = list(v.walls), list(v.windows)
    path = main.projectPath
    malformed = folder / "malformed.plan"
    malformed.write_text("{", encoding = "utf-8")
    valid = folder / "incoming.plan"
    valid.write_text(json.dumps(main.defaultProjectData), encoding = "utf-8")
    messages = []
    with patch.object(main, "ConfirmProjectReplacement", return_value = True), patch.object(main,
            "ShowAppMessage", side_effect = lambda *args, **kwargs: messages.append(args[0])):
        for target in (folder / "missing.plan", malformed):
            assert not main.OpenProject(target)
            assert v.walls[0] is identities[0][0] and v.windows[0] is identities[1][0]
            assert EncodeScene(v) == previous and (v.undoHistory, v.redoHistory) == history
        with patch("planner_app.project_recovery.RecoverProject", side_effect = GeometryLoadCancelled):
            assert not main.OpenProject(valid)
        assert EncodeScene(v) == previous and (v.undoHistory, v.redoHistory) == history
        with patch("planner_app.project_recovery.RecoverProject", return_value = (
                DecodeProject(main.defaultProjectData, v.furnishingDefinitions), ["Fixture repair"])), patch.object(
                main, "BackupProjectForRecovery", side_effect = OSError("Backup unavailable")):
            assert not main.OpenProject(valid)
        assert EncodeScene(v) == previous and (v.undoHistory, v.redoHistory) == history
        apply = main.ApplyProject
        attempts = []

        def FailApply(decoded, target):
            attempts.append(target)
            result = apply(decoded, target)
            if len(attempts) == 1:
                raise RuntimeError("Installation failed after replacing the scene")
            return result

        with patch.object(main, "ApplyProject", side_effect = FailApply):
            assert not main.OpenProject(valid)
    assert "Project Restore Failed" not in messages
    assert main.projectPath == path
    assert v.walls[0] is parent and v.windows[0] is door
    assert EncodeScene(v) == previous and (v.undoHistory, v.redoHistory) == history
    assert v.SelectionEntries() == [(parent, None)]
    main.RefreshProjectDirty()
    assert main.projectDirty
    v.Undo()
    assert len(v.walls) == 2 and v.OpeningFits(door)
    repaired = RoundTrip(main, folder / "restored.plan")
    v.Redo()
    assert EncodeScene(v) == previous
    v.Undo()
    assert EncodeScene(v) == repaired
    with patch.object(main, "ConfirmProjectReplacement", return_value = True):
        assert main.OpenProject(valid)
    assert not v.walls and not v.windows and not v.undoHistory and not v.redoHistory
    assert not main.projectDirty


def CheckReservedDoorDeletion(main, folder):
    for kind in (PocketDoor, BarnDoor):
        Reset(main)
        v = main.viewport
        before = v.CaptureState()
        parent = Wall(QtCore.QPointF(0, 0), QtCore.QPointF(3000, 0))
        support = Wall(QtCore.QPointF(3000, 0), QtCore.QPointF(6000, 0))
        unrelated = Wall(QtCore.QPointF(0, 5000), QtCore.QPointF(3000, 5000))
        door = kind(parent, .6, 1.2)
        v.walls, v.windows = [parent, support, unrelated], [door]
        v.SetSelection([(support, None), (unrelated, None)])
        v.RecordEdit(before)
        assert v.OpeningsValid()
        original = EncodeScene(v)
        history = list(v.undoHistory)
        revision = v.sceneRevision
        assert v.DeleteSelected() is False
        assert EncodeScene(v) == original and v.undoHistory == history and v.sceneRevision == revision
        assert v.SelectionEntries() == [(support, None), (unrelated, None)]
        assert "reserved space" in v.clipboardError
        RoundTrip(main, folder / "reserved.plan")
        parent, support, unrelated = v.walls
        door = v.windows[0]
        v.SetSelection([(unrelated, None)])
        v.DeleteSelected()
        assert len(v.walls) == 2 and v.OpeningsValid()
        v.Undo()
        assert EncodeScene(v) == original
        v.Redo()
        assert len(v.walls) == 2
        # Explicitly selecting the dependent door permits an atomic deletion.
        v.SetSelection([(support, None), (door, None)])
        v.DeleteSelected()
        assert len(v.walls) == 1 and not v.windows
        deleted = RoundTrip(main, folder / "reserved-deleted.plan")
        v.Undo()
        assert len(v.walls) == 2 and len(v.windows) == 1 and v.OpeningsValid()
        v.Redo()
        assert EncodeScene(v) == deleted


def CheckPivotHistory(main, folder):
    Reset(main)
    v = main.viewport
    before = v.CaptureState()
    furnishing = Furnishing(v.furnishingDefinitions["desk"], QtCore.QPointF())
    v.furnishings = [furnishing]
    v.SetSelection([(furnishing, None)])
    v.RecordEdit(before)
    v.furnishingRotationObject = furnishing
    v.rotationPivot = QtCore.QPointF(100, 100)
    original = EncodeScene(v)
    main.EditObjectPosition("x", 1100)
    moved = EncodeScene(v)
    assert v.rotationPivot == QtCore.QPointF(1100, 100)
    v.Undo()
    assert EncodeScene(v) == original and v.rotationPivot == QtCore.QPointF(100, 100)
    v.Redo()
    assert EncodeScene(v) == moved and v.rotationPivot == QtCore.QPointF(1100, 100)
    RoundTrip(main, folder / "pivot.plan")
    v.Undo()
    furnishing = v.furnishings[0]
    assert EncodeScene(v) == original and v.rotationPivot == QtCore.QPointF(100, 100)
    assert v.furnishingRotationObject is furnishing
    assert main.ObjectPositionPivot([furnishing]) == QtCore.QPointF(100, 100)
    first = QtCore.QPointF(furnishing.firstVertex)
    pivot = QtCore.QPointF(v.rotationPivot)
    handle = next(handle for handle in v.FurnishingHandles(furnishing) if handle[0] == "rotate")
    offset = v.ViewportToWorld(handle[3]) - pivot
    end = v.WorldToViewport(pivot + QtCore.QPointF(-offset.y(), offset.x()))
    v.BeginFurnishingHandleDrag(furnishing, handle, handle[3])
    v.UpdateFurnishingHandleDrag(end, QtCore.Qt.KeyboardModifier.NoModifier)
    release = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonRelease, end,
        QtCore.QPointF(v.mapToGlobal(end.toPoint())), QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
    v.mouseReleaseEvent(release)
    offset = first - pivot
    expectedFirst = pivot + QtCore.QPointF(-offset.y(), offset.x())
    assert QtCore.QLineF(furnishing.firstVertex, expectedFirst).length() < 1e-6
    v.Undo()
    assert EncodeScene(v) == original and v.rotationPivot == pivot
    # Return to the original move's redo branch after testing the new rotation.
    v.redoHistory.clear()
    main.EditObjectPosition("x", 1100)
    v.Undo()
    RoundTrip(main, folder / "pivot-undone.plan")
    v.Redo()
    furnishing = v.furnishings[0]
    assert EncodeScene(v) == moved and v.rotationPivot == QtCore.QPointF(1100, 100)
    # Continue editing after replay: property movement must use the restored pivot.
    main.EditObjectPosition("x", 1200)
    assert v.rotationPivot == QtCore.QPointF(1200, 100) and not v.redoHistory
    v.Undo()
    assert EncodeScene(v) == moved and v.rotationPivot == QtCore.QPointF(1100, 100)
    # Deletion must not retain a pivot owner that no longer belongs to the scene.
    v.DeleteSelected()
    assert not v.furnishings
    assert v.rotationPivot is None and v.furnishingRotationObject is None
    RoundTrip(main, folder / "pivot-deleted.plan")
    v.Undo()
    assert v.furnishingRotationObject is v.furnishings[0]
    assert v.rotationPivot == QtCore.QPointF(1100, 100)
    # Malformed optional editor metadata invalidates only the journal.
    data = copy.deepcopy(main.BuildProjectData())
    edited = next(edit for edit in data["history"]["undo"] if "editor" in edit)
    edited["editor"][0]["pivot"] = [float("inf"), 0]
    loaded = DecodeProject(data, v.furnishingDefinitions)
    assert not loaded[5]["history"]["undo"] and len(loaded[2]) == 1
    # Shared selection pivots must retain every member, including across disk.
    Reset(main)
    first = Furnishing(v.furnishingDefinitions["desk"], QtCore.QPointF())
    second = Furnishing(v.furnishingDefinitions["desk"], QtCore.QPointF(2500, 1500))
    before = v.CaptureState()
    v.furnishings = [first, second]
    v.SetSelection([(first, None), (second, None)])
    v.RecordEdit(before)
    v.furnishingRotationObject = second
    v.rotationPivot = QtCore.QPointF(100, 100)
    original = EncodeScene(v)
    main.EditObjectPosition("y", 600)
    moved = RoundTrip(main, folder / "group-pivot.plan")
    v.Undo()
    assert EncodeScene(v) == original and v.rotationPivot == QtCore.QPointF(100, 100)
    assert len(v.SelectionEntries()) == 2 and v.furnishingRotationObject is v.furnishings[1]
    v.Redo()
    assert EncodeScene(v) == moved and v.rotationPivot == QtCore.QPointF(100, 600)


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        CheckSelectionDuringDrag(main, folder)
        CheckPropertyHistoryOverlap(main, folder)
        CheckFailedOpen(main, folder)
        CheckReservedDoorDeletion(main, folder)
        CheckPivotHistory(main, folder)
    main.close()
    print("PASS: Select All / drag cancellation, opacity-drag undo/redo, failed/cancelled/partial document loads, reserved-door deletion, pivot replay and saved journals")


if __name__ == "__main__":
    Main()
