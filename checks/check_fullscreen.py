"""Viewport-only layout, overlay controls, shortcuts and sidebar restoration."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from planner import MainWindow
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    main.mainSplitter.setSizes([950, 450])
    main.SetPropertiesCollapsed(True)
    app.processEvents()
    sizes = main.mainSplitter.sizes()
    propertiesSizes = main.sidebarContentSplitter.sizes()
    width = v.width()
    settings = main.ProjectSettings()
    v.setFocus()
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_F)
    app.processEvents()
    assert main.viewportOnlyMode and main.sidebarPanel.isHidden()
    assert v.width() > width and v.size() == main.centralWidget().size()
    assert main.fullscreenButton.isVisible()
    assert main.fullscreenButton.x() == v.width() - 42
    assert main.ProjectUiState()["mainSplitter"] == sizes
    assert main.SessionUiState()["mainSplitter"] == sizes
    assert main.ProjectSettings() == settings
    main.grab().save("screenshots/fullscreen-viewport.png")
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Escape)
    app.processEvents()
    assert not main.viewportOnlyMode and main.sidebarPanel.isVisible()
    assert main.mainSplitter.sizes() == sizes
    assert main.propertiesCollapsed and main.sidebarContentSplitter.sizes() == propertiesSizes
    QtTest.QTest.mouseClick(main.fullscreenButton, QtCore.Qt.MouseButton.LeftButton)
    app.processEvents()
    assert main.viewportOnlyMode
    main.resize(1500, 950)
    app.processEvents()
    assert main.fullscreenButton.x() == v.width() - 42
    QtTest.QTest.mouseClick(main.fullscreenButton, QtCore.Qt.MouseButton.LeftButton)
    app.processEvents()
    assert not main.viewportOnlyMode
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_F)
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_F)
    assert not main.viewportOnlyMode
    editor = QtWidgets.QLineEdit(main.sidebarPanel)
    editor.show()
    editor.setFocus()
    QtTest.QTest.keyClick(editor, QtCore.Qt.Key.Key_F)
    assert editor.text() == "f" and not main.viewportOnlyMode
    editor.deleteLater()
    main.close()
    print("PASS: fullscreen button, F/Esc, text entry and restored/persisted sidebar layout.")


if __name__ == "__main__":
    Main()
