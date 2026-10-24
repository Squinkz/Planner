"""Repeated semantic artwork reuses engines without sharing mutable wrappers."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtGui, QtWidgets
from planner_app.graphics import icons, palette
from planner_app.graphics.theme import ApplyApplicationTheme, MaterialIcon, WallPresetIcon


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    retained = {}
    for cycle in range(4):
        for theme in ("Dark UI", "Light UI", "Neutral UI"):
            palette.SetThemes(uiTheme = theme)
            for repeat in range(20):
                artwork = (icons.UiIcon("search"), icons.GroupModeIcon(), WallPresetIcon(0), MaterialIcon("Brick"))
                for index, icon in enumerate(artwork):
                    icon.pixmap(24, 24)
                    key = (theme, index)
                    if key in retained:
                        assert icon is not retained[key]
                        assert icon.cacheKey() == retained[key].cacheKey()
                    else:
                        retained[key] = icon
        counts = (len(icons.iconSources), len(icons.pixmapSources), len(icons.themeIconCache))
        if cycle == 0:
            baseline = counts
        else:
            assert counts == baseline, (baseline, counts)
    original = retained[("Dark UI", 0)]
    originalKey = original.cacheKey()
    copy = QtGui.QIcon(original)
    pixmap = QtGui.QPixmap(24, 24)
    pixmap.fill(QtGui.QColor("magenta"))
    copy.addPixmap(pixmap)
    assert copy.cacheKey() != originalKey
    assert original.cacheKey() == originalKey
    palette.SetThemes(uiTheme = "Light UI")
    refreshed = icons.iconSources[originalKey]()
    assert refreshed.cacheKey() == icons.UiIcon("search").cacheKey()
    assert refreshed.cacheKey() != originalKey
    assert all(not icon.isNull() and icon.cacheKey() in icons.iconSources for icon in retained.values())


if __name__ == "__main__":
    Main()
