"""Bundled help navigation, theme rendering and editor isolation."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from fixtures.parity_examples import CreateObject, ExampleWindow, InstallScene, WorkflowState
from planner_app.graphics.palette import themeColors


def Main():
    captures = workspace / "diagnostics" / "help-menu-20261018"
    captures.mkdir(exist_ok = True)
    with ExampleWindow() as (main, folder):
        app = QtWidgets.QApplication.instance()
        wall = CreateObject(main.viewport, "Wall")
        InstallScene(main, [wall])
        main.viewport.SetSelection([(wall, -1)])
        before = WorkflowState(main)
        assert main.helpWindow is None
        main.menuButtons["Help"].click()
        app.processEvents()
        helpWindow = main.helpWindow
        browser = helpWindow.browser
        assert helpWindow.isVisible() and not helpWindow.isModal()
        initialFont = browser.document().defaultFont().toString()
        initialSize = browser.document().size()
        initialParagraph = browser.document().documentLayout().blockBoundingRect(browser.document().begin().next())
        helpWindow.homeButton.click()
        app.processEvents()
        assert browser.document().defaultFont().toString() == initialFont
        assert browser.document().size() == initialSize
        assert browser.document().documentLayout().blockBoundingRect(browser.document().begin().next()) == initialParagraph
        assert helpWindow.windowFlags() & QtCore.Qt.WindowType.WindowMinimizeButtonHint
        assert helpWindow.windowFlags() & QtCore.Qt.WindowType.WindowMaximizeButtonHint
        helpWindow.showMaximized()
        app.processEvents()
        assert helpWindow.isMaximized()
        helpWindow.showMinimized()
        app.processEvents()
        assert helpWindow.isMinimized()
        main.menuButtons["Help"].click()
        app.processEvents()
        assert helpWindow.isMaximized() and not helpWindow.isMinimized()
        helpWindow.showNormal()
        app.processEvents()
        assert not helpWindow.isMinimized() and not helpWindow.isMaximized()
        assert browser.toPlainText().startswith("Welcome to Planner")
        assert browser.document().firstBlock().blockFormat().headingLevel() == 1
        assert not helpWindow.backButton.isEnabled()
        assert all(not button.autoDefault() for button in (helpWindow.backButton, helpWindow.forwardButton, helpWindow.homeButton))
        block = browser.document().begin()
        destinations = []
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.charFormat().isAnchor():
                    destinations.append(fragment.charFormat().anchorHref())
                    assert fragment.charFormat().foreground().color() == QtGui.QColor(themeColors["info"])
                    assert fragment.charFormat().fontUnderline()
                iterator += 1
            block = block.next()
        assert "editing.md" in destinations and "export.md" in destinations
        assert helpWindow.grab().save(str(captures / "home-dark.png"))
        browser.verticalScrollBar().setValue(150)
        cursor = browser.document().find("Selecting, moving and editing")
        cursor.setPosition(cursor.selectionStart() + 5)
        browser.setTextCursor(cursor)
        browser.ensureCursorVisible()
        originalScroll = browser.verticalScrollBar().value()
        QtTest.QTest.mouseClick(browser.viewport(), QtCore.Qt.MouseButton.LeftButton,
                               pos = browser.cursorRect(cursor).center())
        app.processEvents()
        assert browser.source().fileName() == "editing.md" and helpWindow.backButton.isEnabled()
        assert "Selecting" in helpWindow.windowTitle()
        helpWindow.backButton.click()
        app.processEvents()
        assert browser.source().fileName() == "README.md"
        assert browser.verticalScrollBar().value() == originalScroll
        helpWindow.forwardButton.click()
        assert browser.source().fileName() == "editing.md"
        # Device navigation works over document text, margins and navigation buttons.
        # Three history entries detect accidental handling on both press and release.
        helpWindow.ShowPage("export.md")
        for target in (browser.viewport(), browser, helpWindow, helpWindow.homeButton):
            QtTest.QTest.mouseClick(target, QtCore.Qt.MouseButton.BackButton)
            assert browser.source().fileName() == "editing.md"
            QtTest.QTest.mouseClick(target, QtCore.Qt.MouseButton.ForwardButton)
            assert browser.source().fileName() == "export.md"
        helpWindow.activateWindow()
        helpWindow.homeButton.setFocus()
        app.processEvents()
        for key, modifiers, expected in ((QtCore.Qt.Key.Key_Back, QtCore.Qt.KeyboardModifier.NoModifier, "editing.md"),
                                         (QtCore.Qt.Key.Key_Forward, QtCore.Qt.KeyboardModifier.NoModifier, "export.md"),
                                         (QtCore.Qt.Key.Key_Left, QtCore.Qt.KeyboardModifier.AltModifier, "editing.md"),
                                         (QtCore.Qt.Key.Key_Right, QtCore.Qt.KeyboardModifier.AltModifier, "export.md")):
            QtTest.QTest.keyClick(helpWindow.homeButton, key, modifiers)
            assert browser.source().fileName() == expected
        helpWindow.homeButton.click()
        assert browser.source().fileName() == "README.md"
        current = browser.source()
        assert not helpWindow.ShowPage("missing.md")
        assert helpWindow.statusLabel.isVisible() and browser.source() == current
        assert not helpWindow.ShowPage("../../README.md")
        helpWindow.homeButton.click()
        assert not helpWindow.statusLabel.isVisible()
        with patch.object(QtGui.QDesktopServices, "openUrl", return_value = True) as external:
            helpWindow.OpenLink(QtCore.QUrl("https://example.com/help"))
            external.assert_called_once()
            helpWindow.OpenLink(QtCore.QUrl("javascript:alert(1)"))
            assert external.call_count == 1
        assert browser.source() == current
        helpWindow.resize(440, 360)
        app.processEvents()
        assert browser.horizontalScrollBar().maximum() == 0
        textLeft = browser.viewport().mapTo(helpWindow, QtCore.QPoint(20, 0)).x()
        assert helpWindow.backButton.mapTo(helpWindow, QtCore.QPoint()).x() == textLeft
        assert helpWindow.grab().save(str(captures / "home-small.png"))
        for page in sorted((workspace / "planner-main" / "docs" / "help").glob("*.md")):
            assert helpWindow.ShowPage(page)
            app.processEvents()
            assert browser.toPlainText() and browser.horizontalScrollBar().maximum() == 0, page
        helpWindow.homeButton.click()
        helpWindow.resize(1440, 900)
        app.processEvents()
        assert browser.width() == helpWindow.width() - 24
        assert abs(browser.viewport().width() - 880) <= 1
        scrollbar = browser.verticalScrollBar()
        if scrollbar.isVisible():
            assert helpWindow.width() - scrollbar.mapTo(helpWindow, scrollbar.rect().topRight()).x() < 20
        assert abs(browser.mapTo(helpWindow, browser.rect().center()).x() - helpWindow.rect().center().x()) <= 1
        textLeft = browser.viewport().mapTo(helpWindow, QtCore.QPoint(20, 0)).x()
        assert helpWindow.backButton.mapTo(helpWindow, QtCore.QPoint()).x() == textLeft
        assert browser.document().firstBlock().blockFormat().alignment() == QtCore.Qt.AlignmentFlag.AlignLeft
        image = browser.grab().toImage()
        assert image.pixelColor(5, 10).name() == themeColors["windowBackground"]
        assert image.pixelColor(browser.viewport().x() + 5, browser.viewport().y() + 5).name() == themeColors["fieldBackground"]
        helpWindow.ShowPage("editing.md")
        app.processEvents()
        assert scrollbar.maximum() > 0
        for target, position in ((browser, QtCore.QPointF(5, 100)),
                                 (browser, QtCore.QPointF(browser.width() - 25, 100)),
                                 (helpWindow, QtCore.QPointF(2, 100))):
            scrollbar.setValue(0)
            event = QtGui.QWheelEvent(position, QtCore.QPointF(target.mapToGlobal(position.toPoint())),
                                      QtCore.QPoint(), QtCore.QPoint(0, -120), QtCore.Qt.MouseButton.NoButton,
                                      QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
            QtWidgets.QApplication.sendEvent(target, event)
            assert scrollbar.value() > 0
        helpWindow.ShowPage("README.md")
        app.processEvents()
        scrollbar.setValue(0)
        assert helpWindow.grab().save(str(captures / "home-wide.png"))
        helpWindow.resize(880, 720)
        main.SetThemes("Light UI", "Dark Canvas", notify = False)
        app.processEvents()
        assert helpWindow.grab().save(str(captures / "home-light.png"))
        assert browser.palette().color(QtGui.QPalette.ColorRole.Text) != browser.palette().color(QtGui.QPalette.ColorRole.Base)
        main.SetThemes("Dark UI", "Dark Canvas", notify = False)
        main.menuButtons["Keyboard shortcuts"].click()
        app.processEvents()
        assert main.helpWindow is helpWindow and browser.source().fileName() == "shortcuts.md"
        assert helpWindow.grab().save(str(captures / "shortcuts-dark.png"))
        main.menuButtons["About"].click()
        assert main.aboutDialog is not None and main.aboutDialog.isVisible()
        assert browser.source().fileName() == "shortcuts.md"
        main.aboutDialog.close()
        browser.setFocus()
        QtTest.QTest.keyClick(browser, QtCore.Qt.Key.Key_Delete)
        QtTest.QTest.keyClick(browser, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
        assert WorkflowState(main) == before
        QtTest.QTest.keyClick(helpWindow, QtCore.Qt.Key.Key_Escape)
        assert not helpWindow.isVisible()
        assert browser.backwardHistoryCount() == browser.forwardHistoryCount() == 0
        main.activateWindow()
        main.viewport.setFocus()
        app.processEvents()
        QtTest.QTest.keyClick(main.viewport, QtCore.Qt.Key.Key_F1)
        app.processEvents()
        assert helpWindow.isVisible() and browser.source().fileName() == "README.md"
        assert not helpWindow.backButton.isEnabled() and not helpWindow.forwardButton.isEnabled()
        helpWindow.showMinimized()
        main.activateWindow()
        main.viewport.setFocus()
        app.processEvents()
        QtTest.QTest.keyClick(main.viewport, QtCore.Qt.Key.Key_F1)
        app.processEvents()
        assert helpWindow.isMaximized() and not helpWindow.isMinimized()
        assert WorkflowState(main) == before
        helpWindow.close()
        assert browser.backwardHistoryCount() == browser.forwardHistoryCount() == 0
        main.menuButtons["Keyboard shortcuts"].click()
        app.processEvents()
        assert browser.source().fileName() == "shortcuts.md"
        assert not helpWindow.backButton.isEnabled() and not helpWindow.forwardButton.isEnabled()
        helpWindow.close()
    print("Help viewer: native Markdown, navigation, reuse, themes, wrapping and editor isolation passed")


if __name__ == "__main__":
    Main()
