"""Bounding-box handles transform all furnishing members as one undoable gesture."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall
from furnishings import Furnishing


def Mouse(viewport, eventType, position):
    left = QtCore.Qt.MouseButton.LeftButton
    button = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseMove else left
    buttons = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseButtonRelease else left
    event = QtGui.QMouseEvent(eventType, position, QtCore.QPointF(viewport.mapToGlobal(position.toPoint())),
                             button, buttons, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, event)


def Center(obj):
    return (obj.firstVertex + obj.secondVertex) / 2


def Reset(viewport, objects):
    viewport.CancelInteraction()
    viewport.walls = []
    for obj, x, angle in zip(objects, (-800, 800), (0, 90)):
        obj.firstVertex, obj.secondVertex = QtCore.QPointF(x, -300), QtCore.QPointF(x, 300)
        obj.width = 1200
        obj.angle = angle
    viewport.SetSelection([(obj, None) for obj in objects])
    viewport.furnishingRotationObject = None
    viewport.undoHistory = []
    viewport.redoHistory = []
    viewport.snapEnabled = False


app = QtWidgets.QApplication([])
main = MainWindow()
main.show()
app.processEvents()
viewport = main.viewport
point = QtCore.QPointF
objects = [Furnishing(viewport.furnishingDefinitions["desk"]) for index in range(2)]
viewport.furnishings = objects
press, move, release = QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseMove, QtCore.QEvent.Type.MouseButtonRelease
Reset(viewport, objects)
box = viewport.FurnishingSelectionBox()
assert math.isclose(box.width, 2500) and math.isclose(box.length, 1200)
visible = viewport.VisibleFurnishingHandles()
assert len(visible) == 1 and len(visible[0][1]) == 8
assert visible[0][0].selectionMembers == tuple(objects)

# Clicking different members toggles the shared mode, preserving the selection.
for obj in objects:
    position = viewport.WorldToViewport(Center(obj))
    Mouse(viewport, press, position)
    Mouse(viewport, release, position)
    assert len(viewport.SelectionEntries()) == 2
    expected = "rotate" if obj is objects[0] else "resize"
    assert {handle[0] for handle in viewport.VisibleFurnishingHandles()[0][1]} == ({"rotate", "pivot"} if expected == "rotate" else {"resize"})

# Side handles anchor the opposite group edge, including differently oriented members.
for field in ("width", "length"):
    for sign in (-1, 1):
        Reset(viewport, objects)
        box = viewport.FurnishingSelectionBox()
        originalSize = getattr(box, field)
        axis = point(1, 0) if field == "width" else point(0, 1)
        anchor = QtCore.QPointF.dotProduct(Center(box), axis) - sign * originalSize / 2
        start = next(handle[3] for handle in viewport.FurnishingHandles(box) if handle[:3] == ("resize", field, sign))
        Mouse(viewport, press, start)
        for distance in (100, 400, 400, -200, 100):
            end = viewport.WorldToViewport(viewport.ViewportToWorld(start) + axis * (sign * distance))
            Mouse(viewport, move, end)
            current = viewport.FurnishingSelectionBox()
            assert math.isclose(getattr(current, field), originalSize + distance, abs_tol = 1e-6)
            assert math.isclose(QtCore.QPointF.dotProduct(Center(current), axis) - sign * getattr(current, field) / 2,
                                anchor, abs_tol = 1e-6)
        Mouse(viewport, release, end)
        assert len(viewport.undoHistory) == 1 and len(viewport.SelectionEntries()) == 2
        viewport.Undo()
        assert math.isclose(viewport.FurnishingSelectionBox().width, 2500)
        assert math.isclose(viewport.FurnishingSelectionBox().length, 1200)

# Corner scaling preserves the selection and each member's aspect ratio and opposite corner.
for eastSign, northSign in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
    Reset(viewport, objects)
    box = viewport.FurnishingSelectionBox()
    diagonal = point(eastSign * box.width, northSign * box.length)
    anchor = Center(box) - diagonal / 2
    originalCenters = [Center(obj) for obj in objects]
    start = next(handle[3] for handle in viewport.FurnishingHandles(box)
                 if handle[:3] == ("resize", "corner", (eastSign, northSign)))
    Mouse(viewport, press, start)
    for scale in (1.2, 1.4, .7, 1.2):
        end = viewport.WorldToViewport(viewport.ViewportToWorld(start) + diagonal * (scale - 1))
        Mouse(viewport, move, end)
        current = viewport.FurnishingSelectionBox()
        assert QtCore.QLineF(Center(current) - point(eastSign * current.width, northSign * current.length) / 2,
                            anchor).length() < 1e-6
        for obj, originalCenter in zip(objects, originalCenters):
            assert math.isclose(obj.width, 1200 * scale) and math.isclose(obj.length, 600 * scale)
            assert QtCore.QLineF(Center(obj), anchor + (originalCenter - anchor) * scale).length() < 1e-6
    Mouse(viewport, release, end)
    viewport.Undo()
    viewport.Redo()
    assert all(math.isclose(obj.width, 1440) and math.isclose(obj.length, 720) for obj in objects)

# Rotation orbits each midpoint and rotates each graphic; Snap quantizes the shared angle.
Reset(viewport, objects)
box = viewport.FurnishingSelectionBox()
pivot = Center(box)
originalCenters = [Center(obj) for obj in objects]
viewport.furnishingRotationObject = objects[0]
start = viewport.VisibleFurnishingHandles()[0][1][0][3]
offset = viewport.ViewportToWorld(start) - pivot
Mouse(viewport, press, start)
for degrees, snapping in ((37, False), (30, True)):
    viewport.snapEnabled = snapping
    radians = math.radians(37)
    rotated = point(offset.x() * math.cos(radians) - offset.y() * math.sin(radians),
                    offset.x() * math.sin(radians) + offset.y() * math.cos(radians))
    end = viewport.WorldToViewport(pivot + rotated)
    Mouse(viewport, move, end)
    radians = math.radians(degrees)
    for index, (obj, originalCenter) in enumerate(zip(objects, originalCenters)):
        relative = originalCenter - pivot
        expected = pivot + point(relative.x() * math.cos(radians) - relative.y() * math.sin(radians),
                                 relative.x() * math.sin(radians) + relative.y() * math.cos(radians))
        assert QtCore.QLineF(Center(obj), expected).length() < 1e-6
        assert math.isclose(obj.angle, degrees + index * 90, abs_tol = 1e-6)
        assert math.isclose(obj.width, 1200) and math.isclose(obj.length, 600)
Mouse(viewport, release, end)
assert len(viewport.undoHistory) == 1
viewport.Undo()
assert all(QtCore.QLineF(Center(obj), center).length() < 1e-6 for obj, center in zip(objects, originalCenters))

# One colliding member cancels the entire group; Escape does the same.
Reset(viewport, objects)
viewport.walls = [Wall(point(1800, -3000), point(1800, 3000), 100)]
box = viewport.FurnishingSelectionBox()
start = next(handle[3] for handle in viewport.FurnishingHandles(box) if handle[:3] == ("resize", "corner", (1, 1)))
end = viewport.WorldToViewport(viewport.ViewportToWorld(start) + point(box.width, box.length) * .5)
for cancel in (False, True):
    Mouse(viewport, press, start)
    Mouse(viewport, move, end)
    assert any(not viewport.FurnishingFits(obj) for obj in objects)
    viewport.grab()
    if cancel:
        viewport.CancelInteraction()
    else:
        Mouse(viewport, release, end)
    assert all(math.isclose(obj.width, 1200) and math.isclose(obj.length, 600) for obj in objects)
    assert not viewport.undoHistory and len(viewport.SelectionEntries()) == 2

viewport.SetSelection([(objects[0], None), (viewport.walls[0], None)])
assert viewport.FurnishingSelectionBox().rotationOnly
assert {handle[0] for obj, handles in viewport.VisibleFurnishingHandles() for handle in handles} == {"rotate", "pivot"}
main.close()
print("PASS: furnishing-only AABB handles, shared mode, anchored side/corner scaling, group rotation, Snap, atomic history and cancellation")
