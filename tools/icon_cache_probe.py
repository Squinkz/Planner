"""Measure source-registry growth after repeated icon/theme cycles; no leak inference."""
import json
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parent.parent
(root / "diagnostics").mkdir(exist_ok = True)
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtWidgets
from planner_app.graphics import icons, palette
from planner_app.graphics.theme import ApplyApplicationTheme, WallPresetIcon, MaterialIcon


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    samples = []
    retainedCopies = []
    for cycle in range(4):
        for uiTheme in ("Dark UI", "Light UI", "Neutral UI"):
            palette.SetThemes(uiTheme = uiTheme)
            for repeat in range(50):
                for icon in (icons.UiIcon("search"), icons.GroupModeIcon(), WallPresetIcon(0), MaterialIcon("Brick")):
                    icon.pixmap(24, 24)
                    if cycle == 0 and repeat == 0:
                        retainedCopies.append(icon)
        samples.append({"cycle": cycle + 1, "iconSources": len(icons.iconSources),
                        "pixmapSources": len(icons.pixmapSources), "svgVariants": len(icons.uiIconCache)})
    assert all(not icon.isNull() and icons.iconSources.get(icon.cacheKey()) is not None for icon in retainedCopies)
    report = {"cycles": samples, "retainedCopies": len(retainedCopies),
              "note": "Registry counts are not process RSS or proof of a memory leak."}
    (root / "diagnostics/icon-cache-growth-20261008.json").write_text(json.dumps(report, indent = 2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    Main()
