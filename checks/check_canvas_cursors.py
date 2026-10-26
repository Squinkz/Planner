"""Canvas hover/drag, oriented resize and rotation cursors; enabled button feedback."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall
from furnishings import Furnishing
from planner_app.ui.widgets import FurnishingButton, WindowButton
from planner_app.graphics.cursors import RotationCursor


def Mouse(viewport, kind, position, button = QtCore.Qt.MouseButton.NoButton, buttons = QtCore.Qt.MouseButton.NoButton):
    event = QtGui.QMouseEvent(kind, position, QtCore.QPointF(viewport.mapToGlobal(position.toPoint())), button, buttons,
                             QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, event)
    QtWidgets.QApplication.processEvents()


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.snapEnabled = False
    wall = Wall(QtCore.QPointF(-500, 0), QtCore.QPointF(500, 0), 120)
    v.walls = [wall]
    v.windows, v.furnishings, v.labels = [], [], []
    shape = QtCore.Qt.CursorShape
    move = QtCore.QEvent.Type.MouseMove
    press = QtCore.QEvent.Type.MouseButtonPress
    release = QtCore.QEvent.Type.MouseButtonRelease
    left = QtCore.Qt.MouseButton.LeftButton
    right = QtCore.Qt.MouseButton.RightButton
    center = v.WorldToViewport(QtCore.QPointF())
    Mouse(v, move, center)
    assert v.cursor().shape() == shape.SizeAllCursor
    vertex = v.WorldToViewport(wall.firstVertex)
    Mouse(v, move, vertex)
    assert v.cursor().shape() == shape.SizeAllCursor
    Mouse(v, press, vertex, left, left)
    Mouse(v, move, vertex + QtCore.QPointF(-30, 20), buttons = left)
    assert v.cursor().shape() == shape.SizeAllCursor
    Mouse(v, press, vertex + QtCore.QPointF(-30, 20), right, left | right)
    assert v.dragStart is None
    Mouse(v, move, center + QtCore.QPointF(200, -170))
    assert v.cursor().shape() == shape.ArrowCursor
    v.walls = []
    desk = Furnishing(v.furnishingDefinitions["desk"])
    v.furnishings = [desk]
    v.SetSelection([(desk, None)])
    Mouse(v, move, center)
    assert v.cursor().shape() == shape.SizeAllCursor
    for angle, widthCursor in ((0, shape.SizeHorCursor), (45, shape.SizeBDiagCursor), (90, shape.SizeVerCursor)):
        main.EditProperty("angle", angle)
        for handle in v.FurnishingHandles(desk):
            if handle[0] != "resize":
                continue
            Mouse(v, move, handle[3])
            assert v.cursor().shape() in (shape.SizeHorCursor, shape.SizeVerCursor, shape.SizeFDiagCursor, shape.SizeBDiagCursor)
            if handle[1] == "width":
                assert v.cursor().shape() == widthCursor
    main.EditProperty("angle", 0)
    v.furnishingRotationObject = desk
    Mouse(v, move, center)
    assert v.cursor().shape() == shape.SizeAllCursor
    other = Furnishing(desk.definition, QtCore.QPointF(-1500, 0))
    v.furnishings.append(other)
    v.SetSelection([(desk, None), (other, None)])
    v.furnishingRotationObject = desk
    Mouse(v, move, v.WorldToViewport((other.firstVertex + other.secondVertex) / 2))
    assert v.cursor().shape() == shape.SizeAllCursor
    v.SetSelection([(desk, None)])
    v.furnishingRotationObject = desk
    handle = next(handle for handle in v.FurnishingHandles(desk) if handle[0] == "rotate")
    Mouse(v, move, handle[3])
    assert v.cursor().shape() == shape.BitmapCursor and not v.cursor().pixmap().isNull()
    Mouse(v, press, handle[3], left, left)
    Mouse(v, move, handle[3] + QtCore.QPointF(0, 30), buttons = left)
    assert v.cursor().shape() == shape.BitmapCursor
    Mouse(v, press, handle[3] + QtCore.QPointF(0, 30), right, left | right)
    assert v.furnishingHandleDrag is None
    v.furnishingRotationObject = None
    handle = next(handle for handle in v.FurnishingHandles(desk) if handle[0] == "resize" and handle[1] == "width")
    Mouse(v, move, handle[3])
    Mouse(v, press, handle[3], left, left)
    Mouse(v, move, handle[3] + handle[4] * 35, buttons = left)
    assert v.cursor().shape() == shape.SizeHorCursor
    Mouse(v, release, handle[3] + handle[4] * 35, left)
    main.headerButtons["Settings"].click()
    app.processEvents()
    for button in main.findChildren(QtWidgets.QAbstractButton):
        expected = shape.OpenHandCursor if isinstance(button, (FurnishingButton, WindowButton)) else shape.PointingHandCursor
        assert button.cursor().shape() == (expected if button.isEnabled() else shape.ArrowCursor), button.accessibleName()
    for slider in main.findChildren(QtWidgets.QSlider):
        expected = shape.SizeHorCursor if slider.orientation() == QtCore.Qt.Orientation.Horizontal else shape.SizeVerCursor
        assert slider.cursor().shape() == (expected if slider.isEnabled() else shape.ArrowCursor)
    main.settingsWindow.tabs.setCurrentIndex(1)
    app.processEvents()
    for tree in (main.visibilityTree,):
        if tree is main.visibilityTree:
            main.sidebarTabs.setCurrentIndex(2)
            app.processEvents()
        index = tree.model().index(0, 0)
        option = QtWidgets.QStyleOptionViewItem()
        tree.itemDelegate().initStyleOption(option, index)
        option.rect = tree.visualRect(index)
        option.widget = tree
        rect = tree.style().subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, tree)
        Mouse(tree.viewport(), move, QtCore.QPointF(rect.center()))
        assert tree.viewport().cursor().shape() == shape.PointingHandCursor
        Mouse(tree.viewport(), move, QtCore.QPointF(option.rect.right() - 3, option.rect.center().y()))
        assert tree.viewport().cursor().shape() == shape.ArrowCursor
    button = main.fullscreenButton
    button.setEnabled(False)
    assert button.cursor().shape() == shape.ArrowCursor
    button.setEnabled(True)
    assert button.cursor().shape() == shape.PointingHandCursor
    Path("screenshots").mkdir(exist_ok = True)
    RotationCursor().pixmap().save("screenshots/rotation-cursor.png")
    main.close()


if __name__ == "__main__":
    Main()
