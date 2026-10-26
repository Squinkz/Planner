"""Rendered hover targets, cursors and actual left presses share picking priority."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Furnishing, Label, Arrow, MeasurementGuide, BoundaryLine, AngleGuide


def CheckTarget(viewport, position, expectedObject, expectedIndex, expectedHandle = None):
    viewport.hoverPosition = position
    QtTest.QTest.mouseMove(viewport, position.toPoint())
    viewport.hoverPosition = position
    overlays = []
    draw = type(viewport).DrawLabels

    def DrawLabels(v, *args, **kwargs):
        if kwargs.get("drawText") is False:
            overlays.append(args[3])
        return draw(v, *args, **kwargs)

    with patch.object(type(viewport), "DrawLabels", DrawLabels):
        viewport.grab()
    assert overlays and overlays[-1] is expectedObject, (overlays, expectedObject)
    actual = viewport.SelectionTarget(position)
    assert actual[0] is expectedObject and actual[1] == expectedIndex
    assert actual[2] == expectedHandle
    if expectedHandle is None:
        assert viewport.cursor().shape() == QtCore.Qt.CursorShape.SizeAllCursor
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton,
                           QtCore.Qt.KeyboardModifier.NoModifier, position.toPoint())
    if expectedHandle is None:
        assert viewport.furnishingHandleDrag is None
        assert viewport.selectedWall is expectedObject and viewport.selectedVertex == expectedIndex
    else:
        state = viewport.furnishingHandleDrag
        assert state is not None and state["handle"] == expectedHandle
        members = getattr(expectedObject, "selectionMembers", ())
        assert state["sourceObject"] is expectedObject or members and tuple(obj for obj, *unused in state["members"]) == members
    viewport.CancelInteraction()
    QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.LeftButton,
                             QtCore.Qt.KeyboardModifier.NoModifier, position.toPoint())


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.snapEnabled = v.showMeasurements = v.showTips = False
        desk = Furnishing(v.furnishingDefinitions["desk"])
        desk.firstVertex, desk.secondVertex, desk.width = p(0, -300), p(0, 300), 600
        InstallScene(main, [desk])
        v.SetSelection([(desk, None)])
        # A selected resize handle can overlap both an endpoint and a label.
        # Neither underlying target should acquire the active hover highlight.
        handle = next(handle for handle in v.FurnishingHandles(desk) if handle[:3] == ("resize", "width", 1))
        anchor = v.ViewportToWorld(handle[3])
        arrow = Arrow(anchor, anchor + p(0, 1200))
        label = Label(anchor, "Under handle")
        shift = anchor - (label.firstVertex + label.secondVertex) / 2
        label.firstVertex += shift
        label.secondVertex += shift
        for underlying in (arrow, label):
            InstallScene(main, [desk, underlying])
            v.SetSelection([(desk, None)])
            assert v.HitTest(handle[3])[0] is underlying
            CheckTarget(v, handle[3], desk, None, handle)
            v.ShowObjectContextMenu(handle[3], v.mapToGlobal(handle[3].toPoint()))
            assert v.SelectionEntries() == [(desk, None)]
            v.objectContextMenu.hide()
        # Rotation artwork and pivot use the same priority as resize handles.
        for mode in ("rotate", "pivot"):
            InstallScene(main, [desk])
            v.SetSelection([(desk, None)])
            v.furnishingRotationObject = desk
            handle = next(handle for handle in v.FurnishingHandles(desk) if handle[0] == mode)
            anchor = v.ViewportToWorld(handle[3])
            arrow = Arrow(anchor, anchor + p(0, 1200))
            v.walls = [arrow]
            assert v.HitTest(handle[3]) == (arrow, 0)
            CheckTarget(v, handle[3], desk, None, handle)
        # Drawing order and hit order agree for coincident furnishing handles.
        front = Furnishing(v.furnishingDefinitions["desk"])
        front.firstVertex, front.secondVertex, front.width = p(desk.firstVertex), p(desk.secondVertex), desk.width
        InstallScene(main, [desk, front])
        v.SetSelection([(desk, None)])
        handle = next(handle for handle in v.FurnishingHandles(desk) if handle[:3] == ("resize", "width", 1))
        v.hoverPosition = handle[3]
        assert v.VisibleFurnishingHandles()[-1][0] is desk
        v.hoverPosition = p(-10000, -10000)
        assert v.SelectionTarget(handle[3])[0] is desk, "A press must not depend on a preceding mouse move"
        CheckTarget(v, handle[3], desk, None, handle)
        # The shared selection box is also the visible and clickable target.
        front.firstVertex += p(1600, 0)
        front.secondVertex += p(1600, 0)
        InstallScene(main, [desk, front])
        v.SetSelection([(desk, None), (front, None)])
        box = v.FurnishingSelectionBox()
        handle = next(handle for handle in v.FurnishingHandles(box) if handle[:3] == ("resize", "width", 1))
        CheckTarget(v, handle[3], box, None, handle)
        v.ShowObjectContextMenu(handle[3], v.mapToGlobal(handle[3].toPoint()))
        assert {id(obj) for obj, index in v.SelectionEntries()} == {id(desk), id(front)}
        v.objectContextMenu.hide()
        # A guide label under a pivot must not consume the pivot double-click.
        guide = MeasurementGuide(p(-1000, 0), p(1000, 0))
        guide.textOffset = p(0, 1500)
        InstallScene(main, [desk, guide])
        v.SetSelection([(desk, None)])
        v.furnishingRotationObject = desk
        position = v.MeasurementLabelLayout(guide)[0]
        v.rotationPivot = v.ViewportToWorld(position)
        assert v.HitTest(position) == (guide, 3)
        QtTest.QTest.mouseDClick(v, QtCore.Qt.MouseButton.LeftButton,
                                QtCore.Qt.KeyboardModifier.NoModifier, position.toPoint())
        assert v.rotationPivot is None and guide.textOffset == p(0, 1500)
        # A handle outside the object's body is not empty canvas on double-click.
        v.furnishingRotationObject = None
        handle = next(handle for handle in v.FurnishingHandles(desk) if handle[:3] == ("resize", "width", 1))
        before = v.zoom, p(v.panOffset)
        QtTest.QTest.mouseDClick(v, QtCore.Qt.MouseButton.LeftButton,
                                QtCore.Qt.KeyboardModifier.NoModifier, handle[3].toPoint())
        assert v.furnishingHandleDrag is not None and (v.zoom, v.panOffset) == before
        v.CancelInteraction()
        # Whole-object multi-selection advertises a group move at endpoints.
        first = Wall(p(-900, 0), p(0, 0), 120)
        second = Wall(p(0, 0), p(900, 0), 120)
        InstallScene(main, [first, second])
        v.SetSelection([(first, None), (second, None)])
        CheckTarget(v, v.WorldToViewport(first.firstVertex), first, None)
        # Explicit vertex selections keep their endpoint behavior in a group.
        v.SetSelection([(first, 1), (second, 0)])
        target, index = v.HitTest(v.WorldToViewport(p()))
        CheckTarget(v, v.WorldToViewport(p()), target, index)
        # Body picking, dimension labels and angle labels/vertices are unchanged.
        label = Label(p(), "Label")
        InstallScene(main, [label])
        CheckTarget(v, v.WorldToViewport((label.firstVertex + label.secondVertex) / 2), label, None)
        guide = MeasurementGuide(p(-1000, 0), p(1000, 0))
        InstallScene(main, [guide])
        position = v.MeasurementLabelLayout(guide)[0]
        CheckTarget(v, position, guide, 3)
        boundary = BoundaryLine(p(-1000, 0), p(1000, 0))
        InstallScene(main, [boundary])
        v.SetSelection([(boundary, None)])
        CheckTarget(v, v.MeasurementLabelLayout(boundary)[0], boundary, None)
        angle = AngleGuide(p(-1000, 0), p(0, 1000), middleVertex = p())
        InstallScene(main, [angle])
        CheckTarget(v, v.WorldToViewport(angle.middleVertex), angle, 2)
        InstallScene(main, [angle])
        CheckTarget(v, v.AngleLayout(angle, selected = True)[1].center(), angle, 3)
    print("PASS: rendered hover, cursor and click agree for overlapping handles, bodies, vertices and labels")


if __name__ == "__main__":
    Main()
