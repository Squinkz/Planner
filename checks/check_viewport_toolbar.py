"""Shared square viewport controls remain available across all sidebar tabs."""
import os, sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    main.activateWindow()
    main.viewport.setFocus()
    app.processEvents()
    groupMode = main.viewport.groupModeEnabled
    tabIndex = main.sidebarTabs.currentIndex()
    localTransforms = main.viewport.localTransforms
    for expected in (not groupMode, groupMode):
        QtTest.QTest.keyClick(main.viewport, QtCore.Qt.Key.Key_Tab, QtCore.Qt.KeyboardModifier.ControlModifier)
        assert main.viewport.groupModeEnabled == main.groupModeButton.isChecked() == expected
        assert main.sidebarTabs.currentIndex() == tabIndex and main.viewport.localTransforms == localTransforms
    assert not main.groupModeShortcut.autoRepeat()
    buttons = [main.snapButton, main.connectedOptions["vertices"], main.connectedOptions["objects"]]
    assert [button.accessibleName() for button in buttons] == ["Snap", "Connected Points", "Connected Objects"]
    assert all(button.parent() is main.viewportToolbar for button in buttons)
    assert main.snapButton.size() == main.snapOptionsButton.size() == QtCore.QSize(40, 40)
    assert main.snapButton.menu() is None and main.snapOptionsButton.menu() is None
    assert all(button.width() == button.height() == 40 for button in buttons[1:])
    assert all(not button.text() and not button.icon().isNull() for button in buttons)
    toolbarTop = main.viewportToolbar.mapToGlobal(QtCore.QPoint()).y()
    headerBottom = main.headerButtons["File"].mapToGlobal(QtCore.QPoint(0, main.headerButtons["File"].height())).y()
    tabTop = main.sidebarTabs.mapToGlobal(QtCore.QPoint()).y()
    assert headerBottom < toolbarTop
    stripRight = main.sidebarToolbarStrip.mapToGlobal(QtCore.QPoint(main.sidebarToolbarStrip.width(), 0)).x()
    assert stripRight < main.sidebarTabs.mapToGlobal(QtCore.QPoint()).x()
    assert main.sidebarToolbarStrip.mapToGlobal(QtCore.QPoint()).y() == tabTop
    assert buttons[0].y() < buttons[1].y() < buttons[2].y()
    assert main.snapButton.y() < main.snapOptionsButton.y() < buttons[1].y()
    assert not main.buildScrollArea.widget().isAncestorOf(main.viewportToolbar)
    for index in range(main.sidebarTabs.count()):
        main.sidebarTabs.setCurrentIndex(index)
        app.processEvents()
        assert all(button.isVisible() for button in buttons)
        QtTest.QTest.mouseClick(buttons[1], QtCore.Qt.MouseButton.LeftButton)
        QtTest.QTest.mouseClick(buttons[2], QtCore.Qt.MouseButton.LeftButton)
        assert main.viewport.connectedVerticesEnabled == buttons[1].isChecked()
        assert main.viewport.connectedObjectsEnabled == buttons[2].isChecked()
    # Snap toggles independently; the separate options button opens its menu.
    main.viewport.setFocus()
    for index, key in enumerate((QtCore.Qt.Key.Key_1, QtCore.Qt.Key.Key_2, QtCore.Qt.Key.Key_3, QtCore.Qt.Key.Key_4)):
        QtTest.QTest.keyClick(main.viewport, key)
        assert main.sidebarTabs.currentIndex() == index
        assert main.viewport.exportOverlay.active == (index == 3)
    QtTest.QTest.keyClick(main.viewport, QtCore.Qt.Key.Key_1)
    editor = QtWidgets.QLineEdit(main)
    editor.show()
    editor.setFocus()
    QtTest.QTest.keyClick(editor, QtCore.Qt.Key.Key_4)
    assert editor.text() == "4" and main.sidebarTabs.currentIndex() == 0
    editor.hide()
    editor.deleteLater()
    main.sidebarTabs.setCurrentIndex(0)
    app.processEvents()
    old = main.viewport.snapEnabled
    QtTest.QTest.mouseClick(main.snapButton, QtCore.Qt.MouseButton.LeftButton, pos = QtCore.QPoint(10, 20))
    assert main.viewport.snapEnabled != old
    old = main.viewport.snapEnabled
    QtTest.QTest.mouseClick(main.snapOptionsButton, QtCore.Qt.MouseButton.LeftButton)
    assert main.snapMenu.isVisible() and main.viewport.snapEnabled == old
    assert main.snapMenu.geometry().right() < main.snapOptionsButton.mapToGlobal(QtCore.QPoint()).x()
    assert main.snapOptionsButton.isChecked()
    main.snapMenu.grab().save('screenshots/snap-options-menu.png')
    gridButton = main.snapOptions["grid"]
    assert gridButton.objectName() == "headerMenuItem" and not gridButton.iconLabel.pixmap().isNull()
    QtTest.QTest.mouseClick(gridButton, QtCore.Qt.MouseButton.LeftButton)
    assert not main.snapMenu.isVisible() and not main.viewport.gridSnapEnabled
    assert not main.snapOptionsButton.isChecked()
    assert gridButton.iconLabel.pixmap().isNull()
    main.snapMenu.show()
    QtTest.QTest.mouseClick(gridButton, QtCore.Qt.MouseButton.LeftButton)
    assert not main.snapMenu.isVisible() and main.viewport.gridSnapEnabled
    assert not gridButton.iconLabel.pixmap().isNull()
    main.snapMenu.hide()
    QtTest.QTest.mouseClick(main.snapOptionsButton, QtCore.Qt.MouseButton.LeftButton)
    assert main.snapMenu.isVisible()
    main.snapMenu.hide()
    main.sidebarTabs.setCurrentIndex(0)
    main.grab().save('screenshots/shared-viewport-toolbar.png')
    main.close()
    print("PASS: square Snap toggle, separate options button, vertical toolbar and themed menu gestures.")


if __name__ == "__main__":
    Main()
