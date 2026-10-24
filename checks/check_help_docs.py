"""Portable help authoring contract and complete linked guide."""
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


def Main():
    helpRoot = Path(__file__).resolve().parents[1] / "planner-main" / "docs" / "help"
    pages = {path.resolve() for path in helpRoot.glob("*.md")}
    assert len(pages) >= 10
    links = {}
    for path in pages:
        text = path.read_text(encoding = "utf-8")
        assert text.startswith("# ") and len(re.findall(r"^# ", text, re.M)) == 1, path
        for emphasis in re.finditer(r"\*\*(.*?)\*\*", text, re.S):
            assert not re.search(r"\b(?:Ctrl|Shift|Alt|Escape|Enter|F1|(?:left|right|middle|double)-click|(?:left|right|middle)-drag|mouse wheel)\b",
                                 emphasis.group(1), re.I), (path, "Use inline code for input gestures", emphasis.group(1))
        for pattern in (r"<[/!A-Za-z][^>]*>", r"^\s*[-*] \[[ xX]\]",
                        r"\[\[", r"::\w+\{", r"[A-Za-z]:\\", r"(?:python|pip|npm) (?:-m|install|main\.)"):
            assert not re.search(pattern, text, re.M), (path, pattern)
        links[path] = []
        for match in re.finditer(r"(!?)\[[^\]]+\]\(([^)]+)\)", text):
            image, destination = match.groups()
            url = urlsplit(destination)
            assert not url.scheme and not url.netloc and not url.fragment and not url.query, (path, destination)
            target = (path.parent / unquote(url.path).replace("\\", "/")).resolve()
            if target == helpRoot.resolve() / "about":
                continue  # Explicit GUI navigation action, exercised by the About check.
            if image:
                assert target.is_relative_to(helpRoot.resolve()) and target.is_file(), (path, destination)
                continue
            assert target.is_relative_to(helpRoot.resolve()) and target in pages, (path, destination)
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
