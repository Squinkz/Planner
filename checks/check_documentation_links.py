"""First-party docs stay organized, reachable and free of broken local links."""
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtGui, QtWidgets
from planner_app.help_anchors import HeadingAnchors


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    root = Path(__file__).resolve().parents[1]
    helpRoot = root / "planner-main/help"
    pages = {path.resolve() for directory in (root / "docs", helpRoot, root / "tools", root / "checks")
             for path in directory.rglob("*.md") if not any(part.startswith("tmp") for part in path.relative_to(directory).parts)}
    pages.update((root / name).resolve() for name in ("README.md", "CONTRIBUTING.md"))
    home = (root / "README.md").resolve()
    docs = (root / "docs").resolve()
    links = {}
    anchors = {}
    for path in sorted(pages):
        text = path.read_text(encoding = "utf-8")
        # Examples inside fenced code are data rather than navigable links.
        text = re.sub(r"^(```|~~~)[^\n]*\n.*?^\1[^\n]*$", "", text, flags = re.M | re.S)
        links[path] = []
        for destination in re.findall(r"!?\[[^\]]*\]\(([^\s)]+)\)", text):
            url = urlsplit(destination)
            if url.scheme or url.netloc:
                continue
            target = (path.parent / unquote(url.path).replace("\\", "/")).resolve() if url.path else path
            if path.is_relative_to(helpRoot) and target == helpRoot / "about":
                continue  # The Help host routes this action to the standalone About GUI.
            assert target.exists(), (path.relative_to(root), destination)
            if url.fragment and target.is_relative_to(helpRoot) and target.suffix.lower() == ".md":
                if target not in anchors:
                    document = QtGui.QTextDocument()
                    document.setMarkdown(target.read_text(encoding = "utf-8"))
                    anchors[target] = {name for block, name in HeadingAnchors(document)}
                assert unquote(url.fragment) in anchors[target], (path.relative_to(root), destination, "Unknown heading")
            if target in pages:
                links[path].append(target)
    visited, pending = set(), [home]
    while pending:
        page = pending.pop()
        if page not in visited:
            visited.add(page)
            pending.extend(links[page])
    assert visited == pages, [str(path.relative_to(root)) for path in pages - visited]
    print(f"Documentation: {len(pages)} organized first-party Markdown pages; local links and reachability passed")


if __name__ == "__main__":
    Main()
