"""Check furnishing bundle boundaries without compiling the application."""
from pathlib import Path
import runpy
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


def Main():
    root = Path(__file__).resolve().parents[1]
    build = runpy.run_path(str(root / "tools/build_windows.py"))
    hooks = ModuleType("PyInstaller.utils.hooks")
    hooks.copy_metadata = lambda package: []
    collected = {}

    def Analysis(*args, **kwargs):
        collected["data"] = kwargs["datas"]
        return SimpleNamespace(pure = [], scripts = [], binaries = [], datas = kwargs["datas"])

    with patch.dict(sys.modules, {"PyInstaller.utils.hooks": hooks}):
        runpy.run_path(str(root / "tools/Planner.spec"), init_globals = dict(
            SPECPATH = str(root / "tools"), Analysis = Analysis, PYZ = lambda *args: None,
            EXE = lambda *args, **kwargs: None, COLLECT = lambda *args, **kwargs: None))
    destinations = {destination for source, destination in collected["data"]}
    assert {"furnishings/definitions", "furnishings/images"} <= destinations
    assert not any("_user" in destination for destination in destinations)
    with tempfile.TemporaryDirectory() as temporary:
        source, distribution = Path(temporary) / "source", Path(temporary) / "dist"
        for name in ("definitions_user", "images_user", "definitions", "images"):
            directory = source / "furnishings" / name
            directory.mkdir(parents = True)
            (directory / "example.txt").write_text(name)
        for name in ("themes", "textures", "assets/fonts", "help"):
            (source / name).mkdir(parents = True)
        for name in ("definitions", "images"):
            (distribution / "_internal/furnishings" / name).mkdir(parents = True)
        manifest = build["CopyExternalResources"](source, distribution)
        assert set(manifest) == {"furnishings/definitions_user/example.txt", "furnishings/images_user/example.txt"}
        assert all((distribution / relative).read_bytes() == (source / relative).read_bytes() for relative in manifest)
        assert not (distribution / "furnishings/definitions").exists() and not (distribution / "furnishings/images").exists()
    print("PASS: spec bundles only defaults; distribution exposes only user furnishing folders")


if __name__ == "__main__":
    Main()
