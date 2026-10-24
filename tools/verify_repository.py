"""Review publishable files without adding local workspace output to Git."""
from collections import Counter
from pathlib import Path
import subprocess


def Main():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                            cwd = root, capture_output = True, check = True)
    paths = sorted(set(result.stdout.decode("utf-8").split("\0")) - {""})
    allowed = {"planner-main", "checks", "tools", "docs", "demos", ".github"}
    metadata = {".gitignore", ".gitattributes", "README.md", "CONTRIBUTING.md", "requirements-dev.txt",
                "LICENSE", "LICENSE.txt", "CHANGELOG.md", "requirements-build.txt"}
    total = 0
    counts = Counter()
    for name in paths:
        path = Path(name)
        if path.parts[0] not in allowed and name not in metadata:
            raise ValueError(f"Unexpected repository file: {name}")
        source = root / path
        size = source.stat().st_size
        if size > 50 * 1024 * 1024:
            raise ValueError(f"Review large repository file: {name} ({size:,} bytes)")
        if any(part == "__pycache__" or part.startswith("tmp") for part in path.parts):
            raise ValueError(f"Generated files must not be published: {name}")
        total += size
        counts[path.parts[0]] += 1
    print(f"{len(paths):,} selected files, {total / 1024 / 1024:.1f} MiB. No unexpected roots, caches or files above 50 MiB.")
    for name, count in sorted(counts.items()):
        print(f"  {name}: {count}")


if __name__ == "__main__":
    Main()
