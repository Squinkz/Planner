"""Resize uses actual corners/edges, snap priorities, constraints and external targets."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from furnishings import Furnishing


def Mouse(viewport, eventType, position, modifiers = QtCore.Qt.KeyboardModifier.NoModifier):
    left = QtCore.Qt.MouseButton.LeftButton
    button = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseMove else left
    buttons = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseButtonRelease else left
    event = QtGui.QMouseEvent(eventType, position, QtCore.QPointF(viewport.mapToGlobal(position.toPoint())),
                             button, buttons, modifiers)
    QtWidgets.QApplication.sendEvent(viewport, event)


def Reset(viewport, desk, targets = (), angle = 0):
    viewport.CancelInteraction()
    desk.firstVertex, desk.secondVertex = QtCore.QPointF(0, -300), QtCore.QPointF(0, 300)
    desk.width = 1200
    desk.angle = angle
    viewport.furnishings = [desk] + list(targets)
    viewport.SetSelection([(desk, None)])
    viewport.furnishingRotationObject = None
    viewport.snapEnabled = True
    viewport.gridSnapEnabled = False
    viewport.vertexSnapEnabled = False
    viewport.cornerSnapEnabled = False
    viewport.midpointSnapEnabled = False
    viewport.alignmentSnapEnabled = False


def Drag(viewport, box, field, sign, delta, modifiers = QtCore.Qt.KeyboardModifier.NoModifier):
    start = next(handle[3] for handle in viewport.FurnishingHandles(box) if handle[:3] == ("resize", field, sign))
    end = viewport.WorldToViewport(viewport.ViewportToWorld(start) + delta)
    assert viewport.DrawingRect().contains(start), (start, viewport.DrawingRect())
    assert viewport.DrawingRect().contains(end), (end, viewport.DrawingRect())
    Mouse(viewport, press, start)
    assert viewport.furnishingHandleDrag is not None, "The fixture must start a real handle drag."
    Mouse(viewport, move, end, modifiers)
    return end


app = QtWidgets.QApplication([])
main = MainWindow()
main.resize(2200, 1100)
main.show()
app.processEvents()
viewport = main.viewport
point = QtCore.QPointF
press, move, release = QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseMove, QtCore.QEvent.Type.MouseButtonRelease
desk = Furnishing(viewport.furnishingDefinitions["desk"])
null = viewport.furnishingDefinitions["null"]

# Snapping is based on the actual corner, not the arrow's screen offset.
Reset(viewport, desk)
viewport.gridSnapEnabled = True
end = Drag(viewport, desk, "corner", (1, 1), point(185, 92.5))
assert math.isclose(desk.width, 1400) and math.isclose(desk.length, 700)
Mouse(viewport, release, end)
viewport.Undo()
assert desk.width == 1200 and math.isclose(desk.length, 600)

# A nearby external corner wins over grid, while preserving aspect ratio.
target = Furnishing(null, point(1280, 890))  # Southwest corner at (780, 390).
Reset(viewport, desk, [target])
viewport.cornerSnapEnabled = True
viewport.gridSnapEnabled = True
end = Drag(viewport, desk, "corner", (1, 1), point(185, 92.5))
assert math.isclose(desk.width, 1380) and math.isclose(desk.length, 690)
Mouse(viewport, move, end, QtCore.Qt.KeyboardModifier.AltModifier)
assert math.isclose(desk.width, 1385) and math.isclose(desk.length, 692.5)
Mouse(viewport, move, end)
assert math.isclose(desk.width, 1380)
Mouse(viewport, release, end)

# Control Points alone must not enable furnishing-corner targets.
Reset(viewport, desk, [target])
viewport.vertexSnapEnabled = True
viewport.gridSnapEnabled = True
end = Drag(viewport, desk, "corner", (1, 1), point(185, 92.5))
assert math.isclose(desk.width, 1400) and math.isclose(desk.length, 700)
Mouse(viewport, release, end)

# Side resizing snaps anywhere on its edge, including between midpoint and endpoints.
for snapType in ("corner", "alignment", "midpoint"):
    target = Furnishing(null, point(770, 170) if snapType == "midpoint" else point(1270, 670))
    if snapType == "alignment":
        target = Furnishing(null, point(1270, 1670))  # Corner lies beyond the moving edge's span.
    Reset(viewport, desk, [target])
    viewport.cornerSnapEnabled = snapType in ("corner", "alignment")
    viewport.alignmentSnapEnabled = snapType == "alignment"
    viewport.midpointSnapEnabled = snapType == "midpoint"
    viewport.gridSnapEnabled = True
    end = Drag(viewport, desk, "width", 1, point(160, 0))
    assert math.isclose(desk.width, 1370) and math.isclose(desk.length, 600)
    center = (desk.firstVertex + desk.secondVertex) / 2
    assert math.isclose(center.x() - desk.width / 2, -600)
    assert viewport.snapPriority < 2
    Mouse(viewport, release, end)

# Rotated edges use their own normal and retain their anchored opposite edge.
Reset(viewport, desk, angle = 37)
north = (desk.secondVertex - desk.firstVertex) / desk.length
east = point(north.y(), -north.x())
edgeTarget = east * 740 + north * 110
target = Furnishing(null, edgeTarget + point(500, 500))
viewport.furnishings.append(target)
viewport.cornerSnapEnabled = True
end = Drag(viewport, desk, "width", 1, east * 132)
assert math.isclose(desk.width, 1340, abs_tol = 1e-6)
center = (desk.firstVertex + desk.secondVertex) / 2
assert math.isclose(QtCore.QPointF.dotProduct(center, east) - desk.width / 2, -600, abs_tol = 1e-6)
assert math.isclose(desk.angle, 37, abs_tol = 1e-6)
Mouse(viewport, release, end)

# Moving objects never contribute their own vertices or midpoints as snap targets.
Reset(viewport, desk)
viewport.cornerSnapEnabled = True
viewport.midpointSnapEnabled = True
end = Drag(viewport, desk, "width", 1, point(15, 0))
# Cross the drag threshold before returning to a position close to the original edge.
Mouse(viewport, move, end + point(30, 0))
Mouse(viewport, move, end)
assert math.isclose(desk.width, 1215)
Mouse(viewport, release, end)

# The selection's corner snaps as one unit, excluding every moving member.
Reset(viewport, desk)
desk.firstVertex += point(-800, 0)
desk.secondVertex += point(-800, 0)
other = Furnishing(desk.definition, point(800, 0))
target = Furnishing(null, point(2180, 860))  # Corner at (1680, 360).
viewport.furnishings = [desk, other, target]
viewport.SetSelection([(desk, None), (other, None)])
viewport.cornerSnapEnabled = True
box = viewport.FurnishingSelectionBox()
end = Drag(viewport, box, "corner", (1, 1), point(266, 57))
current = viewport.FurnishingSelectionBox()
assert math.isclose(current.width, 3080) and math.isclose(current.length, 660)
assert math.isclose(desk.width, 1320) and math.isclose(other.width, 1320)
assert math.isclose((current.firstVertex.x() + current.secondVertex.x()) / 2 - current.width / 2, -1400)
Mouse(viewport, release, end)

# The visible group edge itself meets the target even with arbitrary member rotations.
Reset(viewport, desk, angle = 37)
other = Furnishing(desk.definition, point(1600, 200))
other.angle = 71
viewport.furnishings = [desk, other]
viewport.SetSelection([(desk, None), (other, None)])
box = viewport.FurnishingSelectionBox()
originalRight = (box.firstVertex.x() + box.secondVertex.x()) / 2 + box.width / 2
originalLeft = originalRight - box.width
targetPoint = point(originalRight + 230, (box.firstVertex.y() + box.secondVertex.y()) / 2 + 170)
viewport.furnishings.append(Furnishing(null, targetPoint + point(500, 500)))
viewport.cornerSnapEnabled = True
end = Drag(viewport, box, "width", 1, point(220, 0))
current = viewport.FurnishingSelectionBox()
currentCenterX = (current.firstVertex.x() + current.secondVertex.x()) / 2
assert math.isclose(currentCenterX + current.width / 2, targetPoint.x(), abs_tol = 1e-6)
assert math.isclose(currentCenterX - current.width / 2, originalLeft, abs_tol = 1e-6)
assert math.isclose(desk.angle, 37, abs_tol = 1e-6) and math.isclose(other.angle, 71, abs_tol = 1e-6)
Mouse(viewport, release, end)

# Corner arrow direction stays 45 degrees in local axes at every aspect ratio.
viewport.CancelInteraction()
for angle in (0, 37, 90):
    for width, length in ((100, 100), (2000, 100), (100, 2000)):
        desk.firstVertex, desk.secondVertex = point(0, -length / 2), point(0, length / 2)
        desk.width = width
        desk.angle = angle
        north = (desk.secondVertex - desk.firstVertex) / desk.length
        east = point(north.y(), -north.x())
        for mode, field, sign, position, outward in viewport.FurnishingHandles(desk):
            if field != "corner":
                continue
            worldDirection = point(outward.x(), -outward.y())
            assert math.isclose(QtCore.QPointF.dotProduct(worldDirection, east), sign[0] / math.sqrt(2), abs_tol = 1e-6)
            assert math.isclose(QtCore.QPointF.dotProduct(worldDirection, north), sign[1] / math.sqrt(2), abs_tol = 1e-6)
main.close()
print("PASS: corner/edge grid, vertex, midpoint and alignment snapping; priorities, Alt, rotated anchors, group targets and 45-degree corner arrows")
