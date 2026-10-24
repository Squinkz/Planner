"""Color entry synchronization, plane gestures, hue retention and dialog results."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.ui.color_picker import ColorPickerDialog


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    dialog = ColorPickerDialog(QtGui.QColor("#ff0000"))
    dialog.show()
    app.processEvents()
    assert [field.value() for field in dialog.rgbFields] == [255, 0, 0]
    assert [field.value() for field in dialog.hsvFields] == [0, 100, 100]
    dialog.hsvFields[0].setValue(120)
    assert dialog.color.name() == "#00ff00" and dialog.hexField.text() == "#00ff00"
    dialog.rgbFields[0].setValue(255)
    assert dialog.color.name() == "#ffff00" and dialog.hsvFields[0].value() == 60
    for text, expected in (("123456", "#123456"), ("#aBcDeF", "#abcdef"), ("abc", "#aabbcc")):
        dialog.hexField.selectAll()
        QtTest.QTest.keyClicks(dialog.hexField, text)
        assert dialog.color.name() == expected
        assert dialog.hexField.text() == text
        assert [field.value() for field in dialog.rgbFields] == list(QtGui.QColor(expected).getRgb()[:3])
    original = QtGui.QColor(dialog.color)
    dialog.hexField.selectAll()
    QtTest.QTest.keyClicks(dialog.hexField, "12")
    assert not dialog.hexField.hasAcceptableInput()
    assert dialog.color == original
    dialog.accept()
    assert not dialog.isVisible() and dialog.color == original, "Incomplete hex changed the confirmed color"
    dialog.show()
    dialog.SetColor(QtGui.QColor("red"))
    huePosition = QtCore.QPoint(16, round(1 + (dialog.huePlane.height() - 2) / 3))
    QtTest.QTest.mouseClick(dialog.huePlane, QtCore.Qt.MouseButton.LeftButton, pos = huePosition)
    assert abs(dialog.hue * 360 - 120) < 2
    svPosition = QtCore.QPoint(round(dialog.svPlane.width() / 2), round(dialog.svPlane.height() / 2))
    QtTest.QTest.mouseClick(dialog.svPlane, QtCore.Qt.MouseButton.LeftButton, pos = svPosition)
    assert abs(dialog.saturation - .5) < .01 and abs(dialog.value - .5) < .01
    dialog.SetHue(.7, 0)
    dialog.SetSv(.8, 0)
    assert dialog.color.name() == "#000000"
    assert dialog.hsvFields[0].value() == 252 and dialog.hsvFields[1].value() == 80
    dialog.SetSv(.8, 1)
    assert abs(dialog.color.hsvHueF() - .7) < .001
    oldHue = dialog.hue
    QtTest.QTest.keyClick(dialog.huePlane, QtCore.Qt.Key.Key_Down)
    assert abs(dialog.hue - oldHue - 1 / 360) < .000001
    dialog.hsvFields[1].setValue(0)
    assert dialog.hue > .7 and dialog.color.saturation() == 0
    dialog.hsvFields[1].setValue(100)
    assert dialog.color.saturation() == 255
    dialog.SetColor(QtGui.QColor("#46a8d2"))
    app.processEvents()
    dialog.grab().save(str(Path(__file__).parent.parent / "diagnostics" / "color-picker-preview.png"))
    dialog.close()
    QtCore.QTimer.singleShot(0, lambda: app.activeModalWidget().reject())
    assert not ColorPickerDialog.GetColor(QtGui.QColor("red")).isValid()
    QtCore.QTimer.singleShot(0, lambda: app.activeModalWidget().accept())
    assert ColorPickerDialog.GetColor(QtGui.QColor("blue")) == QtGui.QColor("blue")
    anchor = QtWidgets.QPushButton("Color")
    anchor.move(100, 100)
    anchor.show()
    popup = ColorPickerDialog(QtGui.QColor("red"))
    popup.popupAnchor = anchor
    popup.setWindowFlags(QtCore.Qt.WindowType.Popup | QtCore.Qt.WindowType.FramelessWindowHint)
    popup.show()
    app.processEvents()
    assert not popup.popupArmed
    available = anchor.screen().availableGeometry()
    assert available.contains(popup.geometry())
    # Leaving before any mouse movement into the popup must not dismiss it.
    app.sendEvent(popup, QtCore.QEvent(QtCore.QEvent.Type.Leave))
    assert popup.isVisible()
    inside = QtCore.QPointF(popup.mapToGlobal(QtCore.QPoint(20, 20)))
    movement = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(20, 20), inside,
                                QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.NoButton,
                                QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(popup, movement)
    assert popup.popupArmed
    app.sendEvent(popup, QtCore.QEvent(QtCore.QEvent.Type.Leave))
    assert not popup.isVisible() and popup.result() == QtWidgets.QDialog.DialogCode.Accepted
    popup.show()
    app.processEvents()
    outside = QtCore.QPointF(popup.mapToGlobal(QtCore.QPoint(-10, -10)))
    press = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonPress, QtCore.QPointF(-10, -10), outside,
                             QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.LeftButton,
                             QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(popup, press)
    assert not popup.isVisible() and not popup.popupArmed
    assert popup.result() == QtWidgets.QDialog.DialogCode.Accepted
    popup.show()
    app.processEvents()
    # A drag ending outside deactivates the popup until the mouse re-enters.
    editor = popup.rgbFields[0].lineEdit()
    QtTest.QTest.mousePress(editor, QtCore.Qt.MouseButton.LeftButton)
    outside = QtCore.QPointF(popup.mapToGlobal(QtCore.QPoint(popup.width() + 50, 20)))
    local = QtCore.QPointF(editor.mapFromGlobal(outside.toPoint()))
    popup.popupArmed = True
    drag = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, local, outside,
                            QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.LeftButton,
                            QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(editor, drag)
    with patch.object(QtWidgets.QApplication, "mouseButtons", return_value = QtCore.Qt.MouseButton.LeftButton):
        app.sendEvent(popup, QtCore.QEvent(QtCore.QEvent.Type.Leave))
    assert popup.isVisible() and popup.rgbFields[0].dragging
    QtTest.QTest.mouseRelease(editor, QtCore.Qt.MouseButton.LeftButton, pos = local.toPoint())
    assert not popup.rgbFields[0].dragging, "Popup consumed the spinbox's drag release"
    app.processEvents()
    assert popup.isVisible() and not popup.popupArmed
    outsideMove = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, local, outside,
                                   QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.NoButton,
                                   QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(editor, outsideMove)
    app.sendEvent(popup, QtCore.QEvent(QtCore.QEvent.Type.Leave))
    assert popup.isVisible() and not popup.popupArmed
    app.sendEvent(popup, movement)
    assert popup.popupArmed
    app.sendEvent(popup, QtCore.QEvent(QtCore.QEvent.Type.Leave))
    assert not popup.isVisible() and popup.result() == QtWidgets.QDialog.DialogCode.Accepted
    popup.show()
    app.processEvents()
    QtTest.QTest.mouseClick(popup.hexField, QtCore.Qt.MouseButton.RightButton)
    assert not popup.isVisible() and popup.result() == QtWidgets.QDialog.DialogCode.Rejected
    anchor.close()
    print("PASS: HSV/RGB/hex entry, mouse and keyboard planes, black/gray hue retention, cancel/accept")


if __name__ == "__main__":
    Main()
