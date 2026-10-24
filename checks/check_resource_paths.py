"""Source and frozen builds resolve editable resources independently of cwd."""
from pathlib import Path
import runpy
import sys
from unittest.mock import patch


def Main():
    app = Path(__file__).resolve().parents[1] / "planner-main"
    source = runpy.run_path(str(app / "planner_app/paths.py"))
    assert source["appDirectory"] == source["externalDirectory"] == app
    executable = app.parent / "dist/Planner/Planner.exe"
    with patch.object(sys, "frozen", True, create = True), patch.object(sys, "executable", str(executable)):
        frozen = runpy.run_path(str(app / "planner_app/paths.py"))
    assert frozen["appDirectory"] == app and frozen["externalDirectory"] == executable.parent
    assert frozen["assetsDirectory"] == app / "assets"
    for name, relative in (("furnishingsDirectory", "furnishings"), ("fontsDirectory", "assets/fonts"),
                           ("themesDirectory", "themes"), ("texturesDirectory", "textures"), ("helpDirectory", "docs/help")):
        assert source[name] == app / relative
        assert frozen[name] == executable.parent / relative
    print("Resource paths: external editable directories, internal assets and unchanged source layout passed")


if __name__ == "__main__":
    Main()
