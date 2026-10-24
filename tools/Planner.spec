"""Windows folder bundle; editable resources are copied by build_windows.py."""
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH).resolve().parent
app = root / "planner-main"
assets = app / "assets"
data = [(str(path), "assets/" + path.name) for path in sorted(assets.iterdir())
        if path.is_dir() and path.name != "fonts"]
data += [(str(path), "assets") for path in sorted(assets.iterdir()) if path.is_file()]
data += [(str(app / "vendor"), "vendor"), (str(app / "startup.plan"), ".")]
licenseFiles = ("LICENSES.txt", "COPYING", "ASSET_LICENSE.txt", "BRANDING_LICENSE.txt")
data += [(str(app / name), ".") for name in licenseFiles]
for package in ("PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6"):
    data += copy_metadata(package)

analysis = Analysis([str(root / "tools/windows_entry.py")],
                    pathex = [str(app), str(root / "tools")], binaries = [], datas = data,
                    hiddenimports = [], hookspath = [str(root / "tools/pyinstaller_hooks")], runtime_hooks = [],
                    excludes = ["PyQt5", "PyQt6", "PySide2", "tkinter"], noarchive = False)
archive = PYZ(analysis.pure)
executable = EXE(archive, analysis.scripts, [], exclude_binaries = True,
                 name = "Planner", debug = False, bootloader_ignore_signals = False,
                 strip = False, upx = False, console = False,
                 icon = str(root / "build/windows/Planner.ico"))
collection = COLLECT(executable, analysis.binaries, analysis.datas,
                     strip = False, upx = False, name = "Planner")
