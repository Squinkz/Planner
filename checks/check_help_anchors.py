"""Automatic heading names, section navigation, history and unchanged typography."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.help_anchors import HeadingAnchors
from planner_app.ui import help_viewer
from check_help_docs import CheckHelpLink


def Main():
    app = QtWidgets.QApplication([])
    headings = [("## Installation", "installation"), ("### What's included?", "whats-included"),
                ("## Installation", "installation-1"), ("## Installation-1", "installation-1-1"),
                ("## Installation", "installation-2"),
                ("## **Adding** `textures` and [fonts](other.md)", "adding-textures-and-fonts"),
                ("## Café & Ελληνικά", "café--ελληνικά"), ("## X_y -- Z", "x_y----z"),
                ("## 🛠 Tools!", "-tools"), ("Underlined heading\n------------------", "underlined-heading")]
    padding = "\n\n".join(f"Paragraph {index}." for index in range(22))
    source = "# Anchor examples\n\n[Installation](#installation)\n\n" + padding
    for heading, name in headings:
        source += "\n\n" + heading + "\n\n" + padding
    source += "\n\n```md\n## Not a heading\n```\n\n" + padding
    document = QtGui.QTextDocument()
    document.setMarkdown(source)
    expected = ["anchor-examples"] + [name for heading, name in headings]
    assert [name for block, name in HeadingAnchors(document)] == expected
    # Independent expected examples exercise punctuation, Unicode, formatting,
    # duplicate suffix collisions, all heading levels and code-fence exclusion.
    document.setMarkdown("# One\n\n## Two\n\n### Three\n\n#### Four\n\n##### Five\n\n###### Six")
    assert [name for block, name in HeadingAnchors(document)] == ["one", "two", "three", "four", "five", "six"]
    with tempfile.TemporaryDirectory() as directory, patch.object(help_viewer, "helpDirectory", Path(directory)):
        root = Path(directory)
        root = root.resolve()
        # Use canonical paths on Windows hosted runners, whose TEMP can be an
        # 8.3 alias even though Qt returns the long form.
        (root / "README.md").write_text(source, encoding = "utf-8")
        (root / "other.md").write_text("# Other page\n\n" + padding + "\n\n## Target section\n\n" + padding,
                                       encoding = "utf-8")
        pages = {root / "README.md", root / "other.md"}
        anchors = {root / "README.md": set(expected), root / "other.md": {"other-page", "target-section"}}
        for destination in ("#installation", "#installation-1", "#caf%C3%A9--%CE%B5%CE%BB%CE%BB%CE%B7%CE%BD%CE%B9%CE%BA%CE%AC",
                            "other.md#target-section"):
            assert CheckHelpLink(root / "README.md", destination, root, pages, anchors) in pages
        for destination in ("#missing", "other.md#missing", "missing.md#installation", "../outside.md#installation",
                            "other.md?query=1#target-section", "#Installation"):
            try:
                CheckHelpLink(root / "README.md", destination, root, pages, anchors)
            except AssertionError:
                pass
            else:
                raise AssertionError(f"Invalid section link was accepted: {destination}")
        parent = QtWidgets.QWidget()
        window = help_viewer.HelpWindow(parent)
        window.resize(780, 500)
        assert window.ShowPage()
        window.show()
        app.processEvents()
        browser, bar = window.browser, window.browser.verticalScrollBar()
        names = []
        block = browser.document().begin()
        while block.isValid():
            if block.blockFormat().headingLevel():
                fragment = block.begin().fragment()
                names.extend(fragment.charFormat().anchorNames())
                assert fragment.charFormat().anchorHref() == ""
            block = block.next()
        assert names == expected, (names, expected)
        beforeText = browser.toPlainText()
        beforeSize = browser.document().size()
        firstColor = browser.document().begin().begin().fragment().charFormat().foreground().color()
        positions = []
        for heading, name in headings:
            window.OpenLink(QtCore.QUrl("#" + name))
            app.processEvents()
            block = next(block for block, anchor in HeadingAnchors(browser.document()) if anchor == name)
            top = browser.document().documentLayout().blockBoundingRect(block).top()
            assert abs(bar.value() - top) <= 2, (name, bar.value(), top)
            assert browser.source().fragment() == name
            positions.append(bar.value())
        assert positions == sorted(positions) and len(set(positions)) == len(headings)
        assert browser.toPlainText() == beforeText and browser.document().size() == beforeSize
        assert browser.document().begin().begin().fragment().charFormat().foreground().color() == firstColor
        # Cross-page fragments, native history, Home and repeated theme styling.
        window.OpenLink(QtCore.QUrl("other.md#target-section"))
        app.processEvents()
        assert Path(browser.source().toLocalFile()).resolve() == (root / "other.md").resolve() and bar.value() > 0
        browser.backward()
        app.processEvents()
        assert browser.source().fragment() == "underlined-heading" and abs(bar.value() - positions[-1]) <= 2
        browser.forward()
        app.processEvents()
        assert browser.source().fragment() == "target-section" and bar.value() > 0
        window.RefreshTheme()
        window.OpenLink(QtCore.QUrl("README.md#installation-1"))
        app.processEvents()
        assert abs(bar.value() - positions[2]) <= 2
        window.homeButton.click()
        app.processEvents()
        assert not browser.source().fragment() and bar.value() == 0
        assert [name for block, name in HeadingAnchors(browser.document())] == expected
        window.close()
        parent.close()
    print("PASS: GitHub-style heading names, section scrolling, cross-page links, Unicode, history and typography")


if __name__ == "__main__":
    Main()
