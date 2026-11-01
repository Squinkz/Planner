"""Export wheel input scrolls the panel without editing value controls."""
import copy
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow


def Main():
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetOverride("titleBlock", dict(enabled = True))
        panel.scaleBarEnabled.setChecked(True)
        panel.SetScaleOption("pageOrigin", [0, 0])
        width, height = panel.PrintLayout()["paperTile"]
        panel.mainWindow.viewport.exportOverlay.bounds = (0, 0, width * 2, height)
        panel.SetBounds(panel.mainWindow.viewport.exportOverlay.bounds)
        assert all(field.isEnabled() for field in panel.pageOverlapFields)
        panel.scrollArea.widget().setMinimumHeight(5000)
        QtWidgets.QApplication.processEvents()
        scroll = panel.scrollArea.verticalScrollBar()
        assert scroll.maximum() > 500
        controls = [control for kind in (QtWidgets.QSlider, QtWidgets.QComboBox, QtWidgets.QAbstractSpinBox)
                    for control in panel.findChildren(kind) if control.window() is main.window()]
        assert panel.scaleBarStyle in controls and panel.scaleBarStyle.isEnabled()
        assert panel.scaleBarDivisionMode in controls and panel.scaleBarDivisionMode.isEnabled()
        checked = 0
        for control in controls:
            if not control.isEnabled():
                continue
            targets = [control]
            if isinstance(control, QtWidgets.QAbstractSpinBox) or isinstance(control, QtWidgets.QComboBox) and control.isEditable():
                targets.append(control.lineEdit())
            for target in targets:
                for focused in (False, True):
                    if focused:
                        target.setFocus()
                    else:
                        target.clearFocus()
                    QtWidgets.QApplication.processEvents()
                    for pixel, angle, modifiers in ((QtCore.QPoint(), QtCore.QPoint(0, -120), QtCore.Qt.KeyboardModifier.NoModifier),
                            (QtCore.QPoint(0, -20), QtCore.QPoint(), QtCore.Qt.KeyboardModifier.NoModifier),
                            (QtCore.QPoint(), QtCore.QPoint(0, -120), QtCore.Qt.KeyboardModifier.ControlModifier)):
                        before = copy.deepcopy(panel.overrides)
                        zoom = v.zoom
                        if isinstance(control, QtWidgets.QComboBox):
                            value = control.currentIndex()
                        elif isinstance(control, QtWidgets.QDateTimeEdit):
                            value = control.dateTime()
                        else:
                            value = control.value()
                        scroll.setValue(200)
                        point = QtCore.QPointF(target.rect().center())
                        wheel = QtGui.QWheelEvent(point, QtCore.QPointF(target.mapToGlobal(point.toPoint())), pixel, angle,
                            QtCore.Qt.MouseButton.NoButton, modifiers, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
                        QtWidgets.QApplication.sendEvent(target, wheel)
                        actual = (control.currentIndex() if isinstance(control, QtWidgets.QComboBox) else
                                  control.dateTime() if isinstance(control, QtWidgets.QDateTimeEdit) else control.value())
                        assert actual == value and panel.overrides == before, (control.accessibleName(), focused, pixel, angle)
                        assert v.zoom == zoom, "Export scroll changed canvas zoom"
                        # Qt's scroll area can ignore pixel-only deltas on some
                        # backends; angle-based wheel input must scroll normally.
                        if not angle.isNull() and modifiers == QtCore.Qt.KeyboardModifier.NoModifier:
                            assert scroll.value() > 200, (control.accessibleName(), "Wheel was swallowed")
                        checked += 1
        for labels in panel.measurementLabels.values():
            for label in labels:
                before = copy.deepcopy(v.measurementSettings)
                scroll.setValue(200)
                point = QtCore.QPointF(label.rect().center())
                wheel = QtGui.QWheelEvent(point, QtCore.QPointF(label.mapToGlobal(point.toPoint())), QtCore.QPoint(), QtCore.QPoint(0, -120),
                    QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
                QtWidgets.QApplication.sendEvent(label, wheel)
                assert v.measurementSettings == before and scroll.value() > 200, "Dimension label intercepted export scrolling"
        slider = panel.borderSizeSlider
        before = slider.value()
        slider.setFocus()
        QtTest.QTest.keyClick(slider, QtCore.Qt.Key.Key_Right)
        assert slider.value() != before, "Wheel guard blocked slider keyboard input"
        combo = panel.titleBlockLogoMode
        combo.setCurrentText("Planner")
        combo.setFocus()
        QtTest.QTest.keyClick(combo, QtCore.Qt.Key.Key_Up)
        assert combo.currentText() == "None", "Wheel guard blocked dropdown keyboard input"
        # An open dropdown still scrolls its option list without committing a size.
        combo = panel.pageSizeField
        combo.view().setFixedHeight(120)
        combo.showPopup()
        QtWidgets.QApplication.processEvents()
        view = combo.view()
        bar = view.verticalScrollBar()
        assert bar.maximum() > 0
        bar.setValue(0)
        before = combo.currentData()
        point = QtCore.QPointF(view.viewport().rect().center())
        wheel = QtGui.QWheelEvent(point, QtCore.QPointF(view.viewport().mapToGlobal(point.toPoint())), QtCore.QPoint(), QtCore.QPoint(0, -120),
            QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        QtWidgets.QApplication.sendEvent(view.viewport(), wheel)
        assert bar.value() > 0 and combo.currentData() == before
        combo.hidePopup()
    print(f"Export wheel guard verified for {len(controls)} controls and {checked} wheel/focus cases, plus keyboard and popup scrolling")


if __name__ == "__main__":
    Main()
