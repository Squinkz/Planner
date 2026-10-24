"""Text editors reserve shortcuts without disabling canvas keyboard actions."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow, Label
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    v = main.viewport
    label = Label()
    v.labels = [label]
    v.SetSelection([(label, None)])
    app.processEvents()
    field = main.labelTextField
    field.setFocus()
    field.selectAll()
    thickness = main.wallWidthSelector.slider.value()
    grid, measurements = v.showGrid, v.showMeasurements
    tab = main.sidebarTabs.currentIndex()
    text = "qwsdfhtumg123"
    QtTest.QTest.keyClicks(field, text)
    assert field.toPlainText() == text and label.text == text
    assert main.wallWidthSelector.slider.value() == thickness
    assert v.openingPlacementMode is None and not main.viewportOnlyMode
    assert main.sidebarTabs.currentIndex() == tab and not v.hiddenObjects
    for key in (QtCore.Qt.Key.Key_M, QtCore.Qt.Key.Key_G):
        QtTest.QTest.keyClick(field, key, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert (v.showGrid, v.showMeasurements) == (grid, measurements)
    QtTest.QTest.keyClick(field, QtCore.Qt.Key.Key_A, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert field.textCursor().selectedText() == field.toPlainText()
    QtTest.QTest.keyClick(field, QtCore.Qt.Key.Key_C, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert app.clipboard().text() == field.toPlainText()
    assert field.hasFocus()
    main.sidebarTabs.setCurrentIndex(1)
    main.furnishingSearchField.setFocus()
    QtTest.QTest.keyClicks(main.furnishingSearchField, "qw")
    assert main.furnishingSearchField.text() == "qw"
    assert main.wallWidthSelector.slider.value() == thickness
    # The same shortcut remains available when focus returns to the canvas.
    v.setFocus()
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Q)
    assert main.wallWidthSelector.slider.value() == max(main.wallWidthSelector.slider.minimum(), thickness - 1)
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_M)
    assert v.showMeasurements != measurements
    app.clipboard().clear()
    main.close()
    print("PASS: label/search typing and editing commands stay local; canvas shortcuts still work.")


if __name__ == "__main__":
    Main()
