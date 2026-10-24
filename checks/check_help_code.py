"""Inline/fenced/indented code shading follows themes without changing content."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from fixtures.parity_examples import ExampleWindow
from planner_app.graphics.palette import themeColors
from planner_app.ui.help_viewer import inlinePaddingProperty


def Main():
    with ExampleWindow() as (main, folder):
        main.ShowHelp()
        window = main.helpWindow
        browser = window.browser
        document = browser.document()
        source = "# Code examples\n\nUse `Right-click` and **bold** text. Also `x\u2009y`.\n\n```python\nfirst = 1\nsecond = 2\n```\n\n    indented = 3\n\nOrdinary paragraph.\n"
        document.setMarkdown(source)
        window.StyleDocument()
        original = document.toPlainText()
        captures = workspace / "diagnostics" / "help-code-20261019"
        captures.mkdir(exist_ok = True)
        for theme in ("Dark UI", "Light UI"):
            main.SetThemes(theme, "Dark Canvas", notify = False)
            window.RefreshTheme()
            window.StyleDocument()
            QtWidgets.QApplication.processEvents()
            inline = document.find("Right-click").charFormat()
            color = inline.background().color()
            assert inline.fontFixedPitch() and inline.background().style() == QtCore.Qt.BrushStyle.SolidPattern
            assert color != QtGui.QColor(themeColors["fieldBackground"])
            plain = document.find("Ordinary paragraph.")
            assert plain.charFormat().background().style() == QtCore.Qt.BrushStyle.NoBrush
            assert plain.blockFormat().background().style() == QtCore.Qt.BrushStyle.NoBrush
            for text in ("first = 1", "second = 2", "indented = 3"):
                block = document.find(text).block()
                assert block.blockFormat().background().color() == color, text
                assert block.blockFormat().leftMargin() == block.blockFormat().rightMargin() == 10
            assert document.find("first = 1").blockFormat().bottomMargin() == 0
            assert document.find("second = 2").blockFormat().topMargin() == 0
            code = document.find("Right-click")
            for position in (code.selectionStart() - 1, code.selectionEnd()):
                padding = QtGui.QTextCursor(document)
                padding.setPosition(position)
                padding.setPosition(position + 1, QtGui.QTextCursor.MoveMode.KeepAnchor)
                assert padding.selectedText() == "\u2009" and padding.charFormat().boolProperty(inlinePaddingProperty)
            assert document.toPlainText().count("\u2009") == original.count("\u2009") + 4
            selection = QtGui.QTextCursor(document)
            selection.select(QtGui.QTextCursor.SelectionType.Document)
            browser.setTextCursor(selection)
            mime = browser.createMimeDataFromSelection()
            assert mime.text() == original  # Preserve authored thin spaces too.
            copied = QtGui.QTextDocument()
            copied.setHtml(mime.html())
            assert copied.toPlainText() == original
            selection.clearSelection()
            browser.setTextCursor(selection)
            before = document.toHtml()
            window.StyleDocument()
            window.RefreshTheme()
            assert document.toHtml() == before
            for width in (880, 440):
                window.resize(width, 600)
                QtWidgets.QApplication.processEvents()
                window.grab().save(str(captures / (theme.lower().replace(" ", "-") + f"-{width}.png")))
        window.ShowPage("drawing.md")
        assert document.find("Right-click").charFormat().background().style() == QtCore.Qt.BrushStyle.SolidPattern
    print("Help code: inline, fenced and indented shading; themes, spacing, idempotence and content preservation passed")


if __name__ == "__main__":
    Main()
