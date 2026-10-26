"""Shift vertex extrusion inherits properties and preserves its source/history."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets, QtTest
from planner import MainWindow, Wall, Counter, Stair, Arrow, MeasurementGuide, Door, CasementWindow
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    none = QtCore.Qt.KeyboardModifier.NoModifier
    left = QtCore.Qt.MouseButton.LeftButton
    v.snapEnabled = False
    for cls in (Wall, Counter, Stair, Arrow, MeasurementGuide):
        for index in (0, 1):
            source = cls(point(-1000, 0), point(1000, 0))
            source.material = "Brick"
            if isinstance(source, Arrow):
                source.solidTip, source.tipSize, source.intensity = False, 120, .5
            if isinstance(source, Stair):
                source.directionReversed, source.autosize, source.manualStepCount = True, False, 9
            v.walls, v.windows = [source], []
            v.SetSelection([(source, index)])
            original = (point(source.firstVertex), point(source.secondVertex))
            anchor = original[index]
            target = anchor + point(0, -1200)
            historyCount = len(v.undoHistory)
            Drag(v, v.WorldToViewport(anchor).toPoint(), v.WorldToViewport(target).toPoint(), shift)
            assert len(v.walls) == 2, (cls.__name__, index)
            created = v.walls[-1]
            assert type(created) is cls and created.objectId != source.objectId
            assert source.firstVertex == original[0] and source.secondVertex == original[1]
            # Directed runs keep the dragged endpoint's identity so extruding
            # from the back does not reverse an arrow or staircase.
            draggedIndex = index if isinstance(source, (Arrow, Stair)) else 1
            createdVertices = (created.firstVertex, created.secondVertex)
            assert createdVertices[1 - draggedIndex] == anchor
            assert QtCore.QLineF(createdVertices[draggedIndex], target).length() < 1
            assert created.width == source.width and created.material == source.material
            if isinstance(source, Arrow):
                assert (created.solidTip, created.tipSize, created.intensity) == (False, 120, .5)
            if isinstance(source, Stair):
                assert (created.directionReversed, created.autosize, created.manualStepCount) == (True, False, 9)
            assert len(v.undoHistory) == historyCount + 1
            v.Undo()
            assert len(v.walls) == 1 and source.firstVertex == original[0] and source.secondVertex == original[1]
            v.Redo()
            assert v.walls[-1] is created
    # Shift can be pressed/released during the gesture; Right Mouse cancels.
    source = Counter(point(-1000, 0), point(1000, 0))
    v.walls, v.windows = [source], []
    v.SetSelection([(source, 0)])
    start = v.WorldToViewport(source.firstVertex).toPoint()
    end = start + QtCore.QPoint(0, 120)
    QtTest.QTest.mousePress(v, left, none, start)
    v.UpdateInteraction(QtCore.QPointF(end), none)
    assert source.firstVertex != point(-1000, 0)
    v.UpdateInteraction(QtCore.QPointF(end), shift)
    assert len(v.walls) == 2 and source.firstVertex == point(-1000, 0)
    v.UpdateInteraction(QtCore.QPointF(end), none)
    assert len(v.walls) == 1 and source.firstVertex != point(-1000, 0)
    v.UpdateInteraction(QtCore.QPointF(end), shift)
    QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.RightButton, none, end)
    assert len(v.walls) == 1 and source.firstVertex == point(-1000, 0)
    QtTest.QTest.mouseRelease(v, left, none, end)
    # Attached opening points resize from center instead of extruding copies.
    for cls in (Door, CasementWindow):
        for index in (0, 1):
            wall = Wall(point(-2500, 0), point(2500, 0))
            opening = cls(wall, .4, .6)
            opening.hingeAtSecond = True
            opening.swingsOutwards = True
            opening.measurementFlipped = True
            v.walls, v.windows = [wall], [opening]
            v.SetSelection([(opening, index)])
            anchor = point(opening.firstVertex if index == 0 else opening.secondVertex)
            target = anchor + point(-800 if index == 0 else 800, 0)
            Drag(v, v.WorldToViewport(anchor).toPoint(), v.WorldToViewport(target).toPoint(), shift)
            assert v.windows == [opening], (cls.__name__, index)
            assert opening.hingeAtSecond and opening.swingsOutwards and opening.measurementFlipped
            assert abs(opening.length - 2600) < 1
            assert opening.centerFraction == .5
    main.close()


if __name__ == "__main__":
    Main()
