"""Build, verify and ZIP Planner with editable resources outside the bundle."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile


def PackageDistribution(distribution, build, version):
    name = f"Planner-{version}-Windows"
    archive = Path(shutil.make_archive(str(build / name), "zip", root_dir = distribution.parent, base_dir = distribution.name))
    destination = distribution.parent / (name + ".zip")
    archive.replace(destination)
    return destination


def CopyExternalResources(source, distribution):
    external = ("furnishings/definitions_user", "furnishings/images_user", "themes", "textures", "assets/fonts", "help")
    manifest = {}
    for relative in external:
        shutil.copytree(source / relative, distribution / relative,
                        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "DO.NOT.EDIT.ANYTHING.IN.THIS.FOLDER"))
        assert not (distribution / "_internal" / relative).exists(), relative + " was accidentally bundled"
        for path in sorted((distribution / relative).rglob("*")):
            if path.is_file():
                name = path.relative_to(distribution).as_posix()
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                assert hashlib.sha256((source / name).read_bytes()).hexdigest() == digest
                manifest[name] = digest
    for name in ("definitions", "images"):
        assert (distribution / "_internal/furnishings" / name).is_dir(), "Missing bundled furnishings: " + name
        assert not (distribution / "furnishings" / name).exists(), "Default furnishings must be internal: " + name
    return manifest


def Main():
    if sys.platform != "win32":
        raise SystemExit("Build the Windows executable on Windows.")
    root = Path(__file__).resolve().parents[1]
    source = root / "planner-main"
    version = runpy.run_path(str(source / "planner_app/version.py"))["version"]
    build = root / "build/windows"
    distribution = root / "dist/Planner"
    # PyInstaller replaces its generated output. Reject symlinked destinations
    # so replacement stays inside this repository's build/dist directories.
    for directory, parent in ((build, root / "build"), (distribution, root / "dist")):
        if not directory.resolve().is_relative_to(root) or parent.is_symlink() or directory.is_symlink():
            raise SystemExit(f"Build destination is outside the repository: {directory}")
    build.mkdir(parents = True, exist_ok = True)
    try:
        import PyInstaller
    except ImportError:
        raise SystemExit("Install build dependencies first: python -m pip install -r requirements-build.txt")
    expected = "6.22.3"
    if PyInstaller.__version__ != expected:
        raise SystemExit(f"Expected PyInstaller {expected}; install requirements-build.txt.")
    from PySide6 import QtCore, QtGui, QtSvg
    app = QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
    renderer = QtSvg.QSvgRenderer(str(source / "assets/planner.svg"))
    if not renderer.isValid():
        raise SystemExit("Cannot read the application icon.")
    icon = QtGui.QImage(256, 256, QtGui.QImage.Format.Format_ARGB32)
    icon.fill(QtCore.Qt.GlobalColor.transparent)
    with QtGui.QPainter(icon) as painter:
        renderer.render(painter)
    if not icon.save(str(build / "Planner.ico"), "ICO"):
        raise SystemExit("Cannot write the executable icon.")
    environment = dict(os.environ, PYINSTALLER_CONFIG_DIR = str(build / "cache"))
    windows = Path(os.environ["SystemRoot"])
    # Dependency discovery must not pick unrelated DLLs from graphics tools or
    # other applications on PATH (for example a different ICU implementation).
    environment["PATH"] = os.pathsep.join((str(Path(sys.executable).parent), sys.base_prefix,
                                           str(windows / "System32"), str(windows)))
    for name in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH", "QML_IMPORT_PATH"):
        environment.pop(name, None)
    print("Building Planner.exe...", flush = True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(root / "dist"), "--workpath", str(build / "pyinstaller"),
                    str(root / "tools/Planner.spec")], cwd = root, env = environment, check = True)
    manifest = CopyExternalResources(source, distribution)
    (build / "external-resources.json").write_text(json.dumps(manifest, indent = 2), encoding = "utf-8")
    reportPath = build / "smoke-report.json"
    reportPath.unlink(missing_ok = True)
    print("Checking the packaged app, external resources, help, PNG/SVG and optimized PNG...", flush = True)
    with tempfile.TemporaryDirectory(prefix = "smoke-", dir = build) as folder:
        environment = dict(environment, QT_QPA_PLATFORM = "offscreen", QT_QPA_FONTDIR = str(distribution / "assets/fonts"),
                           PLANNER_SESSION_PATH = str(Path(folder) / "session.json"),
                           PLANNER_STARTUP_PATH = str(Path(folder) / "startup.plan"),
                           PLANNER_PREFERENCES_PATH = str(Path(folder) / "preferences.json"))
        environment["PATH"] = os.pathsep.join((str(windows / "System32"), str(windows)))
        result = subprocess.run([str(distribution / "Planner.exe"), "--smoke-test", str(reportPath)],
                                cwd = folder, env = environment, timeout = 120)
    report = json.loads(reportPath.read_text(encoding = "utf-8")) if reportPath.exists() else {}
    if result.returncode or not report.get("ok"):
        raise SystemExit("Packaged smoke test failed: " + report.get("error", "No smoke report was produced."))
    archive = PackageDistribution(distribution, build, version)
    print(f"Built {distribution / 'Planner.exe'}", flush = True)
    print(f"ZIP: {archive}", flush = True)
    print(f"Verified {len(manifest)} external resource files. Report: {reportPath}", flush = True)


if __name__ == "__main__":
    Main()
