"""Help autoscroll latching, held drags, margins, speed and cancellation."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.theme import ApplyApplicationTheme


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.show()
    main.ShowHelp("editing.md")
    helpWindow = main.helpWindow
    helpWindow.activateWindow()
    browser = helpWindow.browser
    browser.setPlainText("\n".join(f"Autoscroll line {index}" for index in range(1000)))
    helpWindow.resize(1200, 700)
    app.processEvents()
    scrollbar = browser.verticalScrollBar()
    middle = QtCore.Qt.MouseButton.MiddleButton
    originalCursor = QtGui.QCursor.pos()
    try:
        for target, anchor in ((browser.viewport(), QtCore.QPoint(60, 120)),
                               (browser, QtCore.QPoint(3, 120)),
                               (helpWindow, QtCore.QPoint(3, 200))):
            start = target.mapToGlobal(anchor)
            QtGui.QCursor.setPos(start)
            scrollbar.setValue(scrollbar.maximum() // 2)
            QtTest.QTest.mouseClick(target, middle, pos = anchor)
            assert helpWindow.autoScrollOrigin is not None and helpWindow.autoScrollAnchor.isVisible()
            assert helpWindow.autoScrollTimer.isActive()
            if target is browser.viewport():
                assert helpWindow.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/help-autoscroll.png"))
            value = scrollbar.value()
            QtTest.QTest.qWait(80)
            assert scrollbar.value() == value, "Anchor dead zone must not scroll"
            QtGui.QCursor.setPos(start + QtCore.QPoint(0, 50))
            QtTest.QTest.qWait(120)
            nearDelta = scrollbar.value() - value
            assert nearDelta > 0
            value = scrollbar.value()
            QtGui.QCursor.setPos(start + QtCore.QPoint(0, 150))
            QtTest.QTest.qWait(120)
            assert scrollbar.value() - value > nearDelta
            value = scrollbar.value()
            QtGui.QCursor.setPos(start - QtCore.QPoint(0, 100))
            QtTest.QTest.qWait(120)
            assert scrollbar.value() < value
            QtTest.QTest.keyClick(helpWindow, QtCore.Qt.Key.Key_Escape)
            assert helpWindow.isVisible() and helpWindow.autoScrollOrigin is None
            assert not helpWindow.autoScrollAnchor.isVisible() and not helpWindow.autoScrollTimer.isActive()
        # A held middle drag stops on release, while a click stays latched.
        anchor = QtCore.QPoint(70, 140)
        start = browser.viewport().mapToGlobal(anchor)
        QtGui.QCursor.setPos(start)
        QtTest.QTest.mousePress(browser.viewport(), middle, pos = anchor)
        end = anchor + QtCore.QPoint(0, 90)
        QtGui.QCursor.setPos(browser.viewport().mapToGlobal(end))
        QtTest.QTest.qWait(60)
        QtTest.QTest.mouseRelease(browser.viewport(), middle, pos = end)
        assert helpWindow.autoScrollOrigin is None
        # Cancelling with a click must not activate the control beneath it.
        QtGui.QCursor.setPos(start)
        QtTest.QTest.mouseClick(browser.viewport(), middle, pos = anchor)
        source = browser.source()
        QtTest.QTest.mouseClick(helpWindow.homeButton, QtCore.Qt.MouseButton.LeftButton)
        assert helpWindow.autoScrollOrigin is None and browser.source() == source
        QtGui.QCursor.setPos(start)
        QtTest.QTest.mouseClick(browser.viewport(), middle, pos = anchor)
        QtTest.QTest.mouseClick(browser.viewport(), middle, pos = anchor)
        assert helpWindow.autoScrollOrigin is None
        # Page changes, hiding and deactivation release the timer and mouse grab.
        for action in (lambda: helpWindow.ShowPage("README.md"), helpWindow.hide,
                       lambda: app.sendEvent(helpWindow, QtCore.QEvent(QtCore.QEvent.Type.WindowDeactivate))):
            helpWindow.show()
            app.processEvents()
            QtGui.QCursor.setPos(start)
            QtTest.QTest.mouseClick(browser.viewport(), middle, pos = anchor)
            assert helpWindow.autoScrollOrigin is not None
            action()
            assert helpWindow.autoScrollOrigin is None and not helpWindow.autoScrollTimer.isActive()
            assert QtWidgets.QWidget.mouseGrabber() is not helpWindow
    finally:
        helpWindow.StopAutoScroll()
        QtGui.QCursor.setPos(originalCursor)
        main.MarkProjectClean()
        main.close()
    print("PASS: Help middle-click autoscroll, held release, margins, dead zone, speed, direction and cancellation.")


if __name__ == "__main__":
    Main()
