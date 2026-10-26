"""Held modifiers, tools and mouse gestures cannot outlive their input context."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall
from planner_app.ui.widgets import DragSpinBox, DragSlider, FurnishingButton


def Move(widget, position, buttons = QtCore.Qt.MouseButton.LeftButton, modifiers = QtCore.Qt.KeyboardModifier.NoModifier):
    position = QtCore.QPointF(position)
    event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, position,
                             QtCore.QPointF(widget.mapToGlobal(position.toPoint())),
                             QtCore.Qt.MouseButton.NoButton, buttons, modifiers)
    QtWidgets.QApplication.sendEvent(widget, event)


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        point = QtCore.QPointF
        none = QtCore.Qt.KeyboardModifier.NoModifier
        left, right, middle = QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.RightButton, QtCore.Qt.MouseButton.MiddleButton
        wall = Wall(point(0, 0), point(1000, 0), 200)
        InstallScene(main, [wall])
        main.snapButton.setChecked(False)
        for key, owner, attribute in ((QtCore.Qt.Key.Key_Control, v, "controlHeld"),
                                      (QtCore.Qt.Key.Key_Shift, main, "shiftHeld")):
            QtTest.QTest.keyPress(v, key)
            assert getattr(owner, attribute)
            main.ShowSettings()
            settings = main.settingsWindow
            settings.tabs.setCurrentIndex(1)
            field = settings.precisionField
            field.setFocus()
            QtTest.QTest.keyRelease(field, key)
            assert not getattr(owner, attribute)
            QtTest.QTest.keyPress(field, key)
            assert getattr(owner, attribute)
            QtTest.QTest.keyRelease(v, key)
            assert not getattr(owner, attribute)
            settings.hide()

        # A pointer event reconciles a modifier release swallowed by native UI.
        QtTest.QTest.keyPress(v, QtCore.Qt.Key.Key_Control)
        QtTest.QTest.keyPress(v, QtCore.Qt.Key.Key_Shift)
        # sendEvent bypasses Qt's native modifier-cache refresh, so emulate the
        # state that real post-dialog pointer input reports to QApplication.
        with patch.object(QtWidgets.QApplication, "keyboardModifiers", return_value = none):
            Move(v, point(200, 200), QtCore.Qt.MouseButton.NoButton)
        assert not v.controlHeld and not main.shiftHeld
        QtTest.QTest.keyRelease(v, QtCore.Qt.Key.Key_Shift)
        QtTest.QTest.keyRelease(v, QtCore.Qt.Key.Key_Control)

        for key in (QtCore.Qt.Key.Key_D, QtCore.Qt.Key.Key_S):
            v.BeginOpeningMode("Door" if key == QtCore.Qt.Key.Key_D else "Window")
            assert v.openingPlacementMode is not None
            QtWidgets.QApplication.sendEvent(main, QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate))
            assert v.openingPlacementMode is None and not v.openingPlacementPressed

        start = v.WorldToViewport(wall.firstVertex).toPoint()
        for lostButtons in (False, True):
            original = point(wall.firstVertex)
            QtTest.QTest.mousePress(v, left, pos = start)
            Move(v, start + QtCore.QPoint(35, -23))
            assert wall.firstVertex != original and v.dragStart is not None
            if lostButtons:
                Move(v, start + QtCore.QPoint(40, -28), QtCore.Qt.MouseButton.NoButton)
            else:
                QtWidgets.QApplication.sendEvent(main, QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate))
            assert wall.firstVertex == original and v.dragStart is None and not v.isDragging
            QtTest.QTest.mouseRelease(v, left, pos = start)

        void = v.WorldToViewport(point(-1500, -1000)).toPoint()
        QtTest.QTest.mousePress(v, left, pos = void)
        assert v.boxStart is not None
        QtWidgets.QApplication.sendEvent(main, QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate))
        assert v.boxStart is None and v.pendingShiftSelection is None
        QtTest.QTest.mouseRelease(v, left, pos = void)
        QtTest.QTest.mousePress(v, right, pos = void)
        Move(v, void + QtCore.QPoint(45, -30), right)
        assert v.pendingWall is not None
        QtWidgets.QApplication.sendEvent(main, QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate))
        assert v.pendingWall is None and v.rightClickStart is None and v.wallDrawButton is None
        QtTest.QTest.mouseRelease(v, right, pos = void)
        QtTest.QTest.mousePress(v, middle, pos = void)
        assert v.isPanning
        QtWidgets.QApplication.sendEvent(main, QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate))
        assert not v.isPanning and not v.panFrameTimer.isActive() and not v.dragPanTimer.isActive()
        QtTest.QTest.mouseRelease(v, middle, pos = void)

        imagePath = folder / "reference.png"
        image = QtGui.QImage(100, 50, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor("red"))
        assert image.save(str(imagePath))
        reference = main.referenceImage
        assert reference.Load(imagePath)
        reference.state.update(center = [0, 0], width = 2000, height = 1000)
        reference.SyncControls()
        original = reference.Snapshot()
        center = v.WorldToViewport(point()).toPoint()
        QtTest.QTest.mousePress(v, left, pos = center)
        Move(v, center + QtCore.QPoint(35, 23))
        assert reference.drag is not None and reference.Snapshot() != original
        QtWidgets.QApplication.sendEvent(main, QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate))
        assert reference.active and reference.drag is None and reference.Snapshot() == original
        QtTest.QTest.mouseRelease(v, left, pos = center)
        calibration = reference.calibration
        calibration.Start()
        QtTest.QTest.mousePress(v, left, pos = center)
        assert calibration.placementPress is not None
        Move(v, center + QtCore.QPoint(40, -30))
        assert calibration.draggedPoint is not None and len(calibration.points) == 2
        QtWidgets.QApplication.sendEvent(v, QtCore.QEvent(QtCore.QEvent.Type.UngrabMouse))
        assert calibration.active and calibration.draggedPoint is None
        assert calibration.placementPress is None and len(calibration.points) == 1
        QtTest.QTest.mouseRelease(v, left, pos = center)
        calibration.Stop()
        reference.Hide()

        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        overlay = v.exportOverlay
        x, y, width, length = overlay.bounds
        edge = v.WorldToViewport(point(x, y + length / 2)).toPoint()
        QtTest.QTest.mousePress(v, left, pos = edge)
        assert overlay.dragEdge is not None or overlay.dragRuler is not None
        QtWidgets.QApplication.sendEvent(main, QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate))
        assert overlay.dragEdge is None and overlay.dragRuler is None
        assert main.exportPanel.exportGestureBefore is None
        QtTest.QTest.mouseRelease(v, left, pos = edge)
        main.sidebarTabs.setCurrentIndex(0)

        # Palette presses and the custom wall selector cannot arm a later drag.
        furnishing = FurnishingButton(v.furnishingDefinitions["desk"])
        furnishing.setParent(main)
        furnishing.show()
        for button in (main.windowButton, furnishing):
            QtTest.QTest.mousePress(button, left, pos = button.rect().center())
            assert button.pressPosition is not None
            QtWidgets.QApplication.sendEvent(button, QtCore.QEvent(QtCore.QEvent.Type.UngrabMouse))
            assert button.pressPosition is None and not button.isDown()
            QtTest.QTest.mouseRelease(button, left, pos = button.rect().center())
        furnishing.hide()
        selector = main.wallWidthSelector
        position = QtCore.QPoint(round(selector.PresetCenters()[1]), 15)
        QtTest.QTest.mousePress(selector, left, pos = position)
        assert selector.pressX is not None
        QtWidgets.QApplication.sendEvent(selector, QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate))
        assert selector.pressX is None and not selector.dragging
        QtTest.QTest.mouseRelease(selector, left, pos = position)

        # Scrubbing fields cancel once, release the cursor and ignore stale moves.
        scrub = DragSpinBox(main)
        scrub.setRange(-1000, 1000)
        scrub.setValue(50)
        scrub.resize(200, 32)
        scrub.show()
        finished = []
        scrub.dragFinished.connect(finished.append)
        editor = scrub.lineEdit()
        center = editor.rect().center()
        QtTest.QTest.mousePress(editor, left, pos = center)
        Move(editor, center + QtCore.QPoint(30, 0))
        assert scrub.dragging
        QtWidgets.QApplication.sendEvent(scrub, QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate))
        assert not scrub.dragging and scrub.pressPosition is None and finished == [True]
        value = scrub.value()
        Move(editor, center + QtCore.QPoint(60, 0), QtCore.Qt.MouseButton.NoButton)
        assert scrub.value() == value and finished == [True]
        QtTest.QTest.mouseRelease(editor, left, pos = center)
        scrub.hide()

        slider = DragSlider(QtCore.Qt.Orientation.Horizontal, main)
        slider.resize(200, 32)
        slider.show()
        QtTest.QTest.mousePress(slider, left, pos = slider.rect().center())
        assert slider.isSliderDown() and slider.dragOffset is not None
        QtWidgets.QApplication.sendEvent(slider, QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate))
        assert not slider.isSliderDown() and slider.dragOffset is None
        QtTest.QTest.mouseRelease(slider, left, pos = slider.rect().center())
        slider.hide()

        main.ShowSettings()
        settings = main.settingsWindow
        settings.tabs.setCurrentIndex(1)
        settings.wallMeasurementModeField.setCurrentText("All")
        QtWidgets.QApplication.processEvents()
        label = next(label for label in settings.findChildren(QtWidgets.QLabel) if label.property("measurementKey") == "doors")
        QtTest.QTest.mousePress(label, left, pos = label.rect().center())
        assert settings.measurementDragging == "doors"
        QtWidgets.QApplication.sendEvent(settings, QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate))
        assert settings.measurementDragging is None and not settings.measurementSliders["doors"].isSliderDown()
        QtTest.QTest.mouseRelease(label, left, pos = label.rect().center())
        settings.hide()

        # Application loss clears every cached modifier as well as button state.
        QtTest.QTest.keyPress(v, QtCore.Qt.Key.Key_Control)
        QtTest.QTest.keyPress(v, QtCore.Qt.Key.Key_Shift)
        QtTest.QTest.keyPress(v, QtCore.Qt.Key.Key_Alt)
        QtWidgets.QApplication.sendEvent(QtWidgets.QApplication.instance(), QtCore.QEvent(QtCore.QEvent.Type.ApplicationDeactivate))
        assert not v.controlHeld and not main.shiftHeld and not main.altHeld
        for key in (QtCore.Qt.Key.Key_Alt, QtCore.Qt.Key.Key_Shift, QtCore.Qt.Key.Key_Control):
            QtTest.QTest.keyRelease(v, key)
    print("PASS: cross-window modifiers, held tools, canvas drags, panning, scrubs, sliders and application deactivation")


if __name__ == "__main__":
    Main()
