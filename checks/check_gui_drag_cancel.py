"""Sidebar drags cancel natively and reject queued moves/drops afterward."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall
from planner_app.ui.widgets import FurnishingButton


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    viewport = main.viewport
    point = QtCore.QPointF
    viewport.snapEnabled = False
    viewport.walls = [Wall(point(-1500, 0), point(1500, 0), 120)]
    position = viewport.WorldToViewport(point())
    left, right = QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.RightButton
    action = QtCore.Qt.DropAction.CopyAction
    modifiers = QtCore.Qt.KeyboardModifier.NoModifier
    before = viewport.CaptureState()
    history = len(viewport.undoHistory)
    furnishing = FurnishingButton(viewport.furnishingDefinitions["desk"])
    furnishing.setParent(main)
    buttons = [main.doorButton, main.openDoorwayButton, main.stairButton, main.counterButton,
               main.labelButton, furnishing, *main.wallToolButtons.values()]
    for index, button in enumerate(buttons):
        def ExecDrag(drag, actions):
            assert viewport.guiDragActive and not viewport.guiDragCancelled
            mime = drag.mimeData()
            viewport.dragEnterEvent(QtGui.QDragEnterEvent(position.toPoint(), action, mime, left, modifiers))
            viewport.dragMoveEvent(QtGui.QDragMoveEvent(position.toPoint(), action, mime, left, modifiers))
            viewport.grab()
            if index % 2:
                viewport.dragMoveEvent(QtGui.QDragMoveEvent(position.toPoint(), action, mime, left | right, modifiers))
            else:
                event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonPress, position,
                                         point(viewport.mapToGlobal(position.toPoint())), right, left | right, modifiers)
                app.sendEvent(viewport, event)
            assert viewport.guiDragCancelled
            assert all(preview is None for preview in (viewport.windowDropPreview, viewport.inactiveOpeningPreview,
                                                       viewport.furnishingPreview, viewport.counterPreview, viewport.labelPreview, viewport.pendingWall))
            assert not viewport.pendingShapeWalls
            move = QtGui.QDragMoveEvent(position.toPoint(), action, mime, left, modifiers)
            viewport.dragMoveEvent(move)
            drop = QtGui.QDropEvent(position, action, mime, left, modifiers)
            viewport.dropEvent(drop)
            assert not move.isAccepted() and not drop.isAccepted()
            return QtCore.Qt.DropAction.IgnoreAction

        button.pressPosition = QtCore.QPoint()
        move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, point(30, 30), point(30, 30),
                                QtCore.Qt.MouseButton.NoButton, left, modifiers)
        with patch.object(QtGui.QDrag, "exec", ExecDrag), patch.object(QtGui.QDrag, "cancel") as cancel:
            button.mouseMoveEvent(move)
            assert cancel.call_count == 1
        assert not viewport.guiDragActive and viewport.guiDragKind is None
        assert viewport.CaptureState() == before and len(viewport.undoHistory) == history
        assert not viewport.objectContextMenu.isVisible()
    # Starting a fresh drag resets cancellation and permits normal placement.
    def PlaceLabel(drag, actions):
        assert not viewport.guiDragCancelled
        mime = drag.mimeData()
        viewport.dragEnterEvent(QtGui.QDragEnterEvent(position.toPoint(), action, mime, left, modifiers))
        viewport.dragMoveEvent(QtGui.QDragMoveEvent(position.toPoint(), action, mime, left, modifiers))
        drop = QtGui.QDropEvent(position, action, mime, left, modifiers)
        viewport.dropEvent(drop)
        assert drop.isAccepted()
        return action

    main.labelButton.pressPosition = QtCore.QPoint()
    with patch.object(QtGui.QDrag, "exec", PlaceLabel):
        main.labelButton.mouseMoveEvent(move)
    assert len(viewport.labels) == 1 and len(viewport.undoHistory) == history + 1
    main.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
