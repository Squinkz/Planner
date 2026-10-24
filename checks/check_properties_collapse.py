"""Properties heading toggles, divider auto-collapse and session restoration."""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner_app.ui.main_window import MainWindow
from planner_app.graphics.theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    app.setStyleSheet(BuildStyle())
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    previousPath = os.environ.get("PLANNER_SESSION_PATH")
    with tempfile.TemporaryDirectory() as folder:
        os.environ["PLANNER_SESSION_PATH"] = str(Path(folder) / "session.json")
        main = MainWindow()
        main.show()
        app.processEvents()
        splitter = main.sidebarContentSplitter
        splitter.setSizes([500, 340])
        app.processEvents()
        original = splitter.sizes()
        viewportSize = main.viewport.size()
        left = QtCore.Qt.MouseButton.LeftButton
        QtTest.QTest.mouseClick(main.propertiesHeading, left)
        app.processEvents()
        assert main.propertiesCollapsed and not main.propertiesScrollArea.isVisible()
        assert main.propertiesPanel.height() == main.propertiesHeadingHeight
        assert splitter.sizes()[0] > original[0]
        assert main.propertiesPanel.geometry().bottom() == splitter.height() - 1
        assert main.viewport.size() == viewportSize
        assert main.propertiesHeading.toolTip() == "Restore object properties"
        assert not main.projectDirty
        collapsedHeight = main.propertiesPanel.height()
        main.resize(1440, 1000)
        app.processEvents()
        assert main.propertiesPanel.height() == collapsedHeight
        # The arrow shares the whole header's toggle behavior.
        QtTest.QTest.mouseClick(main.propertiesHeading.arrowLabel, left)
        app.processEvents()
        assert not main.propertiesCollapsed and main.propertiesScrollArea.isVisible()
        assert abs(splitter.sizes()[1] - original[1]) <= 1
        assert main.propertiesHeading.toolTip() == "Minimize object properties"
        main.resize(1440, 900)
        app.processEvents()
        # Drag below the threshold using actual global-coordinate handle events.
        handle = splitter.handle(1)
        start = handle.rect().center()
        globalEnd = splitter.mapToGlobal(QtCore.QPoint(splitter.width() // 2,
            splitter.height() - main.propertiesHeadingHeight - 10))
        QtTest.QTest.mousePress(handle, left, pos = start)
        move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove,
            QtCore.QPointF(handle.mapFromGlobal(globalEnd)), QtCore.QPointF(globalEnd),
            QtCore.Qt.MouseButton.NoButton, left, QtCore.Qt.KeyboardModifier.NoModifier)
        app.sendEvent(handle, move)
        QtTest.QTest.mouseRelease(handle, left, pos = handle.mapFromGlobal(globalEnd))
        app.processEvents()
        assert main.propertiesCollapsed and main.propertiesRestoreHeight is None
        assert main.propertiesPanel.height() == main.propertiesHeadingHeight
        # Keyboard restoration uses the default third after drag collapse.
        main.propertiesHeading.setFocus()
        QtTest.QTest.keyClick(main.propertiesHeading, QtCore.Qt.Key.Key_Space)
        app.processEvents()
        sizes = splitter.sizes()
        assert not main.propertiesCollapsed and abs(sizes[1] / sum(sizes) - 1 / 3) < .01
        # Both collapsed state and a remembered manual height survive reopening.
        splitter.setSizes([500, 320])
        app.processEvents()
        remembered = splitter.sizes()[1]
        QtTest.QTest.mouseClick(main.propertiesHeading, left)
        app.processEvents()
        main.sidebarPanel.grab().save("screenshots/properties-minimized.png")
        assert main.WriteSession(wait = True)
        main.close()
        restored = MainWindow()
        restored.show()
        app.processEvents()
        assert restored.sessionRestored and restored.propertiesCollapsed
        assert restored.propertiesPanel.height() == restored.propertiesHeadingHeight
        assert restored.propertiesRestoreHeight == remembered
        QtTest.QTest.mouseClick(restored.propertiesHeading, left)
        app.processEvents()
        assert abs(restored.sidebarContentSplitter.sizes()[1] - remembered) <= 1
        # A minimized panel can also be pulled open without jumping to its remembered height.
        QtTest.QTest.mouseClick(restored.propertiesHeading, left)
        app.processEvents()
        splitter = restored.sidebarContentSplitter
        handle = splitter.handle(1)
        assert handle.isEnabled()
        start = handle.rect().center()
        globalEnd = splitter.mapToGlobal(QtCore.QPoint(splitter.width() // 2,
            splitter.height() - 220))
        QtTest.QTest.mousePress(handle, left, pos = start)
        move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove,
            QtCore.QPointF(handle.mapFromGlobal(globalEnd)), QtCore.QPointF(globalEnd),
            QtCore.Qt.MouseButton.NoButton, left, QtCore.Qt.KeyboardModifier.NoModifier)
        app.sendEvent(handle, move)
        QtTest.QTest.mouseRelease(handle, left, pos = handle.mapFromGlobal(globalEnd))
        app.processEvents()
        assert not restored.propertiesCollapsed and restored.propertiesScrollArea.isVisible()
        assert 210 <= splitter.sizes()[1] <= 230
        assert restored.propertiesHeading.toolTip() == "Minimize object properties"
        assert not restored.propertiesDividerDragging
        restored.close()
    if previousPath is None:
        os.environ.pop("PLANNER_SESSION_PATH", None)
    else:
        os.environ["PLANNER_SESSION_PATH"] = previousPath
    print("PASS: heading/arrow collapse, bottom anchoring, divider threshold, default/manual restoration and session persistence")


if __name__ == "__main__":
    Main()
