"""Standalone Stacker-style About, footer actions and help-link routing."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow, WorkflowState
from planner_app.version import displayVersion


def Main():
    captures = workspace / "diagnostics" / "help-menu-20261018"
    captures.mkdir(exist_ok = True)
    with ExampleWindow() as (main, folder):
        app = QtWidgets.QApplication.instance()
        before = WorkflowState(main)
        main.menuButtons["About"].click()
        app.processEvents()
        about = main.aboutDialog
        assert main.helpWindow is None
        assert about.isVisible() and about.windowTitle() == "About Planner"
        assert about.windowFlags() & QtCore.Qt.WindowType.FramelessWindowHint
        assert about.minimumWidth() == 600
        assert about.layout().contentsMargins() == QtCore.QMargins(24, 24, 24, 18)
        assert about.layout().spacing() == 12
        assert not about.logoLabel.pixmap().isNull()
        assert about.logoLabel.pixmap().size() == QtCore.QSize(300, 300)
        labels = [widget.text() for widget in about.findChildren(QtWidgets.QLabel)]
        assert displayVersion in labels and "2026 Dieter Stassen" in labels
        assert "Build your dream,\ndesign your space.\n\nMake your house a Home." in labels
        assert not any("Stacker" in text for text in labels)
        assert about.grab().save(str(captures / "about-dark.png"))
        main.ShowAbout()
        assert main.aboutDialog is about
        QtTest.QTest.mouseClick(about.logoLabel, QtCore.Qt.MouseButton.LeftButton)
        assert main.aboutDialog is None
        main.SetThemes("Light UI", "Dark Canvas", notify = False)
        main.ShowAbout()
        app.processEvents()
        assert main.aboutDialog.grab().save(str(captures / "about-light.png"))
        main.aboutDialog.close()
        main.SetThemes("Dark UI", "Dark Canvas", notify = False)
        main.ShowHelp()
        helpWindow = main.helpWindow
        source = helpWindow.browser.source()
        historyCount = helpWindow.browser.backwardHistoryCount()
        helpWindow.OpenLink(QtCore.QUrl("about"))
        app.processEvents()
        assert main.aboutDialog.isVisible()
        assert helpWindow.browser.source() == source
        assert helpWindow.browser.backwardHistoryCount() == historyCount
        for name, url in (("Github", "https://github.com/Squinkz/Planner"),
                          ("Report Issue", "https://github.com/Squinkz/Planner/issues")):
            main.ShowAbout()
            with patch.object(QtGui.QDesktopServices, "openUrl", return_value = True) as openUrl:
                link = next(widget for widget in main.aboutDialog.findChildren(QtWidgets.QWidget)
                            if widget.accessibleName() == name)
                QtTest.QTest.mouseClick(link, QtCore.Qt.MouseButton.LeftButton)
                assert openUrl.call_count == 1
                assert openUrl.call_args.args[0].toString() == url
            assert main.aboutDialog is None
        main.ShowAbout()
        link = next(widget for widget in main.aboutDialog.findChildren(QtWidgets.QWidget)
                    if widget.accessibleName() == "Licenses")
        QtTest.QTest.mouseClick(link, QtCore.Qt.MouseButton.LeftButton)
        app.processEvents()
        assert main.aboutDialog is None and main.licensesDialog.isVisible()
        text = main.licensesDialog.findChild(QtWidgets.QPlainTextEdit).toPlainText()
        assert "Photopea" in text and "SIL OPEN FONT LICENSE" in text and "Planner" in text
        assert "GNU GENERAL PUBLIC LICENSE" in text and "GPL-3.0-only" in text
        assert "Planner Original Graphics License" in text and "Planner Branding License" in text
        assert "D-DIN Condensed" in text and "Datto Inc." in text
        assert "Drafting Small Caps" in text and "Architects Daughter" in text and "Kimberly Geswein" in text
        for name in ("OFL.txt", "OFL-D-DIN.txt", "OFL-DraftingSmallCaps.txt", "FONTLOG.txt"):
            assert name in text
        assert "could not be loaded" not in text
        main.licensesDialog.close()
        main.ShowAbout()
        QtTest.QTest.keyClick(main.aboutDialog, QtCore.Qt.Key.Key_Escape)
        assert main.aboutDialog is None
        assert WorkflowState(main) == before
        helpWindow.close()
    print("About: layout, logo, dismissal, profile/licenses and help routing passed")


if __name__ == "__main__":
    Main()
