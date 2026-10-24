"""Track clicks jump immediately, held drags reverse freely, and edits coalesce."""
import faulthandler
import os
import sys
from pathlib import Path

faulthandler.enable()
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Label, Arrow
from planner_app.ui.widgets import DragSlider
from planner_app.graphics.theme import BuildStyle


def Position(slider, fraction):
    option = QtWidgets.QStyleOptionSlider()
    slider.initStyleOption(option)
    handle = slider.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_Slider, option,
                                           QtWidgets.QStyle.SubControl.SC_SliderHandle, slider)
    groove = slider.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_Slider, option,
                                           QtWidgets.QStyle.SubControl.SC_SliderGroove, slider)
    if slider.orientation() == QtCore.Qt.Orientation.Horizontal:
        return QtCore.QPoint(round(groove.left() + handle.width() / 2 + (groove.width() - handle.width()) * fraction), slider.height() // 2)
    return QtCore.QPoint(slider.width() // 2, round(groove.top() + handle.height() / 2 + (groove.height() - handle.height()) * fraction))


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    left = QtCore.Qt.MouseButton.LeftButton
    slider = DragSlider(QtCore.Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.resize(320, 32)
    slider.show()
    app.processEvents()
    changes = []
    slider.valueChanged.connect(changes.append)
    QtTest.QTest.mousePress(slider, left, pos = Position(slider, .8))
    assert abs(slider.value() - 80) <= 1 and slider.isSliderDown()
    QtTest.QTest.qWait(650)
    assert len(changes) == 1, changes
    for fraction in (.2, .9, .1, .6):
        position = Position(slider, fraction)
        position.setY(120)
        QtTest.QTest.mouseMove(slider, position)
        assert abs(slider.value() - fraction * 100) <= 1
    QtTest.QTest.mouseRelease(slider, left, pos = Position(slider, .6))
    assert not slider.isSliderDown() and slider.dragOffset is None
    option = QtWidgets.QStyleOptionSlider()
    slider.initStyleOption(option)
    handle = slider.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_Slider, option,
                                           QtWidgets.QStyle.SubControl.SC_SliderHandle, slider)
    original = slider.value()
    QtTest.QTest.mousePress(slider, left, pos = handle.center() + QtCore.QPoint(4, 0))
    assert slider.value() == original
    QtTest.QTest.keyClick(slider, QtCore.Qt.Key.Key_Escape)
    assert slider.value() == original and not slider.isSliderDown()
    QtTest.QTest.mouseRelease(slider, left)
    QtTest.QTest.mousePress(slider, left, pos = Position(slider, .1))
    slider.setEnabled(False)
    assert not slider.isSliderDown() and slider.dragOffset is None
    slider.close()
    for orientation, inverted, expected in ((QtCore.Qt.Orientation.Vertical, False, 75),
                                            (QtCore.Qt.Orientation.Vertical, True, 25),
                                            (QtCore.Qt.Orientation.Horizontal, True, 75)):
        slider = DragSlider(orientation)
        slider.setRange(0, 100)
        slider.setInvertedAppearance(inverted)
        slider.resize(32, 320) if orientation == QtCore.Qt.Orientation.Vertical else slider.resize(320, 32)
        slider.show()
        app.processEvents()
        QtTest.QTest.mouseClick(slider, left, pos = Position(slider, .25))
        assert abs(slider.value() - expected) <= 1
        slider.close()
    main = MainWindow()
    main.show()
    main.headerButtons["Settings"].click()
    panel = main.settingsWindow
    panel.tabs.setCurrentIndex(2)
    app.processEvents()
    # Exercise grid callbacks, field synchronization and recovery timers while held.
    for key, slider in panel.sliders.items():
        option = QtWidgets.QStyleOptionSlider()
        slider.initStyleOption(option)
        handle = slider.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_Slider, option,
                                               QtWidgets.QStyle.SubControl.SC_SliderHandle, slider)
        original = slider.value()
        QtTest.QTest.mousePress(slider, left, pos = handle.center())
        QtTest.QTest.mouseMove(slider, handle.center() + QtCore.QPoint(0, 80))
        assert slider.value() == original
        QtTest.QTest.mouseRelease(slider, left, pos = handle.center())
        tolerance = slider.maximum() / max(1, slider.width() - 18) + 1
        QtTest.QTest.mousePress(slider, left, pos = Position(slider, .9))
        assert abs(slider.value() - slider.maximum() * .9) <= tolerance, (key, slider.value(), slider.width())
        QtTest.QTest.qWait(600)
        for fraction in (.9, .05, .8, .1):
            QtTest.QTest.mouseMove(slider, Position(slider, fraction))
            assert abs(slider.value() - slider.maximum() * fraction) <= tolerance
            assert main.viewport.gridIntensities[key] == slider.value() / 1000
        QtTest.QTest.mouseRelease(slider, left, pos = Position(slider, .1))
        assert not slider.isSliderDown()
    panel.close()
    for obj in (Label(), Arrow(QtCore.QPointF(), QtCore.QPointF(1000, 0))):
        v = main.viewport
        v.labels = [obj] if isinstance(obj, Label) else []
        v.walls = [] if isinstance(obj, Label) else [obj]
        v.SetSelection([(obj, None)])
        v.undoHistory.clear()
        v.redoHistory.clear()
        app.processEvents()
        slider = main.labelIntensitySlider if isinstance(obj, Label) else main.arrowFields["intensity"]
        QtTest.QTest.mousePress(slider, left, pos = Position(slider, .3))
        for fraction in (.8, .1, .5):
            QtTest.QTest.mouseMove(slider, Position(slider, fraction))
        QtTest.QTest.mouseRelease(slider, left, pos = Position(slider, .5))
        assert abs(obj.intensity - .5) <= .02
        assert main.propertyDragBefore is None and len(v.undoHistory) == 1
        v.Undo()
        assert obj.intensity == 1
    main.close()


if __name__ == "__main__":
    Main()
