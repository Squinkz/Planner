"""Readable help typography, borderless tables and responsive image layout."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from fixtures.parity_examples import ExampleWindow


def Main():
    with ExampleWindow() as (main, folder):
        main.ShowHelp()
        helpWindow = main.helpWindow
        browser = helpWindow.browser
        app = QtWidgets.QApplication.instance()
        browser.document().setMarkdown("# Heading\n\nFirst paragraph.\n\nSecond paragraph.\n\n"
                                       "## Subheading\n\n### Detail heading\n\n- First item\n- Second item\n\n"
                                       "| First | Second |\n|:---:|:---:|\n| One | Two |\n")
        originalTable = next(frame for frame in browser.document().rootFrame().childFrames() if isinstance(frame, QtGui.QTextTable))
        originalAlignments = {(row, column): originalTable.cellAt(row, column).firstCursorPosition().blockFormat().alignment()
                              for row in range(originalTable.rows()) for column in range(originalTable.columns())}
        helpWindow.StyleDocument()
        document = browser.document()
        em = document.defaultFont().pointSizeF() * browser.logicalDpiY() / 72
        heading = document.firstBlock()
        assert heading.blockFormat().topMargin() == 0
        assert heading.blockFormat().bottomMargin() == 20
        assert abs(heading.begin().fragment().charFormat().fontPointSize() - 22) < .01
        paragraph = document.find("First paragraph.").block()
        assert paragraph.blockFormat().bottomMargin() == 12
        assert paragraph.blockFormat().lineHeight() == em * 1.5
        assert paragraph.blockFormat().lineHeightType() == QtGui.QTextBlockFormat.LineHeightTypes.MinimumHeight.value
        secondHeading = document.find("Subheading").block()
        assert secondHeading.blockFormat().topMargin() == 28 and secondHeading.blockFormat().bottomMargin() == 14
        assert not heading.begin().fragment().charFormat().fontUnderline()
        assert not secondHeading.begin().fragment().charFormat().fontUnderline()
        assert not document.find("Detail heading").charFormat().fontUnderline()
        app.processEvents()
        capture = browser.viewport().grab().toImage()
        for block in (heading, secondHeading):
            rect = document.documentLayout().blockBoundingRect(block)
            x = round(rect.right() - 10)
            y = round(rect.bottom() + 5 - browser.verticalScrollBar().value())
            assert capture.pixelColor(x, y) != capture.pixelColor(x, y + 2), "Heading rule did not render"
        item = document.find("First item").block()
        assert item.textList() is not None and item.blockFormat().bottomMargin() == 6
        table = next(frame for frame in document.rootFrame().childFrames() if isinstance(frame, QtGui.QTextTable))
        assert table.format().border() == 0 and table.format().cellPadding() == 8
        assert table.format().cellSpacing() == 0
        for row in range(table.rows()):
            for column in range(table.columns()):
                cell = table.cellAt(row, column)
                cellFormat = cell.format().toTableCellFormat()
                assert all(getattr(cellFormat, side + "Border")() == 0 for side in ("top", "bottom", "left", "right"))
                block = cell.firstCursorPosition().block()
                assert block.blockFormat().topMargin() == block.blockFormat().bottomMargin() == 0
                assert block.blockFormat().alignment() == originalAlignments[row, column]
                if row == 0:
                    assert block.begin().fragment().charFormat().fontWeight() >= 600
        app.processEvents()
        before = document.toHtml()
        helpWindow.StyleDocument()
        assert document.toHtml() == before

        browser.document().setMarkdown("| | |\n|:---:|---:|\n| First | Second |\n| | |\n| Third | Fourth |\n")
        table = next(frame for frame in document.rootFrame().childFrames() if isinstance(frame, QtGui.QTextTable))
        alignment = table.cellAt(1, 1).firstCursorPosition().blockFormat().alignment()
        helpWindow.StyleDocument()
        assert table.rows() == 3 and table.format().headerRowCount() == 0
        assert table.cellAt(0, 0).firstCursorPosition().block().text() == "First"
        assert table.cellAt(0, 1).firstCursorPosition().blockFormat().alignment() == alignment
        assert table.cellAt(1, 0).firstCursorPosition().block().text() == "", "Empty body row was removed"
        before = document.toHtml()
        helpWindow.StyleDocument()
        assert document.toHtml() == before
        browser.document().setMarkdown("| Named | |\n|---|---|\n| First | Second |\n")
        helpWindow.StyleDocument()
        table = next(frame for frame in document.rootFrame().childFrames() if isinstance(frame, QtGui.QTextTable))
        assert table.rows() == 2 and table.cellAt(0, 0).firstCursorPosition().block().text() == "Named", "Partly populated header was removed"

        browser.document().setMarkdown("## Section\n\n| | |\n|---|---|\n| Item | Description |\n\nAfter table.\n")
        helpWindow.StyleDocument()
        app.processEvents()
        table = next(frame for frame in document.rootFrame().childFrames() if isinstance(frame, QtGui.QTextTable))
        assert table.format().topMargin() == document.firstBlock().blockFormat().bottomMargin()
        spacer = table.lastCursorPosition().block().next()
        assert spacer.text() == "" and spacer.blockFormat().lineHeight() == 1
        assert spacer.blockFormat().bottomMargin() == 0
        before = document.toHtml()
        helpWindow.StyleDocument()
        assert document.toHtml() == before

        # The user's real drawing guide contains images and a centered icon table.
        helpWindow.ShowPage("drawing.md")
        captures = workspace / "diagnostics" / "help-menu-20261018"
        captures.mkdir(exist_ok = True)
        for width, theme, filename in ((880, "Dark UI", "drawing-spaced-dark.png"),
                                        (880, "Light UI", "drawing-spaced-light.png"),
                                        (440, "Light UI", "drawing-spaced-small.png")):
            helpWindow.resize(width, 720)
            main.SetThemes(theme, "Dark Canvas", notify = False)
            app.processEvents()
            helpWindow.ResizeImages()
            app.processEvents()
            assert browser.horizontalScrollBar().maximum() == 0
            assert helpWindow.grab().save(str(captures / filename))
        main.SetThemes("Dark UI", "Dark Canvas", notify = False)
        helpWindow.close()
    print("Help typography: spacing, heading hierarchy, borderless padded tables, alignment, images and idempotence passed")


if __name__ == "__main__":
    Main()
