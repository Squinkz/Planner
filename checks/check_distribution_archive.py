"""Versioned Windows archives preserve the complete distribution directory."""
from pathlib import Path
import runpy
import sys
import tempfile
import zipfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from planner_app.version import appVersion, releaseStage, version, displayVersion


def Main():
    pack = runpy.run_path(str(root / "tools/build_windows.py"))["PackageDistribution"]
    assert version == (f"{appVersion}-{releaseStage}" if releaseStage else appVersion)
    assert displayVersion == (f"{releaseStage.capitalize()} {appVersion}" if releaseStage else appVersion)
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        build = folder / "build"
        distribution = folder / "dist/Planner"
        build.mkdir()
        distribution.mkdir(parents = True)
        files = {"Planner.exe": b"test executable", "assets/fonts/OFL.txt": b"font notice",
                 "furnishings/test.json": b"{}", "_internal/COPYING": b"license"}
        for name, data in files.items():
            path = distribution / name
            path.parent.mkdir(parents = True, exist_ok = True)
            path.write_bytes(data)
        for packageVersion in (version, "1.0.0"):
            for repeat in range(2):
                archive = pack(distribution, build, packageVersion)
                assert archive == folder / "dist" / f"Planner-{packageVersion}-Windows.zip"
                assert not (build / archive.name).exists()
                with zipfile.ZipFile(archive) as zipped:
                    actual = {entry.filename: zipped.read(entry) for entry in zipped.infolist() if not entry.is_dir()}
                assert actual == {"Planner/" + name: data for name, data in files.items()}
        assert (folder / "dist" / f"Planner-{version}-Windows.zip").is_file()
    print("Distribution archives: shared version, prerelease/stable filenames, replacement and complete folder contents passed")


if __name__ == "__main__":
    Main()
