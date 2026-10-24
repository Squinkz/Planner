"""Group copies, opening constraints, atomic edits and canceled stair movement."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Window, Door, Stair
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.unitsMode = "Adaptive Metric"  # Property edits below are expressed in meters.
    point = QtCore.QPointF
    viewport.snapEnabled = False
    window.connectedOptions["vertices"].setChecked(False)
    left = QtCore.Qt.MouseButton.LeftButton
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    first = Wall(point(-1800, 700), point(1800, 700))
    second = Wall(point(-1800, -700), point(1800, -700))
    door = Door(first, .3, .55)
    opening = Window(second, .3, .55)
    viewport.walls = [first, second]
    viewport.windows = [door, opening]
    viewport.SetSelection([(first, None), (second, None)])
    app.processEvents()
    before = viewport.CaptureState()
    start = viewport.WorldToViewport(point(-1000, 700)).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(80, 50), shift)
    assert len(viewport.walls) == 4 and len(viewport.windows) == 4
    assert first.firstVertex == point(-1800, 700) and second.firstVertex == point(-1800, -700)
    copies = [obj for obj, index in viewport.SelectionEntries()]
    assert len(copies) == 2 and all(obj is not first and obj is not second for obj in copies)
    assert all(sum(child.parentWall is obj for child in viewport.windows) == 1 for obj in copies)
    assert len(viewport.undoHistory) == 1
    viewport.Undo()
    assert viewport.CaptureState()[0] == before[0] and viewport.CaptureState()[3] == before[3]
    assert len(viewport.SelectionEntries()) == 2
    viewport.Redo()
    assert len(viewport.walls) == 4 and len(viewport.SelectionEntries()) == 2
    viewport.Undo()
    # Grabbing an endpoint of a whole-object selection still duplicates the group.
    endpoint = viewport.WorldToViewport(first.firstVertex).toPoint()
    Drag(viewport, endpoint, endpoint + QtCore.QPoint(80, 50), shift)
    assert len(viewport.walls) == 4 and len(viewport.windows) == 4
    assert first.firstVertex == point(-1800, 700) and second.firstVertex == point(-1800, -700)
    assert len(viewport.SelectionEntries()) == 2 and all(index is None for obj, index in viewport.SelectionEntries())
    viewport.Undo()
    # Releasing Shift during a group drag switches back to source translation.
    QtTest.QTest.mousePress(viewport, left, shift, start)
    shifted = start + QtCore.QPoint(80, 0)
    move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(shifted),
                            QtCore.QPointF(viewport.mapToGlobal(shifted)), QtCore.Qt.MouseButton.NoButton, left, shift)
    QtWidgets.QApplication.sendEvent(viewport, move)
    assert len(viewport.walls) == 4
    QtTest.QTest.mouseRelease(viewport, left, QtCore.Qt.KeyboardModifier.NoModifier, shifted)
    assert len(viewport.walls) == 2 and first.firstVertex == point(-1400, 700) and second.firstVertex == point(-1400, -700)
    viewport.Undo()
    # Multiple fixed-wall openings move equally along parallel parent walls.
    viewport.SetSelection([(door, None), (opening, None)])
    app.processEvents()
    oldDoor = point(door.firstVertex)
    oldWindow = point(opening.firstVertex)
    start = viewport.WorldToViewport((door.firstVertex + door.secondVertex) / 2).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(60, 50))
    assert door.firstVertex == oldDoor + point(300, 0) and opening.firstVertex == oldWindow + point(300, 0)
    assert abs(door.length - 900) < .01 and abs(opening.length - 900) < .01
    viewport.Undo()
    # Multiple selected openings duplicate together when grabbed by an endpoint.
    endpoint = viewport.WorldToViewport(door.firstVertex).toPoint()
    Drag(viewport, endpoint, endpoint + QtCore.QPoint(260, 0), shift)
    assert len(viewport.windows) == 4 and len(viewport.walls) == 2
    assert door.firstVertex == oldDoor and opening.firstVertex == oldWindow
    copies = [obj for obj, index in viewport.SelectionEntries()]
    assert len(copies) == 2 and all(obj is not door and obj is not opening for obj in copies)
    for copied, original in zip(copies, (door, opening)):
        assert copied.parentWall is original.parentWall and abs(copied.length - original.length) < .01
        assert QtCore.QLineF(copied.firstVertex, original.firstVertex + point(1300, 0)).length() < .01
    viewport.Undo()
    assert viewport.windows == [door, opening]
    viewport.Redo()
    assert len(viewport.windows) == 4
    viewport.Undo()
    before = viewport.CaptureState()
    Drag(viewport, endpoint, endpoint + QtCore.QPoint(40, 0), shift)
    assert viewport.CaptureState()[0] == before[0] and viewport.CaptureState()[3] == before[3]
    assert len(viewport.windows) == 2
    Drag(viewport, endpoint, endpoint - QtCore.QPoint(200, 0), shift)
    assert len(viewport.windows) == 4
    for copied, original in zip([obj for obj, index in viewport.SelectionEntries()], (door, opening)):
        assert QtCore.QLineF(copied.firstVertex, original.firstVertex - point(1000, 0)).length() < .01
    viewport.Undo()
    # Selecting an opening and one handle must not move that handle twice or resize it.
    viewport.SetSelection([(opening, None), (opening, 0)])
    app.processEvents()
    oldWindow = point(opening.firstVertex)
    start = viewport.WorldToViewport((opening.firstVertex + opening.secondVertex) / 2).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(60, 0))
    assert opening.firstVertex == oldWindow + point(300, 0) and abs(opening.length - 900) < .01
    viewport.Undo()
    # Two same-class doors expose length and apply Flip to both.
    another = Door(second, .4, .65)
    viewport.windows = [door, another]
    viewport.SetSelection([(door, None), (another, None)])
    window.propertyFields["length"].setValue(.7)
    assert abs(door.length - 700) < .01 and abs(another.length - 700) < .01
    window.doorFields["swing"].click()
    assert door.swingsOutwards and another.swingsOutwards
    viewport.Undo()
    assert not door.swingsOutwards and not another.swingsOutwards
    # An impossible shared edit rolls back every member rather than leaving
    # a partially applied property value on the first object that could fit.
    adjacent = Door(first, .7, .9)
    viewport.windows = [door, adjacent]
    viewport.SetSelection([(door, None), (adjacent, None)])
    before = viewport.CaptureState()
    historyCount = len(viewport.undoHistory)
    window.EditProperty("length", 2)
    assert viewport.CaptureState()[3] == before[3] and len(viewport.undoHistory) == historyCount
    # A group stair collision previews the movement and restores every member.
    stair = Stair(point(-1400, 1000), point(1400, 1000), 500)
    other = Stair(point(-1400, 1800), point(1400, 1800), 500)
    obstacle = Wall(point(-3000, 0), point(3000, 0))
    viewport.walls = [stair, other, obstacle]
    viewport.windows = []
    viewport.SetSelection([(stair, None), (other, None)])
    app.processEvents()
    before = viewport.CaptureState()
    start = viewport.WorldToViewport(point(0, 1000)).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(0, 200))
    assert viewport.CaptureState()[0] == before[0] and len(viewport.SelectionEntries()) == 2
    window.close()
    print("PASS: whole-group copies/children, modifier release, fixed-parent openings, bulk door edits and invalid group rollback.")


if __name__ == "__main__":
    Main()
