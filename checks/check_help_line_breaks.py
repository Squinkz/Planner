"""Markdown backslash breaks stay within paragraphs and leave code untouched."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.ui import help_viewer


def Main():
    app = QtWidgets.QApplication([])
    parent = QtWidgets.QWidget()
    window = help_viewer.HelpWindow(parent)
    slash = "\\"
    source = "\n".join((
        "# Break examples", "", "First" + slash, "**Second**" + slash, "[Third](other.md)", "",
        "Separate paragraph.", "", "Soft", "wrap.", "",
        "Escaped" + slash * 2, "continuation.", "",
        "Three" + slash * 3, "continued.", "",
        "Inline `literal" + slash, "code`.", "",
        "`Code`" + slash, "after code.", "",
        "> Quote first" + slash, "> Quote second", "",
        "```text", "fenced" + slash, "unchanged", "```", "",
        "    indented" + slash, "    unchanged", "",
        "- List first" + slash, "  List second", "- Another item", "",
        "A private character: \ue000", "", "![Image](image.png)", ""))
    with tempfile.TemporaryDirectory() as directory, patch.object(help_viewer, "helpDirectory", Path(directory)):
        folder = Path(directory)
        path = folder / "README.md"
        original = source.replace("\n", "\r\n").encode("utf-8")
        path.write_bytes(original)
        (folder / "other.md").write_text("# Other page\n\nReturn.", encoding = "utf-8")
        image = QtGui.QImage(20, 20, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtCore.Qt.GlobalColor.red)
        assert image.save(str(folder / "image.png"))
        assert window.ShowPage()
        document = window.browser.document()
        text = document.toRawText()
        assert "First\u2028Second\u2028Third" in text, repr(text)
        assert "Separate paragraph.\u2029Soft wrap." in text
        assert "Escaped\\ continuation." in text
        assert "Three\\\u2028continued." in text
        assert "literal\\ code" in text
        assert "Code\u2028after code." in text.replace("\u2009", ""), repr(text)
        assert "Quote first\u2028Quote second" in text
        assert "fenced\\\u2029unchanged" in text
        assert "indented\\\u2029unchanged" in text
        assert "List first\u2028List second" in text
        assert "A private character: \ue000" in text
        assert document.find("Second").charFormat().fontWeight() >= QtGui.QFont.Weight.Bold
        assert document.find("Third").charFormat().anchorHref() == "other.md"
        assert document.find("List second").block().textList() is not None
        assert document.find("First").block() == document.find("Third").block()
        assert document.find("First").block() != document.find("Separate paragraph.").block()
        assert document.find("literal").charFormat().fontFixedPitch()
        resource = window.browser.loadResource(QtGui.QTextDocument.ResourceType.ImageResource, QtCore.QUrl("image.png"))
        assert resource is not None
        assert path.read_bytes() == original
        window.ShowPage("other.md")
        window.browser.backward()
        assert window.browser.source().fileName() == "README.md"
        assert window.browser.document().toRawText() == text
        window.browser.forward()
        assert window.browser.source().fileName() == "other.md"
        assert path.read_bytes() == original
    window.close()
    print("PASS: backslash hard breaks, formatting, code, escaped slashes, lists, CRLF, resources and navigation")


if __name__ == "__main__":
    Main()
