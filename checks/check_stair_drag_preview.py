"""Invalid stair body/vertex/duplicate drags preview freely and commit on release."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Stair, Wall


def Move(viewport, position, modifiers = QtCore.Qt.KeyboardModifier.NoModifier):
    screen = viewport.WorldToViewport(position).toPoint()
    event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(screen),
                             QtCore.QPointF(viewport.mapToGlobal(screen)), QtCore.Qt.MouseButton.NoButton,
                             QtCore.Qt.MouseButton.LeftButton, modifiers)
    QtWidgets.QApplication.sendEvent(viewport, event)
    return screen


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    viewport.snapEnabled = False
    stair = Stair(point(-1500, 1000), point(1500, 1000), 500)
    wall = Wall(point(-3000, 0), point(3000, 0), 240)
    viewport.walls = [stair, wall]
    viewport.selectedWall = stair
    window.RefreshProperties()
    app.processEvents()
    before = viewport.CaptureState()
    left = QtCore.Qt.MouseButton.LeftButton
    QtTest.QTest.mousePress(viewport, left, pos = viewport.WorldToViewport(point(0, 1000)).toPoint())
    end = Move(viewport, point(0, 0))
    assert stair.firstVertex.y() == 0 and not viewport.OpeningsValid()
    image = viewport.grab().toImage()
    arrowPixel = viewport.WorldToViewport(point(0, 0)).toPoint()
    color = image.pixelColor(arrowPixel)
    # Subpixel coverage changes with line weights; invalid stairs remain neutral
    # gray rather than acquiring the red error or blue selection color.
    channels = color.getRgb()[:3]
    assert min(channels) > 40 and max(channels) - min(channels) < 25, color.name()
    QtTest.QTest.mouseRelease(viewport, left, pos = end)
    assert viewport.CaptureState()[0] == before[0] and not viewport.undoHistory
    # Cross the invalid wall position and finish valid on the other side.
    QtTest.QTest.mousePress(viewport, left, pos = viewport.WorldToViewport(point(0, 1000)).toPoint())
    Move(viewport, point(0, 0))
    end = Move(viewport, point(0, -1000))
    assert stair.firstVertex.y() == -1000 and viewport.OpeningsValid()
    QtTest.QTest.mouseRelease(viewport, left, pos = end)
    assert len(viewport.undoHistory) == 1
    viewport.Undo()
    assert stair.firstVertex.y() == 1000
    # An endpoint also follows the cursor into a collision, then rolls back.
    viewport.selectedVertex = 0
    QtTest.QTest.mousePress(viewport, left, pos = viewport.WorldToViewport(stair.firstVertex).toPoint())
    end = Move(viewport, point(-1500, -200))
    assert stair.firstVertex.y() == -200 and not viewport.OpeningsValid()
    QtTest.QTest.mouseRelease(viewport, left, pos = end)
    assert viewport.CaptureState()[0] == before[0] and not viewport.undoHistory
    # Invalid duplication leaves the source untouched and removes the copy.
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    QtTest.QTest.mousePress(viewport, left, shift, viewport.WorldToViewport(point(0, 1000)).toPoint())
    end = Move(viewport, point(0, 0), shift)
    assert len(viewport.walls) == 3 and stair.firstVertex.y() == 1000
    QtTest.QTest.mouseRelease(viewport, left, shift, end)
    assert len(viewport.walls) == 2 and not viewport.undoHistory
    child = Stair(point(-1500, 1000), point(-1500, 2200), 500)
    viewport.walls.append(child)
    viewport.selectedWall, viewport.selectedVertex = stair, 0
    before = viewport.CaptureState()
    QtTest.QTest.mousePress(viewport, left, pos = viewport.WorldToViewport(stair.firstVertex).toPoint())
    end = Move(viewport, point(-1500, -200))
    assert child.firstVertex == stair.firstVertex and child.firstVertex.y() == -200
    QtTest.QTest.mouseRelease(viewport, left, pos = end)
    assert viewport.CaptureState()[0] == before[0] and not viewport.undoHistory
    QtTest.QTest.mousePress(viewport, left, pos = viewport.WorldToViewport(stair.firstVertex).toPoint())
    Move(viewport, point(-1500, -200))
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Escape)
    assert viewport.CaptureState()[0] == before[0] and viewport.dragStart is None
    # Joined stairs touching two wall faces remain valid despite sub-millimeter
    # endpoint reconstruction differences, while genuine penetration is invalid.
    horizontal = Stair(point(-2300.37, 1620.19), point(180.37, 1620.19))
    vertical = Stair(point(180.37, 1620.19), point(180.37, -1500.19))
    top = Wall(point(-3000, 2240), point(800, 2240), 240)
    right = Wall(point(800, -2100), point(800, 2240), 240)
    viewport.walls = [horizontal, vertical, top, right]
    assert viewport.OpeningsValid()
    vertical.firstVertex += point(3, 0)
    vertical.secondVertex += point(3, 0)
    assert not viewport.OpeningsValid()
    window.close()
    print("PASS: invalid body/vertex previews, release rollback, crossing collisions, gray rendering and duplicate cancellation.")


if __name__ == "__main__":
    Main()
