"""Shift duplication preserves wall children and remains one reversible edit."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow, Wall, Window, Door, SlidingDoor, PocketDoor
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    left = QtCore.Qt.MouseButton.LeftButton
    window.snapButton.setChecked(False)
    window.connectedOptions["objects"].setChecked(True)
    wall = Wall(point(-2000, 0), point(2000, 0), 320, .3, .8, "Wood")
    neighbor = Wall(wall.firstVertex, point(-2000, 1000))
    children = [Window(wall, .05, .15), Door(wall, .2, .3, True, True),
                SlidingDoor(wall, .4, .6, True, True), PocketDoor(wall, .7, .9, True)]
    viewport.walls = [wall, neighbor]
    viewport.windows = children[:]
    viewport.EnsureObjectIds()
    start = viewport.WorldToViewport(point(1850, 0)).toPoint()
    end = start + QtCore.QPoint(0, 100)
    before = viewport.CaptureState()
    Drag(viewport, start, end, shift)
    assert len(viewport.walls) == 3 and len(viewport.windows) == 8
    copy = viewport.selectedWall
    assert copy is not wall and isinstance(copy, Wall)
    assert wall.firstVertex == point(-2000, 0) and neighbor.firstVertex == point(-2000, 0)
    assert copy.firstVertex == point(-2000, -500) and copy.secondVertex == point(2000, -500)
    assert (copy.width, copy.firstMiter, copy.secondMiter, copy.material) == (320, .3, .8, "Wood")
    copies = [opening for opening in viewport.windows if opening.parentWall is copy]
    assert len(copies) == 4
    for source, opening in zip(children, copies):
        assert type(source) is type(opening) and source.length == opening.length
        assert source.centerFraction == opening.centerFraction
        if isinstance(source, (Door, SlidingDoor, PocketDoor)):
            assert opening.hingeAtSecond == source.hingeAtSecond
        if isinstance(source, Door):
            assert opening.swingsOutwards == source.swingsOutwards
        if isinstance(source, SlidingDoor):
            assert opening.panelsFlipped == source.panelsFlipped
    assert len({obj.objectId for obj in viewport.walls + viewport.windows}) == 11
    assert len(viewport.undoHistory) == 1
    viewport.Undo()
    assert viewport.CaptureState()[0] == before[0] and viewport.windows == children
    viewport.Redo()
    assert viewport.selectedWall is copy and all(any(obj is opening for obj in viewport.windows) for opening in copies)
    viewport.Undo()
    # Modifier release removes the provisional copy and moves the original.
    QtTest.QTest.mousePress(viewport, left, shift, start)
    viewport.UpdateInteraction(point(end), shift)
    assert len(viewport.walls) == 3
    QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_Shift)
    assert len(viewport.walls) == 2 and viewport.selectedWall is wall
    QtTest.QTest.mouseRelease(viewport, left, pos = end)
    assert wall.firstVertex == point(-2000, -500)
    viewport.Undo()
    assert wall.firstVertex == point(-2000, 0)
    # Shift can be pressed after a move starts; the source and connected
    # neighbors return to their initial positions while the copy follows.
    QtTest.QTest.mousePress(viewport, left, pos = start)
    viewport.UpdateInteraction(point(end), QtCore.Qt.KeyboardModifier.NoModifier)
    assert wall.firstVertex != point(-2000, 0)
    QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_Shift)
    assert len(viewport.walls) == 3 and wall.firstVertex == point(-2000, 0)
    assert neighbor.firstVertex == point(-2000, 0)
    QtTest.QTest.mouseRelease(viewport, left, shift, end)
    viewport.Undo()
    assert viewport.walls == [wall, neighbor] and viewport.windows == children
    # Escape discards copies and returns selection to the original.
    QtTest.QTest.mousePress(viewport, left, shift, start)
    viewport.UpdateInteraction(point(end), shift)
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Escape)
    QtTest.QTest.mouseRelease(viewport, left, pos = end)
    assert viewport.walls == [wall, neighbor] and viewport.windows == children and viewport.selectedWall is wall
    assert wall.firstVertex == point(-2000, 0)
    # Shift on empty canvas creates nothing; clicking without a drag creates nothing.
    Drag(viewport, QtCore.QPoint(220, 200), QtCore.QPoint(420, 200), shift)
    QtTest.QTest.mouseClick(viewport, left, shift, start)
    assert len(viewport.walls) == 2 and len(viewport.windows) == 4
    # Openings duplicate independently into an available gap on the same wall.
    opening = children[0]
    viewport.SetSelection([(opening, None)])
    start = viewport.WorldToViewport((opening.firstVertex + opening.secondVertex) / 2).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(200, 0), shift)
    assert len(viewport.windows) == 5 and viewport.selectedWall is not opening
    assert opening.centerFraction == .1
    viewport.Undo()
    assert len(viewport.windows) == 4
    window.close()
    print("PASS: Shift copies walls and all opening children, properties, IDs, history, modifier release, cancellation and independent openings.")


if __name__ == "__main__":
    Main()
