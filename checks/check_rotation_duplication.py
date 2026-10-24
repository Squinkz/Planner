"""Shift rotation copies, temporary pivots, modifier toggles and rollback."""
import math
import os
import sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Pillar, Wall
from furnishings import Furnishing


def Mouse(viewport, eventType, position, modifiers = QtCore.Qt.KeyboardModifier.NoModifier):
    left = QtCore.Qt.MouseButton.LeftButton
    button = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseMove else left
    buttons = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseButtonRelease else left
    event = QtGui.QMouseEvent(eventType, position, QtCore.QPointF(viewport.mapToGlobal(position.toPoint())),
                             button, buttons, modifiers)
    QtWidgets.QApplication.sendEvent(viewport, event)


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.snapEnabled = False
    v.zoom = .3
    v.walls, v.windows, v.labels, v.furnishings = [], [], [], []
    point = QtCore.QPointF
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    press, move, release = (QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseMove,
                            QtCore.QEvent.Type.MouseButtonRelease)
    source = Furnishing(v.furnishingDefinitions["desk"])
    source.width = 400
    source.firstVertex, source.secondVertex = point(0, -100), point(0, 100)
    v.furnishings = [source]
    v.SetSelection([(source, None)])
    v.furnishingRotationObject = source
    pivot = point(-800, 0)
    v.rotationPivot = point(pivot)
    start = next(handle[3] for handle in v.FurnishingHandles(source) if handle[0] == "rotate")
    offset = v.ViewportToWorld(start) - pivot
    end = v.WorldToViewport(pivot + point(-offset.y(), offset.x()))
    original = (point(source.firstVertex), point(source.secondVertex))
    Mouse(v, press, start, shift)
    Mouse(v, move, end, shift)
    assert len(v.furnishings) == 2
    duplicate = v.selectedWall
    assert duplicate is not source and source.firstVertex == original[0] and source.secondVertex == original[1]
    assert math.isclose(duplicate.angle, 90, abs_tol = 1e-6) and v.rotationPivot == pivot
    # Releasing Shift transfers the gesture back; pressing it again creates one copy.
    Mouse(v, move, end)
    assert v.furnishings == [source] and math.isclose(source.angle, 90, abs_tol = 1e-6)
    Mouse(v, move, end, shift)
    assert len(v.furnishings) == 2 and source.firstVertex == original[0]
    duplicate = v.selectedWall
    Mouse(v, release, end, shift)
    assert v.furnishingRotationObject is duplicate and v.rotationPivot == pivot
    assert v.SelectionEntries() == [(duplicate, None)] and len(v.undoHistory) == 1
    # The next rotation uses the retained pivot, with no Shift required.
    start = next(handle[3] for handle in v.FurnishingHandles(duplicate) if handle[0] == "rotate")
    offset = v.ViewportToWorld(start) - pivot
    end = v.WorldToViewport(pivot + point(-offset.y(), offset.x()))
    Mouse(v, press, start)
    Mouse(v, move, end)
    Mouse(v, release, end)
    assert math.isclose(duplicate.angle, 180, abs_tol = 1e-6) and v.rotationPivot == pivot
    v.Undo()
    assert math.isclose(duplicate.angle, 90, abs_tol = 1e-6)
    v.Undo()
    assert v.furnishings == [source] and source.firstVertex == original[0]
    v.Redo()
    assert len(v.furnishings) == 2
    v.SetSelection([])
    assert v.rotationPivot is None

    # Group rotation copies all selected members, retains grouping and cancels cleanly.
    v.furnishings = [source]
    other = source.Clone()
    other.firstVertex += point(500, 0)
    other.secondVertex += point(500, 0)
    v.furnishings.append(other)
    v.objectGroups = [(source, other)]
    v.SetSelection([(source, None)])
    v.furnishingRotationObject = source
    v.rotationPivot = point(-1000, 0)
    box = v.FurnishingSelectionBox()
    handle = next(handle for handle in v.FurnishingHandles(box) if handle[0] == "rotate")
    start = handle[3]
    offset = v.ViewportToWorld(start) - v.rotationPivot
    end = v.WorldToViewport(v.rotationPivot + point(-offset.y(), offset.x()))
    v.BeginFurnishingHandleDrag(box, handle, start)
    v.UpdateFurnishingHandleDrag(end, shift)
    assert len(v.furnishings) == 4 and len(v.objectGroups) == 2
    assert all(math.isclose(obj.angle, 90, abs_tol = 1e-6) for obj, index in v.SelectionEntries())
    v.CancelInteraction()
    assert v.furnishings == [source, other] and v.objectGroups == [(source, other)]
    assert v.rotationPivot == point(-1000, 0)
    assert {id(obj) for obj, index in v.SelectionEntries()} == {id(source), id(other)}
    v.BeginFurnishingHandleDrag(box, handle, start)
    v.UpdateFurnishingHandleDrag(end, shift)
    Mouse(v, release, end, shift)
    assert len(v.furnishings) == 4 and len(v.objectGroups) == 2
    assert v.rotationPivot == point(-1000, 0)
    assert v.furnishingRotationObject in [obj for obj, index in v.SelectionEntries()]
    v.Undo()
    assert v.furnishings == [source, other] and v.objectGroups == [(source, other)]

    # Architectural rectangular objects use the same rotation gesture and cleanup.
    v.objectGroups, v.furnishings = [], []
    pillar = Pillar(point(0, -100), point(0, 100), 200)
    v.walls = [pillar]
    v.SetSelection([(pillar, None)])
    v.furnishingRotationObject = pillar
    v.rotationPivot = point(-800, 0)
    handle = next(handle for handle in v.FurnishingHandles(pillar) if handle[0] == "rotate")
    start = handle[3]
    offset = v.ViewportToWorld(start) - v.rotationPivot
    end = v.WorldToViewport(v.rotationPivot + point(-offset.y(), offset.x()))
    v.BeginFurnishingHandleDrag(pillar, handle, start)
    v.UpdateFurnishingHandleDrag(end, shift)
    assert len(v.walls) == 2 and v.selectedWall is not pillar
    v.CancelInteraction()
    assert v.walls == [pillar] and v.selectedWall is pillar and v.rotationPivot == point(-800, 0)

    # Copies that hit a wall are rejected without changing the original or losing its pivot.
    v.objectGroups = []
    v.furnishings = [source]
    v.walls = [Wall(point(-1000, 150), point(1000, 150), 50)]
    v.SetSelection([(source, None)])
    v.furnishingRotationObject = source
    v.rotationPivot = point()
    handle = next(handle for handle in v.FurnishingHandles(source) if handle[0] == "rotate")
    start = handle[3]
    offset = v.ViewportToWorld(start)
    end = v.WorldToViewport(point(-offset.y(), offset.x()))
    v.BeginFurnishingHandleDrag(source, handle, start)
    v.UpdateFurnishingHandleDrag(end, shift)
    Mouse(v, release, end, shift)
    assert v.furnishings == [source] and source.firstVertex == original[0]
    assert v.selectedWall is source and v.rotationPivot == point()
    main.close()
    print("PASS: Shift rotation duplicates, preserves pivot until deselection, toggles live, and rolls back groups/collisions.")


if __name__ == "__main__":
    Main()
