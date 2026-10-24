"""First-party docs stay organized, reachable and free of broken local links."""
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


def Main():
    root = Path(__file__).resolve().parents[1]
    helpRoot = root / "planner-main/docs/help"
    pages = {path.resolve() for directory in (root / "docs", helpRoot, root / "tools", root / "checks")
             for path in directory.rglob("*.md") if not any(part.startswith("tmp") for part in path.relative_to(directory).parts)}
    pages.update((root / name).resolve() for name in ("README.md", "CONTRIBUTING.md"))
    home = (root / "README.md").resolve()
    docs = (root / "docs").resolve()
    links = {}
    for path in sorted(pages):
        text = path.read_text(encoding = "utf-8")
        # Examples inside fenced code are data rather than navigable links.
        text = re.sub(r"^(```|~~~)[^\n]*\n.*?^\1[^\n]*$", "", text, flags = re.M | re.S)
        links[path] = []
        for destination in re.findall(r"!?\[[^\]]*\]\(([^\s)]+)\)", text):
            url = urlsplit(destination)
            if url.scheme or url.netloc or not url.path:
                continue
            target = (path.parent / unquote(url.path).replace("\\", "/")).resolve()
            if path.is_relative_to(helpRoot) and target == helpRoot / "about":
                continue  # The Help host routes this action to the standalone About GUI.
            assert target.exists(), (path.relative_to(root), destination)
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
