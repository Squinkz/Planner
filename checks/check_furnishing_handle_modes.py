"""Body clicks toggle selected furnishing handles; drags and Shift clicks do not."""
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


app = QtWidgets.QApplication([])
main = MainWindow()
main.show()
app.processEvents()
viewport = main.viewport
viewport.snapEnabled = False
desk = Furnishing(viewport.furnishingDefinitions["desk"])
viewport.furnishings = [desk]
center = viewport.WorldToViewport(QtCore.QPointF())
body = center + QtCore.QPointF(20, 0)
press = QtCore.QEvent.Type.MouseButtonPress
release = QtCore.QEvent.Type.MouseButtonRelease
move = QtCore.QEvent.Type.MouseMove
viewport.hoverPosition = center
assert {handle[0] for obj, handles in viewport.VisibleFurnishingHandles() for handle in handles} == {"resize"}

for click, expectedMode in enumerate(("resize", "rotate", "resize", "rotate")):
    Mouse(viewport, press, body)
    Mouse(viewport, release, body)
    visible = viewport.VisibleFurnishingHandles()
    assert len(visible) == 1 and len(visible[0][1]) == (8 if expectedMode == "resize" else 5)
    expectedHandles = {"rotate", "pivot"} if expectedMode == "rotate" else {"resize"}
    assert {handle[0] for handle in visible[0][1]} == expectedHandles
    hidden = next(handle for handle in viewport.FurnishingHandles(desk) if handle[0] not in expectedHandles)
    viewport.hoverPosition = hidden[3]
    hitObject, hitHandle = viewport.HitFurnishingHandle(hidden[3])
    assert hitObject is None or hitHandle[0] == expectedMode
    viewport.hoverPosition = center
    assert not viewport.undoHistory

# Body movement retains rotation mode and still records just the movement.
end = body + QtCore.QPointF(50, 0)
Mouse(viewport, press, body)
Mouse(viewport, move, end)
Mouse(viewport, release, end)
assert viewport.furnishingRotationObject is desk and len(viewport.undoHistory) == 1
viewport.Undo()
assert viewport.furnishingRotationObject is desk

# Shift-click keeps selection and handle mode; Ctrl-click removes it.
shift = QtCore.Qt.KeyboardModifier.ShiftModifier
Mouse(viewport, press, body, shift)
Mouse(viewport, release, body, shift)
assert viewport.SelectionEntries() == [(desk, None)] and viewport.furnishingRotationObject is desk
ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
Mouse(viewport, press, body, ctrl)
Mouse(viewport, release, body, ctrl)
assert not viewport.SelectionEntries() and viewport.furnishingRotationObject is None
Mouse(viewport, press, body)
Mouse(viewport, release, body)
assert viewport.furnishingRotationObject is None
assert {handle[0] for obj, handles in viewport.VisibleFurnishingHandles() for handle in handles} == {"resize"}
main.close()
print("PASS: initial scale, body-click mode toggles, hidden handle hit testing, body drag and Shift selection")
