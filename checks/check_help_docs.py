"""Portable help authoring contract and complete linked guide."""
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtGui, QtWidgets
from planner_app.help_anchors import HeadingAnchors


def CheckHelpLink(path, destination, helpRoot, pages, anchors, image = False):
    url = urlsplit(destination)
    assert not url.scheme and not url.netloc and not url.query, (path, destination)
    target = (path.parent / unquote(url.path).replace("\\", "/")).resolve() if url.path else path
    if target == helpRoot.resolve() / "about":
        assert not url.fragment and not image, (path, destination)
        return None  # Navigation action, exercised by the About check.
    if image:
        assert not url.fragment, (path, destination)
        assert target.is_relative_to(helpRoot.resolve()) and target.is_file(), (path, destination)
        return None
    assert target.is_relative_to(helpRoot.resolve()) and target in pages, (path, destination)
    if url.fragment:
        assert unquote(url.fragment) in anchors[target], (path, destination, "Unknown heading")
    return target


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    helpRoot = Path(__file__).resolve().parents[1] / "planner-main" / "help"
    pages = {path.resolve() for path in helpRoot.rglob("*.md")}
    assert len(pages) >= 10
    anchors = {}
    for path in pages:
        document = QtGui.QTextDocument()
        document.setMarkdown(path.read_text(encoding = "utf-8"))
        anchors[path] = {name for block, name in HeadingAnchors(document)}
    links = {}
    for path in pages:
        text = path.read_text(encoding = "utf-8")
        assert text.startswith("# ") and len(re.findall(r"^# ", text, re.M)) == 1, path
        # Code examples may contain HTML tags, links and command lines as data.
        prose = re.sub(r"^(`{3,}|~{3,})[^\n]*\n.*?^\1[^\n]*$", "", text, flags = re.M | re.S)
        markup = re.sub(r"(`+).*?\1", "", prose, flags = re.S)
        for emphasis in re.finditer(r"\*\*(.*?)\*\*", markup, re.S):
            assert not re.search(r"\b(?:Ctrl|Shift|Alt|Escape|Enter|F1|(?:left|right|middle|double)-click|(?:left|right|middle)-drag|mouse wheel)\b",
                                 emphasis.group(1), re.I), (path, "Use inline code for input gestures", emphasis.group(1))
        for pattern in (r"<[/!A-Za-z][^>]*>", r"^\s*[-*] \[[ xX]\]",
                        r"\[\[", r"::\w+\{", r"[A-Za-z]:\\", r"(?:python|pip|npm) (?:-m|install|main\.)"):
            assert not re.search(pattern, markup, re.M), (path, pattern)
        links[path] = []
        for match in re.finditer(r"(!?)\[[^\]]+\]\(([^)]+)\)", prose):
            image, destination = match.groups()
            target = CheckHelpLink(path, destination, helpRoot, pages, anchors, image = bool(image))
            if target is not None:
                links[path].append(target)
    home = (helpRoot / "README.md").resolve()
    reached, pending = set(), [home]
    while pending:
        page = pending.pop()
        if page not in reached:
            reached.add(page)
            pending.extend(links[page])
    assert reached == pages, pages - reached
    for page in pages - {home}:
        assert home in links[page], page
    print(f"Help: {len(pages)} portable pages, all links valid and reachable")


if __name__ == "__main__":
    Main()
