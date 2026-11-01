"""A source checkout contains the app, developer references and no private plans."""
from pathlib import Path
import re


def Main():
    root = Path(__file__).resolve().parents[1]
    app = root / "planner-main"
    assert (root / ".github/workflows/checks.yml").is_file()
    assert (root / "requirements-dev.txt").is_file()
    assert (root / "docs/parity/cases.json").is_file()
    assert (root / "demos/.gitkeep").is_file()
    assert not (app / "requirements-dev.txt").exists()
    assert (app / "help/README.md").is_file() and not (app / "docs").exists()
    assert not (app / "checks").exists() and not (app / "tools").exists()
    # These verified first-party releases use Node 24. Retired action runtimes
    # can fail before Python or any application regression check is launched.
    minimumVersions = {"actions/checkout": 6, "actions/setup-python": 6, "actions/upload-artifact": 6}
    for name in ("checks.yml", "windows-build.yml"):
        workflow = (root / ".github/workflows" / name).read_text(encoding = "utf-8")
        actions = re.findall(r"uses:\s*(actions/[\w-]+)@v(\d+)", workflow)
        for action, minimum in minimumVersions.items():
            versions = [int(version) for used, version in actions if used == action]
            assert versions and all(version >= minimum for version in versions), (name, action, versions)
    for name in ("rectangular_rooms", "angled_rooms", "dense_furnishings"):
        assert (root / "checks/fixtures/plans" / (name + ".plan")).is_file()
    assert (app / "main.py").is_file() and (app / "requirements.txt").is_file()
    print("Repository layout: self-contained app, external checks/tools/docs, synthetic fixtures and reserved demos passed")


if __name__ == "__main__":
    Main()
