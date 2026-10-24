"""Unused custom variants retire while widget-held Qt copies remain refreshable."""
import gc
import json
import os
import sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtGui, QtWidgets
from planner_app.graphics import icons


def Main():
    app = QtWidgets.QApplication([])
    # Exercise the production retirement policy with small limits so several
    # complete turnover cycles fit the ordinary regression time budget.
    icons.artworkCacheLimit = 32
    icons.sourceCacheLimit = 64
    icons.pathCacheLimit = 64
    button = QtWidgets.QPushButton()
    original = icons.UiIcon("search")
    key = original.cacheKey()
    button.setIcon(QtGui.QIcon(original))
    label = QtWidgets.QLabel()
    label.setPixmap(original.pixmap(24, 24))
    pixelKey = label.pixmap().cacheKey()
    stylesheet = QtWidgets.QPushButton()
    path = icons.UiIconPath("search", "#fedcba")
    source = path.read_bytes()
    stylesheet.setStyleSheet(f'image: url("{path.as_posix()}");')
    del original
    samples = []
    for cycle in range(3):
        for index in range(250):
            icon = icons.UiIcon("search", f"#{0x100000 + cycle * 250 + index:06x}")
        del icon
        gc.collect()
        icons.PruneArtworkCaches()
        assert key in icons.iconSources and pixelKey in icons.pixmapSources
        assert not button.icon().pixmap(24, 24).isNull()
        assert path.read_bytes() == source
        assert len(icons.themeIconCache) <= icons.artworkCacheLimit
        samples.append({"sources": len(icons.iconSources), "paths": len(icons.uiIconCache),
                        "files": len(list(Path(icons.uiIconCacheDirectory.name).glob("*.svg")))})
    assert samples[-1]["sources"] <= samples[-2]["sources"] + 10
    assert samples[-1]["paths"] <= samples[-2]["paths"] + 10
    assert samples[-1]["files"] == samples[-1]["paths"]
    refreshed = icons.iconSources[key]()
    assert not refreshed.isNull()
    (Path(__file__).resolve().parent.parent / "diagnostics/artwork-lifetime-20261008.json").write_text(json.dumps(samples, indent = 2) + "\n")


if __name__ == "__main__":
    Main()
