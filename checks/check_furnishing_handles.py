"""Native handle dragging: local anchors, rotation snapping and invalid rollback."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall
from furnishings import Furnishing
from planner_app.graphics.palette import themeColors


def Mouse(viewport, eventType, position, modifiers = QtCore.Qt.KeyboardModifier.NoModifier):
    left = QtCore.Qt.MouseButton.LeftButton
    buttons = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseButtonRelease else left
    button = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseMove else left
    event = QtGui.QMouseEvent(eventType, position,
                             QtCore.QPointF(viewport.mapToGlobal(position.toPoint())), button, buttons, modifiers)
    QtWidgets.QApplication.sendEvent(viewport, event)


def Center(furnishing):
    return (furnishing.firstVertex + furnishing.secondVertex) / 2


app = QtWidgets.QApplication([])
main = MainWindow()
main.show()
app.processEvents()
viewport = main.viewport
viewport.snapEnabled = False
point = QtCore.QPointF
press = QtCore.QEvent.Type.MouseButtonPress
move = QtCore.QEvent.Type.MouseMove
release = QtCore.QEvent.Type.MouseButtonRelease
desk = Furnishing(viewport.furnishingDefinitions["desk"])
viewport.furnishings = [desk]
viewport.SetSelection([(desk, None)])

# Every side remains local to the furnishing and anchors its opposite side.
for angle in (0, 37, 90):
    for field in ("width", "length"):
        for sign in (-1, 1):
            desk.firstVertex, desk.secondVertex = point(0, -300), point(0, 300)
            desk.width = 1200
            desk.angle = angle
            viewport.undoHistory = []
            north = (desk.secondVertex - desk.firstVertex) / desk.length
            axis = north if field == "length" else point(north.y(), -north.x())
            originalSize = getattr(desk, field)
            anchor = Center(desk) - axis * (sign * originalSize / 2)
            handle = next(handle for handle in viewport.FurnishingHandles(desk)
                          if handle[:3] == ("resize", field, sign))
            start = handle[3]
            end = viewport.WorldToViewport(viewport.ViewportToWorld(start) + axis * (sign * 200))
            Mouse(viewport, press, start)
            assert viewport.furnishingHandleDrag is not None and not viewport.groupDrag
            for distance in (100, 400, 400, -200, 0, 200):
                position = viewport.WorldToViewport(viewport.ViewportToWorld(start) + axis * (sign * distance))
                Mouse(viewport, move, position)
                assert math.isclose(getattr(desk, field), originalSize + distance, abs_tol = 1e-6)
                assert QtCore.QLineF(Center(desk) - axis * (sign * getattr(desk, field) / 2), anchor).length() < 1e-6
            Mouse(viewport, release, end)
            assert len(viewport.undoHistory) == 1 and viewport.furnishingHandleDrag is None
            assert QtCore.QLineF(Center(desk) - axis * (sign * getattr(desk, field) / 2), anchor).length() < 1e-6
            viewport.Undo()
            assert math.isclose(getattr(desk, field), originalSize, abs_tol = 1e-6)
            viewport.Redo()
            assert math.isclose(getattr(desk, field), originalSize + 200, abs_tol = 1e-6)
            assert QtCore.QLineF(Center(desk) - axis * (sign * getattr(desk, field) / 2), anchor).length() < 1e-6

# Every resize corner anchors its diagonal opposite through repeated updates.
for angle in (0, 37, 90):
    for eastSign, northSign in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        desk.firstVertex, desk.secondVertex = point(0, -300), point(0, 300)
        desk.width = 1200
        desk.angle = angle
        viewport.undoHistory = []
        north = (desk.secondVertex - desk.firstVertex) / desk.length
        east = point(north.y(), -north.x())
        anchor = Center(desk) - east * (eastSign * 600) - north * (northSign * 300)
        handle = next(handle for handle in viewport.FurnishingHandles(desk)
                      if handle[:3] == ("resize", "corner", (eastSign, northSign)))
        start = handle[3]
        Mouse(viewport, press, start)
        assert viewport.furnishingHandleDrag["handle"][1] == "corner"
        for widthDelta, lengthDelta, expectedWidth in ((200, 100, 1400), (200, 100, 1400),
                                                      (-400, -200, 800), (100, -200, 1200), (200, 100, 1400)):
            end = viewport.WorldToViewport(viewport.ViewportToWorld(start)
                                           + east * (eastSign * widthDelta) + north * (northSign * lengthDelta))
            Mouse(viewport, move, end)
            assert math.isclose(desk.width, expectedWidth, abs_tol = 1e-6)
            assert math.isclose(desk.length, expectedWidth / 2, abs_tol = 1e-6)
            assert math.isclose(desk.width / desk.length, 2, abs_tol = 1e-6)
            currentAnchor = Center(desk) - east * (eastSign * desk.width / 2) - north * (northSign * desk.length / 2)
            assert QtCore.QLineF(currentAnchor, anchor).length() < 1e-6
        Mouse(viewport, release, end)
        currentAnchor = Center(desk) - east * (eastSign * desk.width / 2) - north * (northSign * desk.length / 2)
        assert QtCore.QLineF(currentAnchor, anchor).length() < 1e-6
        assert len(viewport.undoHistory) == 1
        viewport.Undo()
        assert math.isclose(desk.width, 1200) and math.isclose(desk.length, 600)
        assert QtCore.QLineF(Center(desk), point()).length() < 1e-6
        viewport.Redo()
        assert math.isclose(desk.width, 1400) and math.isclose(desk.length, 700)

# Corner rotation follows Snap, including live toggles and temporary Alt inversion.
desk.firstVertex, desk.secondVertex = point(0, -300), point(0, 300)
desk.width = 1200
centerClick = viewport.WorldToViewport(Center(desk))
Mouse(viewport, press, centerClick)
Mouse(viewport, release, centerClick)
assert viewport.furnishingRotationObject is desk
for corner in range(4):
    desk.angle = 22
    center = Center(desk)
    start = viewport.FurnishingHandles(desk)[4 + corner][3]
    offset = viewport.ViewportToWorld(start) - center
    angle = math.radians(37)
    rotated = point(offset.x() * math.cos(angle) - offset.y() * math.sin(angle),
                    offset.x() * math.sin(angle) + offset.y() * math.cos(angle))
    end = viewport.WorldToViewport(center + rotated)
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    Mouse(viewport, press, start)
    Mouse(viewport, move, end)
    assert math.isclose(desk.angle, 59, abs_tol = 1e-6)
    Mouse(viewport, move, end, ctrl)
    assert math.isclose(desk.angle, 59, abs_tol = 1e-6)
    main.SetSnapping(True)
    Mouse(viewport, move, end)
    assert math.isclose(desk.angle, 60, abs_tol = 1e-6)
    Mouse(viewport, move, end, QtCore.Qt.KeyboardModifier.AltModifier)
    assert math.isclose(desk.angle, 59, abs_tol = 1e-6)
    Mouse(viewport, move, end)
    assert math.isclose(desk.angle, 60, abs_tol = 1e-6)
    main.SetSnapping(False)
    Mouse(viewport, move, end, ctrl)
    assert math.isclose(desk.angle, 59, abs_tol = 1e-6)
    main.SetSnapping(True)
    assert QtCore.QLineF(Center(desk), center).length() < 1e-6
    assert math.isclose(desk.length, 600) and desk.width == 1200
    Mouse(viewport, release, end)
    main.SetSnapping(False)
    viewport.Undo()
    assert math.isclose(desk.angle, 22, abs_tol = 1e-6)

# Invalid geometry remains draggable and rolls back on release or Escape.
centerClick = viewport.WorldToViewport(Center(desk)) + point(20, 0)
Mouse(viewport, press, centerClick)
Mouse(viewport, release, centerClick)
assert viewport.furnishingRotationObject is None
desk.angle = 0
viewport.walls = [Wall(point(850, -2000), point(850, 2000), 100)]
viewport.undoHistory = []
start = next(handle[3] for handle in viewport.FurnishingHandles(desk) if handle[:3] == ("resize", "width", 1))
end = viewport.WorldToViewport(viewport.ViewportToWorld(start) + point(400, 0))
Mouse(viewport, press, start)
Mouse(viewport, move, end)
assert desk.width == 1600 and not viewport.FurnishingFits(desk)
viewport.grab()
Mouse(viewport, release, end)
assert desk.width == 1200 and Center(desk) == point() and not viewport.undoHistory
Mouse(viewport, press, start)
Mouse(viewport, move, end)
viewport.CancelInteraction()
assert desk.width == 1200 and Center(desk) == point() and viewport.furnishingHandleDrag is None

# Invalid corner resizing restores both dimensions and its original midpoint.
start = next(handle[3] for handle in viewport.FurnishingHandles(desk)
             if handle[:3] == ("resize", "corner", (1, 1)))
end = viewport.WorldToViewport(viewport.ViewportToWorld(start) + point(400, 200))
Mouse(viewport, press, start)
Mouse(viewport, move, end)
assert math.isclose(desk.width, 1600) and math.isclose(desk.length, 800)
assert not viewport.FurnishingFits(desk)
Mouse(viewport, release, end)
assert desk.width == 1200 and math.isclose(desk.length, 600) and Center(desk) == point()
assert not viewport.undoHistory

# A rotation can pass through a collision and finish in another valid orientation.
centerClick = viewport.WorldToViewport(Center(desk))
Mouse(viewport, press, centerClick)
Mouse(viewport, release, centerClick)
viewport.walls = [Wall(point(650, -2000), point(650, 2000), 100)]
start = viewport.FurnishingHandles(desk)[4][3]
offset = viewport.ViewportToWorld(start)
Mouse(viewport, press, start)
for degrees in (45, 90):
    radians = math.radians(degrees)
    end = viewport.WorldToViewport(point(offset.x() * math.cos(radians) - offset.y() * math.sin(radians),
                                         offset.x() * math.sin(radians) + offset.y() * math.cos(radians)))
    Mouse(viewport, move, end)
    assert math.isclose(desk.angle, degrees, abs_tol = 1e-6)
    assert viewport.FurnishingFits(desk) == (degrees == 90)
Mouse(viewport, release, end)
assert math.isclose(desk.angle, 90, abs_tol = 1e-6) and len(viewport.undoHistory) == 1
viewport.Undo()
assert math.isclose(desk.angle, 0, abs_tol = 1e-6)

# Hover reveals the eight scale handles; moving away hides them.
viewport.walls = []
viewport.SetSelection([])
viewport.hoverPosition = viewport.WorldToViewport(point())
assert len(viewport.VisibleFurnishingHandles()[0][1]) == 8
handlePixel = viewport.FurnishingHandles(desk)[0][3].toPoint()
hoverImage = viewport.grab().toImage()
reference = QtGui.QColor(themeColors["objectOutline"]).getRgb()[:3]
assert any(all(abs(actual - expected) <= 2 for actual, expected in
               zip(hoverImage.pixelColor(handlePixel + QtCore.QPoint(x, y)).getRgb()[:3], reference))
           for x in range(-10, 11) for y in range(-10, 11))
viewport.SetSelection([(desk, None)])
selectedImage = viewport.grab().toImage()
reference = QtGui.QColor(viewport.SelectionColor(desk)).getRgb()[:3]
assert any(all(abs(actual - expected) <= 2 for actual, expected in
               zip(selectedImage.pixelColor(handlePixel + QtCore.QPoint(x, y)).getRgb()[:3], reference))
           for x in range(-10, 11) for y in range(-10, 11))
viewport.showMeasurements = False
viewport.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots/resize-handle-icons.png"))
viewport.SetSelection([])
viewport.hoverPosition = point(handlePixel)
assert viewport.HitFurnishingHandle(point(handlePixel))[0] is desk
viewport.hoverPosition = point(40, 40)
assert not viewport.VisibleFurnishingHandles()
main.close()
print("PASS: local resizing, anchored proportional corners, rotation Snap settings, hover and collision/cancel history")
