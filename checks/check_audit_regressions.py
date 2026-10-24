"""Semantic regressions for the October audit: persistence, topology and editing."""
import copy
import math
import os
import sys
import warnings
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner_app.models import Wall, Stair, Counter, Furnishing, Window, OpenDoorway, Label
from planner_app.viewport.widget import DrawingViewport
from planner_app.project_codec import EncodeScene, DecodeProject
from planner_app.ui.main_window import MainWindow
from planner_app.graphics.symbols import DrawStairSymbol
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    v = window.viewport
    p = QtCore.QPointF
    v.snapEnabled = False
    v.connectedEnabled = False

    # Nearly collinear unequal flights retain their runs.
    first = Stair(p(), p(3000, 0), 1000)
    second = Stair(p(), p(math.cos(math.radians(179)) * 3000, math.sin(math.radians(179)) * 3000), 600)
    v.walls = [first, second]
    v.EnsureObjectIds()
    assert first.LandingTrims(v.walls) == second.LandingTrims(v.walls) == (0, 0)
    beforeCount = first.stepCount
    v.hiddenObjects, v.hiddenObjectIds = [second], {id(second)}
    v.grab()
    assert first.stepCount == beforeCount and first.sceneStairs == [first, second]
    v.hiddenObjects, v.hiddenObjectIds = [], set()

    # A new landing normalizes an explicit count as part of the topology edit.
    first = Stair(p(-3000, 0), p())
    first.autosize, first.manualStepCount = False, 1
    v.walls = [first]
    v.EnsureObjectIds()
    before = v.CaptureState()
    second = Stair(p(), p(0, 3000))
    v.walls.append(second)
    v.RecordEdit(before)
    assert first.manualStepCount == first.stepCount == 2
    v.Undo()
    assert first.manualStepCount == first.stepCount == 1
    v.Redo()
    assert first.manualStepCount == 2

    # Collision includes the corner miter, not merely centerline rectangles.
    v.walls = [Wall(p(), p(2000, 0), 1000), Wall(p(), p(0, 2000), 1000)]
    item = Furnishing(v.furnishingDefinitions["null"], p(-300, -300))
    item.width = 100
    item.firstVertex, item.secondVertex = p(-300, -350), p(-300, -250)
    assert not v.FurnishingFits(item)
    assert not v.CounterFits(Counter(p(-350, -300), p(-250, -300), 100))
    assert not v.StairFits(Stair(p(-350, -300), p(-250, -300), 100))

    # Surviving endpoint properties and collision checks during dissolution.
    older = Wall(p(-1000, 1000), p(), 120, .2, .3)
    newer = Wall(p(), p(1000, 1000), 120, .3, .8)
    older.objectId, newer.objectId = 1, 2
    blocker = Counter(p(-300, 1000), p(300, 1000), 300)
    v.walls, v.windows, v.furnishings = [older, newer, blocker], [], []
    assert not v.DissolveWalls(p()) and len(v.walls) == 3
    v.walls = [older, newer]
    assert v.DissolveWalls(p())
    assert (v.walls[0].firstMiter, v.walls[0].secondMiter) == (.2, .8)

    # Hidden parents cannot receive openings or provide snap targets.
    parent = Wall(p(-2000, 0), p(2000, 0))
    v.walls, v.windows = [parent], []
    v.hiddenObjects, v.hiddenObjectIds = [parent], {id(parent)}
    assert v.FindWindowPlacement(v.WorldToViewport(p()), 600) is None
    assert not list(v.SnapVertices()) and not v.StairSnapTargets()
    v.hiddenObjects, v.hiddenObjectIds = [], set()
    crossing = Wall(p(0, -1500), p(0, 1500))
    v.walls.append(crossing)
    assert not v.OpeningFits(OpenDoorway(parent, .4, .6))

    # Detached decoding rejects malformed bounds before changing live objects.
    v.walls, v.windows, v.furnishings, v.labels = [parent], [Window(parent, .3, .5)], [], []
    v.EnsureObjectIds()
    window.RefreshProjectDirty()
    data = window.BuildProjectData()
    for field, value in (("length", 5000), ("center", .01)):
        invalid = copy.deepcopy(data)
        invalid["scene"]["objects"][1][field] = value
        try:
            DecodeProject(invalid, v.furnishingDefinitions)
            raise AssertionError("Invalid opening was accepted")
        except ValueError:
            pass
    invalid = copy.deepcopy(data)
    invalid["scene"]["objects"][0]["firstMiter"] = 1.1
    try:
        DecodeProject(invalid, v.furnishingDefinitions)
        raise AssertionError("Invalid miter was accepted")
    except ValueError:
        pass
    invalid = copy.deepcopy(data)
    invalid["settings"]["buildSettings"]["openingSizes"] = []
    try:
        DecodeProject(invalid, v.furnishingDefinitions)
        raise AssertionError("Invalid settings were accepted")
    except ValueError:
        pass
    v.windows = []
    missing = Furnishing(v.furnishingDefinitions["null"], p(0, 1500))
    missing.definitionKey = "temporarily-missing"
    v.furnishings = [missing]
    v.EnsureObjectIds()
    window.RefreshProjectDirty()
    decoded = DecodeProject(window.BuildProjectData(), v.furnishingDefinitions)
    assert decoded[2][0].definitionKey == "temporarily-missing"
    v.furnishings = decoded[2]
    assert EncodeScene(v)["objects"][-1]["definition"] == "temporarily-missing"
    assert missing.Clone().definitionKey == "temporarily-missing"

    # Clipboard groups get new members, and incomplete groups are omitted.
    v.walls, v.windows, v.furnishings = [], [], []
    a = Furnishing(v.furnishingDefinitions["desk"], p(-1000, 0))
    b = Furnishing(v.furnishingDefinitions["desk"], p(1000, 0))
    v.furnishings, v.objectGroups = [a, b], [(a, b)]
    v.SetSelection([(a, None), (b, None)])
    assert v.CopySelection() and v.PasteSelection(v.WorldToViewport(p(0, -2000)))
    selected = {id(obj) for obj, index in v.SelectionEntries()}
    assert len(v.objectGroups) == 2 and selected == {id(obj) for obj in v.objectGroups[-1]}
    assert not selected.intersection((id(a), id(b)))

    # Shift duplication retains independent groups; cancellation restores them.
    v.furnishings, v.objectGroups = [a, b], [(a, b)]
    v.SetSelection([(a, None), (b, None)])
    start = v.WorldToViewport((a.firstVertex + a.secondVertex) / 2).toPoint()
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    Drag(v, start, start + QtCore.QPoint(0, -100), shift)
    assert len(v.furnishings) == 4 and len(v.objectGroups) == 2
    copiedIds = {id(obj) for obj, index in v.SelectionEntries()}
    assert copiedIds == {id(obj) for obj in v.objectGroups[-1]}
    v.Undo()
    assert len(v.furnishings) == 2 and v.objectGroups == [(a, b)]
    v.SetSelection([(a, None), (b, None)])
    QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, shift, start)
    v.UpdateInteraction(QtCore.QPointF(start + QtCore.QPoint(0, -100)), shift)
    assert v.dragCopies
    v.CancelInteraction()
    QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, shift, start)
    assert len(v.furnishings) == 2 and v.objectGroups == [(a, b)]

    # Fixed-parent openings use the same allowable translation at wall ends.
    a = Wall(p(-1500, 500), p(1500, 500))
    b = Wall(p(-1500, -500), p(1500, -500))
    openings = [Window(a, .65, .95), Window(b, .2, .5)]
    v.walls, v.windows, v.furnishings, v.objectGroups = [a, b], openings, [], []
    v.SetSelection([(obj, None) for obj in openings])
    originals = [p(obj.firstVertex) for obj in openings]
    start = v.WorldToViewport((openings[0].firstVertex + openings[0].secondVertex) / 2).toPoint()
    Drag(v, start, start + QtCore.QPoint(100, 0))
    offsets = [obj.firstVertex.x() - original.x() for obj, original in zip(openings, originals)]
    assert abs(offsets[0] - 150) < .001 and abs(offsets[1] - offsets[0]) < .001

    # Dense/huge stairs generate only viewport-bounded drawing work.
    image = QtGui.QImage(800, 600, QtGui.QImage.Format.Format_ARGB32)
    painter = QtGui.QPainter(image)
    DrawStairSymbol(painter, p(-1e10, 100), p(1e10, 100), 100, 4000000000,
                    clipRect = QtCore.QRectF(0, 0, 800, 600))
    painter.end()

    # A local editor undo must never consume drawing history.
    label = Label(text = "before")
    v.walls, v.windows, v.labels = [], [], [label]
    v.SetSelection([(label, None)])
    window.RefreshProperties()
    editor = window.labelTextField
    editor.setFocus()
    editor.moveCursor(QtGui.QTextCursor.MoveOperation.End)
    QtTest.QTest.keyClicks(editor, " after")
    historyLength = len(v.undoHistory)
    QtTest.QTest.keyClick(editor, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert editor.toPlainText() == "before" and len(v.undoHistory) == historyLength

    # Consecutive label keystrokes coalesce; ordinary edits retain the budget.
    v.undoHistory.clear()
    v.historyCoalesceKey = None
    editor.moveCursor(QtGui.QTextCursor.MoveOperation.End)
    QtTest.QTest.keyClicks(editor, "12345")
    assert len(v.undoHistory) == 1
    v.historyLimit = 2
    for width in (120, 130, 140):
        before = v.CaptureState()
        label.width = width
        v.RecordEdit(before)
    assert len(v.undoHistory) == 2

    # Failed final checkpoints leave the window, polling and executor usable.
    closeEvent = QtGui.QCloseEvent()
    window.sessionSignature = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with patch("planner_app.ui.session.WriteSessionFile", return_value = "Disk full"), patch.object(window, "ShowAppMessage"):
            window.closeEvent(closeEvent)
    assert not closeEvent.isAccepted() and window.sessionPollTimer.isActive()
    assert window.WriteSession(wait = True)
    QtWidgets.QApplication.clipboard().clear()
    app.processEvents()
    window.close()
    print("PASS: audit topology, collision, persistence, clipboard, group, rendering, undo and recovery regressions")


if __name__ == "__main__":
    Main()
