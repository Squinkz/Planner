"""Ellipse/circle walls, segment wheel, axis orientation and atomic edits."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Counter
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    fontPath = "C:/Windows/Fonts/segoeui.ttf"
    if Path(fontPath).is_file():
        QtGui.QFontDatabase.addApplicationFont(fontPath)
    main = MainWindow()
    main.show()
    app.processEvents()
    viewport = main.viewport
    viewport.ResetView()
    viewport.snapEnabled = False
    viewport.newWallWidth = 120
    viewport.walls, viewport.windows, viewport.furnishings, viewport.labels = [], [], [], []
    point = QtCore.QPointF
    right = QtCore.Qt.MouseButton.RightButton
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    QtTest.QTest.mouseClick(main.wallToolButtons["circle"], QtCore.Qt.MouseButton.LeftButton)
    assert viewport.wallShape == "circle"
    start = viewport.WorldToViewport(point()).toPoint()
    end = viewport.WorldToViewport(point(1000, 600)).toPoint()
    for modifiers in (QtCore.Qt.KeyboardModifier.NoModifier, ctrl, shift, ctrl | shift):
        for count in range(3, 13):
            viewport.walls = []
            viewport.SetSelection([])
            history = len(viewport.undoHistory)
            QtTest.QTest.mousePress(viewport, right, modifiers, start)
            viewport.UpdateInteraction(point(end), modifiers)
            assert viewport.circleSegments == len(viewport.pendingShapeWalls) == 8
            zoom = viewport.zoom
            wheel = QtGui.QWheelEvent(point(end), point(viewport.mapToGlobal(end)), QtCore.QPoint(),
                                      QtCore.QPoint(0, (count - 8) * 120), right, modifiers,
                                      QtCore.Qt.ScrollPhase.NoScrollPhase, False)
            app.sendEvent(viewport, wheel)
            assert viewport.zoom == zoom
            assert viewport.circleSegments == len(viewport.pendingShapeWalls) == count
            center = point() if modifiers & shift else point(500, 500 if modifiers & ctrl else 300)
            radiusX = 1000 if modifiers & shift else 500
            radiusY = radiusX if modifiers & ctrl else (600 if modifiers & shift else 300)
            horizontal = vertical = 0
            lengths = []
            for index, wall in enumerate(viewport.pendingShapeWalls):
                assert wall.secondVertex == viewport.pendingShapeWalls[(index + 1) % count].firstVertex
                offset = wall.firstVertex - center
                assert abs((offset.x() / radiusX) ** 2 + (offset.y() / radiusY) ** 2 - 1) < 1e-10
                delta = wall.secondVertex - wall.firstVertex
                horizontal += abs(delta.y()) < 1e-7
                vertical += abs(delta.x()) < 1e-7
                lengths.append(math.hypot(delta.x(), delta.y()))
            assert horizontal >= (2 if count % 2 == 0 else 1)
            if count % 4 == 0:
                assert vertical >= 2
            if modifiers & ctrl:
                assert max(lengths) - min(lengths) < 1e-7
            viewport.grab()
            QtTest.QTest.mouseRelease(viewport, right, modifiers, end)
            assert len(viewport.walls) == count and len(viewport.undoHistory) == history + 1
            assert all(wall.objectId is not None for wall in viewport.walls)
            viewport.Undo()
            assert not viewport.walls
            viewport.Redo()
            assert len(viewport.walls) == count
    # High-resolution scrolling accumulates, and the minimum is a triangle.
    viewport.walls = []
    viewport.SetSelection([])
    QtTest.QTest.mousePress(viewport, right, pos = start)
    viewport.UpdateInteraction(point(end), QtCore.Qt.KeyboardModifier.NoModifier)
    for delta, expected in ((60, 8), (60, 9), (-2400, 3), (120, 4)):
        wheel = QtGui.QWheelEvent(point(end), point(viewport.mapToGlobal(end)), QtCore.QPoint(),
                                  QtCore.QPoint(0, delta), right, QtCore.Qt.KeyboardModifier.NoModifier,
                                  QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        app.sendEvent(viewport, wheel)
        assert viewport.circleSegments == len(viewport.pendingShapeWalls) == expected
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Escape)
    assert viewport.pendingWall is None and not viewport.pendingShapeWalls and not viewport.walls
    QtTest.QTest.mouseRelease(viewport, right, pos = end)
    # One occupied edge rejects the entire polygon.
    QtTest.QTest.mousePress(viewport, right, pos = start)
    viewport.UpdateInteraction(point(end), QtCore.Qt.KeyboardModifier.NoModifier)
    side = viewport.pendingShapeWalls[0]
    counter = Counter(point(side.firstVertex), point(side.secondVertex), 100)
    viewport.walls = [counter]
    assert not viewport.WallFits(side)
    viewport.CancelInteraction()
    QtTest.QTest.mouseRelease(viewport, right, pos = end)
    QtTest.QTest.mousePress(viewport, right, pos = start)
    viewport.UpdateInteraction(point(end), QtCore.Qt.KeyboardModifier.NoModifier)
    history = len(viewport.undoHistory)
    viewport.grab()
    QtTest.QTest.mouseRelease(viewport, right, pos = end)
    assert viewport.walls == [counter] and len(viewport.undoHistory) == history, (len(viewport.walls), history, len(viewport.undoHistory))
    viewport.walls = []
    Drag(viewport, start, start + QtCore.QPoint(200, 0), button = right)
    assert not viewport.walls and len(viewport.undoHistory) == history
    # A fresh drag resets the count, and modifiers update without mouse motion.
    QtTest.QTest.mousePress(viewport, right, pos = start)
    viewport.UpdateInteraction(point(end), QtCore.Qt.KeyboardModifier.NoModifier)
    assert len(viewport.pendingShapeWalls) == 8
    QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_Control)
    QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_Shift, ctrl)
    center = sum((wall.firstVertex for wall in viewport.pendingShapeWalls), point()) / 8
    assert QtCore.QLineF(center, point()).length() < 1e-7
    assert all(abs(QtCore.QLineF(wall.firstVertex, point()).length() - 1000) < 1e-7 for wall in viewport.pendingShapeWalls)
    viewport.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "circle-wall-preview.png"))
    QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_Shift, ctrl)
    QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_Control)
    viewport.CancelInteraction()
    QtTest.QTest.mouseRelease(viewport, right, pos = end)
    main.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
