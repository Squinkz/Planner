"""Exercise Stacker's copied submenu controller through real pointer events."""
import os, sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall


def Move(widget, local = None):
    local = widget.rect().center() if local is None else local
    QtGui.QCursor.setPos(widget.mapToGlobal(local))
    QtTest.QTest.mouseMove(widget, local)
    QtWidgets.QApplication.processEvents()
    QtTest.QTest.qWait(35)


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    p = QtCore.QPointF
    wall = Wall(p(-1000, 0), p(1000, 0))
    v.walls = [wall]
    position = v.WorldToViewport(p())
    v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
    root = v.objectContextMenu
    controller = root.materialController
    parent = controller.parentButton
    assert controller.childMenu is None
    assert controller.leaveParentTimer.interval() == 80
    assert controller.leaveChildTimer.interval() == 500
    assert controller.pointerWatchTimer.interval() == 25
    Move(parent)
    child = controller.childMenu
    assert child is not None and child.isVisible() and root.isVisible()
    assert parent.isChecked()
    # Moving into the child keeps it open; moving to another root row closes it.
    Move(child)
    assert controller.childMenu is child and child.isVisible()
    copy = next(action.defaultWidget() for action in root.actions()
                if not action.isSeparator() and action.defaultWidget().accessibleName() == "Copy")
    Move(copy)
    QtTest.QTest.qWait(550)
    assert controller.childMenu is None and root.isVisible(), (controller.childMenu, root.isVisible(), QtGui.QCursor.pos(), controller.PointerInWidget(parent), controller.PointerInWidget(controller.childMenu))
    assert not parent.isChecked() and parent.property("forceIdle")
    Move(parent)
    assert controller.childMenu is not None and controller.childMenu.isVisible()
    # Escape hides both menus and stops timers.
    QtTest.QTest.keyClick(root, QtCore.Qt.Key.Key_Escape)
    app.processEvents()
    assert not root.isVisible() and controller.childMenu is None
    assert not controller.pointerWatchTimer.isActive()
    # The same controller clamps the child to the monitor and flips it left.
    screen = main.screen().availableGeometry()
    v.ShowObjectContextMenu(position, screen.bottomRight() - QtCore.QPoint(5, 5))
    controller = root.materialController
    Move(controller.parentButton)
    child = controller.childMenu
    assert child is not None and child.isVisible()
    childRect = QtCore.QRect(child.pos(), child.size())
    assert screen.contains(childRect)
    parentLeft = controller.parentButton.mapToGlobal(QtCore.QPoint()).x()
    assert childRect.right() < parentLeft
    # Leaving both menus dismisses the child, without a stale highlighted row.
    Move(v, QtCore.QPoint(50, 50))
    assert controller.childMenu is None and not controller.parentButton.isChecked()
    root.hide()
    main.close()
    print("PASS: hover-open, parent-to-child travel, sibling/leave closing, Escape, timer cleanup and monitor-edge placement.")


if __name__ == "__main__":
    Main()
