"""Thumbnail reuse, file/content edits, semantic missing paint, fonts and bounds."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtWidgets
from planner_app.graphics import palette, furnishing_thumbnails
from planner_app.graphics.furnishing_thumbnails import FurnishingThumbnailCache


def Main():
    app = QtWidgets.QApplication([])
    cache = FurnishingThumbnailCache(limit = 3, byteLimit = 100000)
    originalColors, originalFont = dict(palette.themeColors), palette.labelFont
    source = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80"><rect x="5" y="5" width="70" height="70" fill="white" stroke="black"/></svg>'
    try:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "icon.svg"
            path.write_bytes(source)
            definition = {"key": "fixture", "width": 80, "length": 80, "iconPath": path}
            with patch.object(furnishing_thumbnails, "FurnishingRenderer", wraps = furnishing_thumbnails.FurnishingRenderer) as renderer:
                icon = cache.Icon(definition)
                assert cache.Icon(dict(definition)).cacheKey() == icon.cacheKey()
                palette.themeColors["canvas"] = "#123456"
                palette.themeColors["missing"] = "#654321"
                palette.labelFont = "Courier New"
                assert cache.Icon(definition).cacheKey() == icon.cacheKey()
                assert renderer.call_count == 1, "Unrelated canvas changes recreated a thumbnail"
                palette.themeColors["icon"] = "#ff0000"
                recolored = cache.Icon(definition)
                assert recolored.cacheKey() != icon.cacheKey()
                palette.themeColors["icon"] = originalColors["icon"]
                assert cache.Icon(definition).cacheKey() == icon.cacheKey(), "Returning to a theme missed the cache"
                # Detect same-size external edits even when mtime is unchanged.
                stamp = path.stat()
                path.write_bytes(source.replace(b'fill="white"', b'fill="black"'))
                os.utime(path, ns = (stamp.st_atime_ns, stamp.st_mtime_ns))
                changed = cache.Icon(definition)
                assert changed.cacheKey() != icon.cacheKey()
                assert changed.pixmap(80, 80).toImage() != icon.pixmap(80, 80).toImage()
                definition["graphicData"] = source.replace(b'<rect ', b'<rect data-theme-outline="missing" ')
                missing = cache.Icon(definition)
                palette.themeColors["missing"] = "#ff00ff"
                changedMissing = cache.Icon(definition)
                assert missing.pixmap(80, 80).toImage() != changedMissing.pixmap(80, 80).toImage()
                definition["graphicData"] = source.replace(b'</svg>', b'<text x="20" y="40">ABC</text></svg>')
                lettering = cache.Icon(definition)
                palette.labelFont = "Noto Sans"
                assert cache.Icon(definition).cacheKey() != lettering.cacheKey()
                definition["width"] = 160
                assert cache.Icon(definition).cacheKey() != lettering.cacheKey()
                assert cache.Icon(definition, size = 40).pixmap(40, 40).width() == 40
                for index in range(10):
                    definition["graphicData"] = source.replace(b'</svg>', f'<!-- {index} --></svg>'.encode())
                    cache.Icon(definition)
                    assert len(cache.icons) <= cache.limit and cache.byteCount <= cache.byteLimit
                    assert len(cache.sources) <= cache.limit and cache.sourceBytes <= cache.byteLimit // 3
                # Discarding oversized variants still returns usable artwork.
                tiny = FurnishingThumbnailCache(byteLimit = 100)
                assert not tiny.Icon(definition).isNull() and not tiny.icons
                assert not icon.pixmap(80, 80).isNull(), "Eviction invalidated a live Qt icon"
    finally:
        palette.themeColors.clear()
        palette.themeColors.update(originalColors)
        palette.labelFont = originalFont
    print("PASS: bounded thumbnail reuse, semantic dependencies, edited assets, fonts and dimensions")


if __name__ == "__main__":
    Main()
