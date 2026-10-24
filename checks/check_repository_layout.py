"""A source checkout contains the app, developer references and no private plans."""
from pathlib import Path


def Main():
    root = Path(__file__).resolve().parents[1]
    app = root / "planner-main"
    assert (root / ".github/workflows/checks.yml").is_file()
    assert (root / "requirements-dev.txt").is_file()
    assert (root / "docs/parity/cases.json").is_file()
    assert (root / "demos/.gitkeep").is_file()
    assert not (app / "requirements-dev.txt").exists()
    assert {path.name for path in (app / "docs").iterdir()} == {"help"}
    assert not (app / "checks").exists() and not (app / "tools").exists()
    for name in ("rectangular_rooms", "angled_rooms", "dense_furnishings"):
        assert (root / "checks/fixtures/plans" / (name + ".plan")).is_file()
    assert (app / "main.py").is_file() and (app / "requirements.txt").is_file()
    print("Repository layout: self-contained app, external checks/tools/docs, synthetic fixtures and reserved demos passed")


if __name__ == "__main__":
    Main()
