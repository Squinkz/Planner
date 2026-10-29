"""Wall-tool palette drags place fixed-size, snapping, undoable constructions."""
import math
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Counter
from planner_app.placement_sizing import NominalPlacementSize
from planner_app.viewport import rendering


class ObservedTips(dict):
    def __getitem__(self, key):
        self.drawn.append(key)
        return super().__getitem__(key)


def Main():
    p = QtCore.QPointF
    left = QtCore.Qt.MouseButton.LeftButton
    copy = QtCore.Qt.DropAction.CopyAction
    noMods = QtCore.Qt.KeyboardModifier.NoModifier
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.snapEnabled = False
        v.newWallWidth = 150
        position = v.DrawingRect().center()
        for mode in ("Millimeters", "Inches"):
            v.unitsMode = mode
            size = NominalPlacementSize(1000, mode)
            for shape, count in (("line", 1), ("square", 4), ("circle", 8)):
                InstallScene(main, [])
                button = main.wallToolButtons[shape]
                # Clicks still select a drawing shape without placing walls.
                QtTest.QTest.mouseClick(button, left)
                assert v.wallShape == shape and not v.walls
                with patch("planner_app.ui.widgets.QtGui.QDrag") as dragClass:
                    drag = dragClass.return_value

                    def Drop(action):
                        assert action == copy and v.guiDragActive and v.guiDragKind == "wall-" + shape
                        mime = drag.setMimeData.call_args.args[0]
                        assert mime.hasFormat("application/x-planner-wall-" + shape)
                        enter = QtGui.QDragEnterEvent(position.toPoint(), copy, mime, left, noMods)
                        v.dragEnterEvent(enter)
                        assert enter.isAccepted()
                        move = QtGui.QDragMoveEvent(position.toPoint(), copy, mime, left, noMods)
                        v.dragMoveEvent(move)
                        assert move.isAccepted() and v.pendingWall is not None
                        preview = v.pendingShapeWalls or [v.pendingWall]
                        assert len(preview) == count
                        assert not v.walls
                        # Modifier refreshes must translate the palette preview,
                        # never resize it as though it were a drawn wall.
                        v.UpdateInteraction(position + p(80, 60), QtCore.Qt.KeyboardModifier.ControlModifier)
                        assert len(v.pendingShapeWalls or [v.pendingWall]) == count
                        if shape == "circle":
                            zoom = v.zoom
                            # Exercise native source delivery, partial wheel ticks,
                            # trackpad deltas and reverse scrolling without zooming.
                            for angle, pixels, expectedCount in ((60, 0, 8), (60, 0, 9), (0, 4, 10), (-120, 0, 9),
                                                                 (-2400, 0, 3), (720, 0, 9)):
                                wheel = QtGui.QWheelEvent(p(button.rect().center()), p(button.mapToGlobal(button.rect().center())),
                                    QtCore.QPoint(0, pixels), QtCore.QPoint(0, angle), left, noMods,
                                    QtCore.Qt.ScrollPhase.NoScrollPhase, False)
                                QtWidgets.QApplication.sendEvent(button, wheel)
                                assert wheel.isAccepted() and v.circleSegments == expectedCount
                                assert len(v.pendingShapeWalls) == expectedCount and v.zoom == zoom
                        tips = ObservedTips(rendering.toolTipRows)
                        tips.drawn = []
                        with patch.object(rendering, "toolTipRows", tips):
                            v.grab()  # Use the ordinary joined-wall preview renderer.
                        assert tips.drawn == (["segments", "cancelMove"] if shape == "circle" else ["cancelMove"]), tips.drawn
                        drop = QtGui.QDropEvent(position, copy, mime, left, noMods)
                        v.dropEvent(drop)
                        assert drop.isAccepted()
                        return copy

                    drag.exec.side_effect = Drop
                    center = p(button.rect().center())
                    QtTest.QTest.mousePress(button, left, pos = center.toPoint())
                    move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, center + p(30, 0),
                                            QtCore.Qt.MouseButton.NoButton, left, noMods)
                    button.mouseMoveEvent(move)
                    QtTest.QTest.mouseRelease(button, left, pos = center.toPoint())
                    drag.exec.assert_called_once()
                assert not v.guiDragActive and v.pendingWall is None and not v.pendingShapeWalls
                count = 9 if shape == "circle" else count
                assert len(v.walls) == count and len(v.undoHistory) == 1
                assert {id(wall) for wall, index in v.SelectionEntries()} == {id(wall) for wall in v.walls}
                assert all(wall.width == 150 and wall.material == v.newWallMaterial for wall in v.walls)
                worldCenter = v.ViewportToWorld(position)
                for wall in v.walls:
                    length = QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
                    expected = 2 * size * math.sin(math.pi / count) if shape == "circle" else size
                    assert abs(length - expected) < 1e-7
                    if shape == "circle":
                        assert abs(QtCore.QLineF(worldCenter, wall.firstVertex).length() - size) < 1e-7
                if count > 1:
                    assert all(wall.secondVertex == v.walls[(index + 1) % count].firstVertex for index, wall in enumerate(v.walls))
                v.Undo()
                assert not v.walls
                v.Redo()
                assert len(v.walls) == count
        # All shapes reject obstructed placements and drops outside the canvas.
        for shape in ("line", "square", "circle"):
            center = v.ViewportToWorld(position)
            blocker = Counter(center - p(2500, 0), center + p(2500, 0), width = 5000)
            InstallScene(main, [blocker])
            mime = QtCore.QMimeData()
            mime.setData("application/x-planner-wall-" + shape, shape.encode())
            v.guiDragActive, v.guiDragKind = True, "wall-" + shape
            move = QtGui.QDragMoveEvent(position.toPoint(), copy, mime, left, noMods)
            v.dragMoveEvent(move)
            previews = v.pendingShapeWalls or [v.pendingWall]
            assert any(not v.WallFits(wall) for wall in previews)
            v.grab()
            v.dragLeaveEvent(QtGui.QDragLeaveEvent())
            assert v.pendingWall is None and not v.pendingShapeWalls
            for target in (position, p(-50, -50)):
                drop = QtGui.QDropEvent(target, copy, mime, left, noMods)
                v.dropEvent(drop)
                assert not drop.isAccepted() and v.walls == [blocker] and not v.undoHistory
            v.guiDragCancelled = True
            drop = QtGui.QDropEvent(position, copy, mime, left, noMods)
            v.dropEvent(drop)
            assert not drop.isAccepted() and v.walls == [blocker]
            v.guiDragCancelled, v.guiDragActive, v.guiDragKind = False, False, None
        # Snapping translates the shape without distorting the one-meter size.
        InstallScene(main, [])
        v.unitsMode = "Millimeters"
        v.snapEnabled = True
        v.circleSegments = 8
        for shape in ("line", "square", "circle"):
            walls = v.FindWallToolPlacement(position + p(17, 11), shape, noMods)
            expected = 2000 * math.sin(math.pi / 8) if shape == "circle" else 1000
            assert all(abs(QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() - expected) < 1e-7 for wall in walls)
        # Lost mouse grabs cannot leave a wall palette button armed.
        for button in main.wallToolButtons.values():
            QtTest.QTest.mousePress(button, left, pos = button.rect().center())
            QtWidgets.QApplication.sendEvent(button, QtCore.QEvent(QtCore.QEvent.Type.UngrabMouse))
            assert button.pressPosition is None and not button.isDown()
            QtTest.QTest.mouseRelease(button, left, pos = button.rect().center())
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        enter = QtGui.QDragEnterEvent(position.toPoint(), copy, mime, left, noMods)
        v.dragEnterEvent(enter)
        assert not enter.isAccepted()
    print("PASS: native wall tool drags, click selection, sizes, units, previews, collision/cancel/outside rejection, snapping and undo/redo")


if __name__ == "__main__":
    Main()
