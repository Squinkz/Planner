"""Rectangle wall drawing, modifier changes, atomic validation and history."""
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
    point = QtCore.QPointF
    right = QtCore.Qt.MouseButton.RightButton
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    QtTest.QTest.mouseClick(main.wallToolButtons["square"], QtCore.Qt.MouseButton.LeftButton)
    assert viewport.wallShape == "square"
    start = viewport.WorldToViewport(point()).toPoint()
    for modifiers in (QtCore.Qt.KeyboardModifier.NoModifier, ctrl, shift, ctrl | shift):
        for x, y in ((1000, 600), (-1000, 600), (1000, -600), (-1000, -600)):
            viewport.walls, viewport.windows, viewport.furnishings, viewport.labels = [], [], [], []
            viewport.SetSelection([])
            end = viewport.WorldToViewport(point(x, y)).toPoint()
            history = len(viewport.undoHistory)
            Drag(viewport, start, end, modifiers, right)
            assert len(viewport.walls) == 4 and len(viewport.undoHistory) == history + 1
            corners = [wall.firstVertex for wall in viewport.walls]
            for index, wall in enumerate(viewport.walls):
                assert wall.secondVertex == corners[(index + 1) % 4]
                assert wall.firstVertex.x() == wall.secondVertex.x() or wall.firstVertex.y() == wall.secondVertex.y()
                assert wall.width == viewport.newWallWidth and wall.material == viewport.newWallMaterial
                assert wall.objectId is not None
            width = max(vertex.x() for vertex in corners) - min(vertex.x() for vertex in corners)
            length = max(vertex.y() for vertex in corners) - min(vertex.y() for vertex in corners)
            assert width == (2000 if modifiers & shift else 1000)
            assert length == ((2000 if modifiers & shift else 1000) if modifiers & ctrl else (1200 if modifiers & shift else 600))
            if modifiers & shift:
                assert sum((vertex.x() for vertex in corners)) == sum((vertex.y() for vertex in corners)) == 0
            else:
                assert corners[0] == point()
            image = viewport.grab()
            assert not image.isNull()
            viewport.Undo()
            assert not viewport.walls
            viewport.Redo()
            assert len(viewport.walls) == 4
    # Modifier keys update the existing preview without a mouse move.
    viewport.walls = []
    viewport.SetSelection([])
    end = viewport.WorldToViewport(point(1000, 600)).toPoint()
    QtTest.QTest.mousePress(viewport, right, pos = start)
    viewport.UpdateInteraction(point(end), QtCore.Qt.KeyboardModifier.NoModifier)
    assert len(viewport.pendingShapeWalls) == 4
    QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_Control)
    assert viewport.pendingShapeWalls[1].secondVertex == point(1000, 1000)
    QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_Control)
    assert viewport.pendingShapeWalls[1].secondVertex == point(1000, 600)
    QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_Shift)
    assert viewport.pendingShapeWalls[0].firstVertex == point(-1000, -600)
    QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_Shift)
    viewport.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "rectangle-wall-preview.png"))
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Escape)
    assert viewport.pendingWall is None and not viewport.pendingShapeWalls and not viewport.walls
    QtTest.QTest.mouseRelease(viewport, right, pos = end)
    # One blocked side rejects all four walls; a flat rectangle is rejected too.
    counter = Counter(point(700, 600), point(1100, 600), 100)
    viewport.walls = [counter]
    history = len(viewport.undoHistory)
    Drag(viewport, start, end, button = right)
    assert viewport.walls == [counter] and len(viewport.undoHistory) == history
    viewport.walls = []
    Drag(viewport, start, start + QtCore.QPoint(200, 0), button = right)
    assert not viewport.walls and len(viewport.undoHistory) == history
    QtTest.QTest.mouseClick(viewport, right, pos = start)
    assert not viewport.walls
    viewport.objectContextMenu.hide()
    # Grid snapping remains available; switching back to line creates one wall.
    viewport.snapEnabled = viewport.gridSnapEnabled = True
    viewport.vertexSnapEnabled = viewport.midpointSnapEnabled = viewport.alignmentSnapEnabled = False
    Drag(viewport, start, end + QtCore.QPoint(3, 3), button = right)
    assert len(viewport.walls) == 4
    assert viewport.walls[1].secondVertex == point(1000, 600)
    viewport.walls = []
    QtTest.QTest.mouseClick(main.wallToolButtons["line"], QtCore.Qt.MouseButton.LeftButton)
    Drag(viewport, start, end, button = right)
    assert len(viewport.walls) == 1
    main.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
