"""Temporary pivots snap, cancel, reset, and orbit individual and selected objects."""
import math
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.models import Furnishing, Label, Pillar, Wall


def Mouse(viewport, eventType, position, modifiers = QtCore.Qt.KeyboardModifier.NoModifier,
          button = QtCore.Qt.MouseButton.LeftButton):
    buttons = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseButtonRelease else button
    eventButton = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseMove else button
    event = QtGui.QMouseEvent(eventType, position, QtCore.QPointF(viewport.mapToGlobal(position.toPoint())),
                             eventButton, buttons, modifiers)
    QtWidgets.QApplication.sendEvent(viewport, event)


def Center(obj):
    return (obj.firstVertex + obj.secondVertex) / 2


def DragPivot(viewport, target, modifiers = QtCore.Qt.KeyboardModifier.NoModifier, cancel = False):
    handle = next(handle for obj, handles in viewport.VisibleFurnishingHandles() for handle in handles if handle[0] == "pivot")
    Mouse(viewport, QtCore.QEvent.Type.MouseButtonPress, handle[3])
    end = viewport.WorldToViewport(target)
    Mouse(viewport, QtCore.QEvent.Type.MouseMove, end, modifiers)
    assert viewport.cursor().shape() == QtCore.Qt.CursorShape.SizeAllCursor
    if cancel:
        Mouse(viewport, QtCore.QEvent.Type.MouseButtonPress, end, button = QtCore.Qt.MouseButton.RightButton)
    else:
        Mouse(viewport, QtCore.QEvent.Type.MouseButtonRelease, end, modifiers)


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    press, move, release = QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseMove, QtCore.QEvent.Type.MouseButtonRelease
    desk = Furnishing(v.furnishingDefinitions["desk"])
    v.furnishings = [desk]
    v.SetSelection([(desk, None)])
    v.furnishingRotationObject = desk
    v.snapEnabled = False
    original = (point(desk.firstVertex), point(desk.secondVertex))
    DragPivot(v, point(600, 400))
    assert v.rotationPivot == point(600, 400)
    assert (desk.firstVertex, desk.secondVertex) == original and not v.undoHistory
    DragPivot(v, point(900, 800), QtCore.Qt.KeyboardModifier.ControlModifier)
    assert v.rotationPivot == point(600, 800), "Ctrl did not constrain the pivot's translation"
    assert v.axisConstraintOrigin is None
    DragPivot(v, point(-500, 700), cancel = True)
    assert v.rotationPivot == point(600, 800) and v.dragStart is None
    v.snapEnabled = True
    v.vertexSnapEnabled = v.midpointSnapEnabled = v.alignmentSnapEnabled = False
    v.gridSnapEnabled = True
    minorStep = v.GridSteps()[1]
    target = point(minorStep * 3.2, minorStep * 2.3)
    DragPivot(v, target)
    assert v.rotationPivot == point(minorStep * 3, minorStep * 2)
    v.walls = [Wall(point(-700, 650), point(-700, 1200), 80)]
    v.vertexSnapEnabled = True
    DragPivot(v, point(-697, 648))
    assert v.rotationPivot == point(-700, 650), "Pivot did not snap to an object vertex"
    v.walls = []

    # Arbitrary external origins rotate furnishings, labels, pillars and a shared selection.
    label = Label(point(), "Pivot")
    label.firstVertex, label.secondVertex = point(0, -300), point(0, 300)
    label.width = 600
    pillar = Pillar(point(0, -300), point(0, 300), 600)
    second = Furnishing(desk.definition, point(700, 0))
    for objects in ([desk], [label], [pillar], [desk, second]):
        v.CancelInteraction()
        v.walls = [obj for obj in objects if isinstance(obj, Pillar)]
        v.labels = [obj for obj in objects if isinstance(obj, Label)]
        v.furnishings = [obj for obj in objects if type(obj) is Furnishing]
        v.SetSelection([(obj, None) for obj in objects])
        v.furnishingRotationObject = objects[0]
        v.rotationPivot = point(-600, 500)
        v.snapEnabled = False
        v.undoHistory = []
        originals = [(obj, Center(obj), obj.angle, obj.width, obj.length) for obj in objects]
        handle = next(handle for obj, handles in v.VisibleFurnishingHandles() for handle in handles if handle[0] == "rotate")
        pivot = point(v.rotationPivot)
        offset = v.ViewportToWorld(handle[3]) - pivot
        radians = math.radians(40)
        end = v.WorldToViewport(pivot + point(offset.x() * math.cos(radians) - offset.y() * math.sin(radians),
                                              offset.x() * math.sin(radians) + offset.y() * math.cos(radians)))
        Mouse(v, press, handle[3])
        Mouse(v, move, end)
        Mouse(v, release, end)
        for obj, center, angle, width, length in originals:
            offset = center - pivot
            expected = pivot + point(offset.x() * math.cos(radians) - offset.y() * math.sin(radians),
                                     offset.x() * math.sin(radians) + offset.y() * math.cos(radians))
            assert QtCore.QLineF(Center(obj), expected).length() < 1e-6, (type(obj).__name__, Center(obj), expected, handle[3], end)
            assert math.isclose((obj.angle - angle) % 360, 40, abs_tol = 1e-6)
            assert math.isclose(obj.width, width) and math.isclose(obj.length, length)
        assert v.rotationPivot == pivot and len(v.undoHistory) == 1
        v.Undo()
        assert all(QtCore.QLineF(Center(obj), center).length() < 1e-6 for obj, center, angle, width, length in originals)

        # A real double-click sequence resets an external pivot without moving
        # the selection, changing the view, or creating an undo entry.
        v.furnishingRotationObject = objects[0]
        v.rotationPivot = point(-600, 500)
        pivotPosition = v.WorldToViewport(v.rotationPivot)
        zoom = v.zoom
        historyLength = len(v.undoHistory)
        Mouse(v, press, pivotPosition)
        Mouse(v, release, pivotPosition)
        Mouse(v, QtCore.QEvent.Type.MouseButtonDblClick, pivotPosition)
        Mouse(v, release, pivotPosition)
        assert v.rotationPivot is None and v.furnishingRotationObject is objects[0]
        assert v.zoom == zoom and len(v.undoHistory) == historyLength
        assert v.dragStart is None and v.furnishingHandleDrag is None
        assert all(QtCore.QLineF(Center(obj), center).length() < 1e-6 for obj, center, angle, width, length in originals)
        selectionBox = v.FurnishingSelectionBox()
        expectedCenter = Center(selectionBox if selectionBox is not None else objects[0])
        handle = next(handle for obj, handles in v.VisibleFurnishingHandles() for handle in handles if handle[0] == "pivot")
        assert QtCore.QLineF(v.ViewportToWorld(handle[3]), expectedCenter).length() < 1e-6

    # An asymmetric selection's axis-aligned bounds change center as it turns.
    # Its displayed and retained pivot must stay at the gesture's actual origin.
    v.walls, v.windows, v.labels, v.objectGroups = [], [], [], []
    v.zoom = .15
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    for modifiers in (QtCore.Qt.KeyboardModifier.NoModifier, shift):
        objects = [Furnishing(desk.definition, point(-900, -400)),
                   Furnishing(desk.definition, point(1100, 200)),
                   Furnishing(desk.definition, point(-200, 1400))]
        for index, obj in enumerate(objects):
            center = Center(obj)
            obj.width = 200 + index * 100
            obj.firstVertex, obj.secondVertex = center - point(0, 150), center + point(0, 150)
        v.furnishings = objects
        v.SetSelection([(obj, None) for obj in objects])
        v.furnishingRotationObject = objects[0]
        v.rotationPivot = None
        v.snapEnabled = False
        box = v.FurnishingSelectionBox()
        pivot = Center(box)
        originals = [(Center(obj), obj.angle, obj.width, obj.length) for obj in objects]
        handle = next(handle for handle in v.FurnishingHandles(box) if handle[0] == "rotate")
        offset = v.ViewportToWorld(handle[3]) - pivot
        v.BeginFurnishingHandleDrag(box, handle, handle[3])
        for degrees in range(15, 361, 15):
            radians = math.radians(degrees)
            end = v.WorldToViewport(pivot + point(offset.x() * math.cos(radians) - offset.y() * math.sin(radians),
                                                  offset.x() * math.sin(radians) + offset.y() * math.cos(radians)))
            v.UpdateFurnishingHandleDrag(end, modifiers)
            pivotHandle = next(handle for obj, handles in v.VisibleFurnishingHandles()
                               for handle in handles if handle[0] == "pivot")
            assert QtCore.QLineF(v.ViewportToWorld(pivotHandle[3]), pivot).length() < 1e-6, degrees
            for (obj, index), (center, angle, width, length) in zip(v.SelectionEntries(), originals):
                delta = center - pivot
                expected = pivot + point(delta.x() * math.cos(radians) - delta.y() * math.sin(radians),
                                         delta.x() * math.sin(radians) + delta.y() * math.cos(radians))
                assert QtCore.QLineF(Center(obj), expected).length() < 1e-6
                assert math.isclose(obj.width, width) and math.isclose(obj.length, length)
        # Commit a partial turn, then start another gesture at the same origin.
        end = v.WorldToViewport(pivot + point(-offset.y(), offset.x()))
        v.UpdateFurnishingHandleDrag(end, modifiers)
        Mouse(v, release, end, modifiers)
        assert v.rotationPivot == pivot
        box = v.FurnishingSelectionBox()
        handle = next(handle for handle in v.FurnishingHandles(box) if handle[0] == "rotate")
        v.BeginFurnishingHandleDrag(box, handle, handle[3])
        assert v.furnishingHandleDrag["pivot"] == pivot
        v.CancelInteraction()
        v.DeselectAll()
        assert v.rotationPivot is None

    # Cancelling a first rotation must restore the previously implicit pivot.
    v.furnishings = objects
    v.SetSelection([(obj, None) for obj in objects])
    v.furnishingRotationObject = objects[0]
    box = v.FurnishingSelectionBox()
    handle = next(handle for handle in v.FurnishingHandles(box) if handle[0] == "rotate")
    v.BeginFurnishingHandleDrag(box, handle, handle[3])
    v.UpdateFurnishingHandleDrag(handle[3] + point(30, 20), QtCore.Qt.KeyboardModifier.NoModifier)
    v.CancelInteraction()
    assert v.rotationPivot is None

    v.furnishings = [desk]
    v.SetSelection([(desk, None)])
    v.furnishingRotationObject = desk
    v.rotationPivot = point(-600, 500)
    body = v.WorldToViewport(Center(desk)) + point(20, 0)
    Mouse(v, press, body)
    Mouse(v, release, body)
    assert v.furnishingRotationObject is None and v.rotationPivot is None
    Mouse(v, press, body)
    Mouse(v, release, body)
    assert v.furnishingRotationObject is desk
    pivotHandle = next(handle for obj, handles in v.VisibleFurnishingHandles() for handle in handles if handle[0] == "pivot")
    assert QtCore.QLineF(v.ViewportToWorld(pivotHandle[3]), Center(desk)).length() < 1e-6
    DragPivot(v, point(-600, 500))
    v.DeselectAll()
    assert v.rotationPivot is None and v.furnishingRotationObject is None
    main.close()


if __name__ == "__main__":
    Main()
