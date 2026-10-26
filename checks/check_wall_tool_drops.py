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
                        v.grab()  # Use the ordinary joined-wall preview renderer.
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
                assert len(v.walls) == count and len(v.undoHistory) == 1
                assert {id(wall) for wall, index in v.SelectionEntries()} == {id(wall) for wall in v.walls}
                assert all(wall.width == 150 and wall.material == v.newWallMaterial for wall in v.walls)
                worldCenter = v.ViewportToWorld(position)
                for wall in v.walls:
                    length = QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
                    expected = 2 * size * math.sin(math.pi / 8) if shape == "circle" else size
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
