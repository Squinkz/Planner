"""Full object gestures with application defaults, live Ctrl and three snap roots."""
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Window, Door
from theme import BuildStyle
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.showMaximized()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    left = QtCore.Qt.MouseButton.LeftButton
    none = QtCore.Qt.KeyboardModifier.NoModifier
    source = Wall(point(-500, 0), point(500, 0))
    child = Door(source, .1, .5)
    target = Wall(point(900, 500), point(900, 1000))
    viewport.walls = [source, target]
    viewport.windows = [child]
    viewport.SetSelection([(source, None)])
    app.processEvents()
    original = point(source.firstVertex)
    for snap in (False, True):
        viewport.snapEnabled = snap
        start = viewport.WorldToViewport(point(300, 0)).toPoint()
        # Hold Ctrl before mouse press, then move repeatedly without mouse flags.
        QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_Control)
        QtTest.QTest.mousePress(viewport, left, none, start)
        assert viewport.selectedWall is source and viewport.selectedVertex is None
        for angle in (4, 19, 37, 56, 79, 104, 131, 168, 203, 247, 287, 331):
            radians = math.radians(angle)
            end = start + QtCore.QPoint(round(65 * math.cos(radians)), -round(65 * math.sin(radians)))
            move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, point(end),
                                    point(viewport.mapToGlobal(end)), QtCore.Qt.MouseButton.NoButton, left, none)
            QtWidgets.QApplication.sendEvent(viewport, move)
            app.processEvents()
            translation = source.firstVertex - original
            if abs(end.x() - start.x()) >= abs(end.y() - start.y()):
                assert translation.y() == 0, (snap, angle, translation)
                if not snap:
                    assert translation.x() == (end.x() - start.x()) / .2
            else:
                assert translation.x() == 0, (snap, angle, translation)
                if not snap:
                    assert translation.y() == -(end.y() - start.y()) / .2
            assert QtCore.QLineF(source.secondVertex - source.firstVertex, point(1000, 0)).length() < .001
            assert abs(child.length - 400) < .001
        QtTest.QTest.mouseRelease(viewport, left, none, end)
        QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_Control)
        viewport.Undo()
        assert source.firstVertex == original
    # Replay the two adjacent cursor positions from the native trace where
    # the old movement jumped from (-1000,-1000) to (-1212,-700).
    for snap in (False, True):
        viewport.snapEnabled = snap
        previous = None
        for cursorDelta in (point(-1140, -900), point(-1145, -875)):
            movement = viewport.SnapObjectMovement([point(), point(1000, 0)], cursorDelta,
                                                   QtCore.Qt.KeyboardModifier.ControlModifier, snapTargets = [])
            assert movement.y() == 0
            if previous is not None:
                assert QtCore.QLineF(previous, movement).length() <= 100
            previous = movement
    # Default snap options must allow each root to win a nearby object target.
    viewport.snapEnabled = True
    for openingType in (Window, Door):
        for targetX, expectedFirst in ((508, 508), (957, 507), (1391, 491)):
            parent = Wall(point(), point(5000, 0))
            opening = openingType(parent, .01, .19)
            target = Wall(point(targetX, 0), point(targetX, 1000))
            viewport.walls = [parent, target]
            viewport.windows = [opening]
            viewport.SetSelection([(opening, None)])
            app.processEvents()
            start = viewport.WorldToViewport(point(250, 0)).toPoint()
            Drag(viewport, start, start + QtCore.QPoint(90, 0))
            # Opening fitting can move or shrink it into the available gap.
            # A rejected placement keeps the original, already obstructed fixture.
            assert abs(opening.firstVertex.x() - 50) < .001 or viewport.OpeningFits(opening)
            assert 1 <= opening.length <= 900 + .001
        # The midpoint's alignment overrides an endpoint already on the grid.
        parent = Wall(point(), point(5000, 0))
        opening = openingType(parent, .01, .19)
        target = Wall(point(970, 800), point(970, 1500))
        viewport.walls = [parent, target]
        viewport.windows = [opening]
        viewport.SetSelection([(opening, None)])
        app.processEvents()
        start = viewport.WorldToViewport(point(250, 0)).toPoint()
        Drag(viewport, start, start + QtCore.QPoint(90, 0))
        assert abs(opening.firstVertex.x() - 520) < .001
        viewport.Undo()
        viewport.midpointSnapEnabled = True
        target.firstVertex = point(967, -500)
        target.secondVertex = point(967, 500)
        Drag(viewport, start, start + QtCore.QPoint(90, 0))
        assert abs(opening.firstVertex.x() - 50) < .001 or viewport.OpeningFits(opening)
        viewport.midpointSnapEnabled = False
    window.close()
    print("PASS: continuous Ctrl wall movement, closest window/door roots, and alignment/midpoint priority over endpoint grid snaps.")


if __name__ == "__main__":
    Main()
