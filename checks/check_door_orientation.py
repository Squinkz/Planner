"""Verify Ctrl door orientation, position locking, history and drop previews."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Door


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    none = QtCore.Qt.KeyboardModifier.NoModifier
    left = QtCore.Qt.MouseButton.LeftButton
    viewport.snapEnabled = False
    # All quadrants use the door's local axes, including reversed and rotated walls.
    for direction in (point(1, 0), point(-1, 0), point(0, 1), point(.6, .8)):
        wall = Wall(direction * -2000, direction * 2000)
        door = Door(wall, .4, .6)
        viewport.walls = [wall]
        viewport.windows = [door]
        center = (door.firstVertex + door.secondVertex) / 2
        normal = point(-direction.y(), direction.x())
        start = viewport.WorldToViewport(center).toPoint()
        QtTest.QTest.mousePress(viewport, left, pos = start)
        original = (point(door.firstVertex), point(door.secondVertex))
        for along, across in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            cursor = viewport.WorldToViewport(center + direction * (along * 600) + normal * (across * 600))
            viewport.UpdateInteraction(cursor, ctrl)
            assert (door.firstVertex, door.secondVertex) == original
            assert door.hingeAtSecond == (along > 0)
            assert door.swingsOutwards == (across < 0)
        QtTest.QTest.mouseRelease(viewport, left, ctrl, cursor.toPoint())
        assert not viewport.doorOrientationLocked
        viewport.Undo()
        assert not door.hingeAtSecond and not door.swingsOutwards
        viewport.Redo()
        assert door.hingeAtSecond and door.swingsOutwards
    # Lock after translation, then release Ctrl without jumping to the pointer.
    wall = Wall(point(-2500, 0), point(2500, 0))
    door = Door(wall, .4, .6)
    viewport.walls = [wall]
    viewport.windows = [door]
    start = viewport.WorldToViewport(point()).toPoint()
    QtTest.QTest.mousePress(viewport, left, pos = start)
    viewport.UpdateInteraction(point(start) + point(60, 0), none)
    lockedCenter = door.centerFraction
    cursor = point(start) + point(120, -80)
    viewport.UpdateInteraction(cursor, ctrl)
    assert door.centerFraction == lockedCenter
    viewport.UpdateInteraction(cursor, none)
    assert abs(door.centerFraction - lockedCenter) < 1e-10
    viewport.UpdateInteraction(cursor + point(40, 0), none)
    assert door.centerFraction > lockedCenter
    viewport.CancelInteraction()
    assert abs(door.centerFraction - .5) < 1e-10
    assert not door.hingeAtSecond and not door.swingsOutwards
    # Native toolbar drop retains the locked preview and chosen orientation.
    viewport.windows = []
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-door", b"door")
    enter = QtGui.QDragEnterEvent(start, QtCore.Qt.DropAction.CopyAction, mime, left, none)
    QtWidgets.QApplication.sendEvent(viewport, enter)
    move = QtGui.QDragMoveEvent(start, QtCore.Qt.DropAction.CopyAction, mime, left, none)
    QtWidgets.QApplication.sendEvent(viewport, move)
    preview = viewport.windowDropPreview
    cursor = point(start) + point(-100, 80)
    move = QtGui.QDragMoveEvent(cursor.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, left, ctrl)
    QtWidgets.QApplication.sendEvent(viewport, move)
    assert viewport.windowDropPreview is preview
    assert not preview.hingeAtSecond and preview.swingsOutwards
    drop = QtGui.QDropEvent(cursor, QtCore.Qt.DropAction.CopyAction, mime, left, ctrl)
    QtWidgets.QApplication.sendEvent(viewport, drop)
    assert drop.isAccepted() and viewport.windows[0] is preview
    assert abs(preview.centerFraction - .5) < 1e-10
    window.close()
    print("PASS: Ctrl quadrants, rotated walls, locked position, resume, cancel, undo/redo and toolbar drop.")


if __name__ == "__main__":
    Main()
