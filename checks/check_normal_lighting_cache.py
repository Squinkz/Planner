"""Exact normal-lighting pixels for every RG pair and cached texture preparation."""
import math
import os
from pathlib import Path
import random
import sys
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtGui, QtWidgets
from planner_app.graphics import compositing


def PreviousLighting(normal, angle, highlights = 1, midtones = 1, shadows = 1):
    """Frozen per-pixel implementation from before native palette expansion."""
    source = normal.constBits()
    pixels = bytearray(normal.width() * normal.height() * 4)
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    colors = {}
    for offset in range(0, len(pixels), 4):
        red, green = source[offset], source[offset + 1]
        key = red * 256 + green
        color = colors.get(key)
        if color is None:
            nx, ny = red / 127.5 - 1, green / 127.5 - 1
            rotatedX = nx * cosine - ny * sine
            rotatedY = nx * sine + ny * cosine
            up, down = min(1, max(0, -rotatedY)), min(1, max(0, rotatedY))
            side = min(1, abs(rotatedX))
            up *= highlights
            down *= shadows
            midtone = 1 - .5 * side * midtones
            factor = (1 - down) * (1 - up) * midtone
            highlight = up * midtone
            alpha = 1 - factor
            value = round(255 * highlight / alpha) if alpha > 0 else 0
            color = bytes((value, value, value, round(255 * alpha)))
            colors[key] = color
        pixels[offset:offset + 4] = color
    return QtGui.QImage(bytes(pixels), normal.width(), normal.height(), normal.width() * 4,
                       QtGui.QImage.Format.Format_RGBA8888).copy()


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    assert "numpy" not in sys.modules, "Loading the editor's compositing module eagerly imported NumPy"
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "all-rg.png"
        pixels = bytes(channel for green in range(256) for red in range(256) for channel in (red, green, red ^ green, 255))
        normal = QtGui.QImage(pixels, 256, 256, 256 * 4, QtGui.QImage.Format.Format_RGBA8888).copy()
        assert normal.save(str(path))
        metadata = path.stat()
        stamp = (metadata.st_mtime_ns, metadata.st_size)
        compositing.NormalTextureLookup.cache_clear()
        compositing.NormalLightingTile.cache_clear()
        width, height, lookup, keys, normalX, normalY = compositing.NormalTextureLookup(path, stamp)
        assert os.environ["OPENBLAS_NUM_THREADS"] == "1"
        assert (width, height, lookup.size, keys.size) == (256, 256, 65536, 65536)
        assert lookup.dtype.name == "uint16" and lookup.nbytes == 2 * 65536
        assert normalX.dtype.name == normalY.dtype.name == "float64"
        assert lookup[0, 255] == 255 and lookup[255, 0] == 65280
        assert lookup[216, 0] == 0xD800 and lookup[220, 0] == 0xDC00
        lightingRandom = random.Random(30541)
        cases = [(0, 1, 1, 1), (37, .25, .5, .75), (90, 0, 1, 1), (180, 1, 0, 1),
                 (270, 1, 1, 0), (359.5, 0, 0, 0), (126, .5, .5, .5), (122.125, .1, .9, .333)]
        cases += [(lightingRandom.uniform(-720, 720), *(lightingRandom.random() for _ in range(3))) for _ in range(24)]
        import numpy as np
        with np.errstate(all = "raise"), patch.object(compositing, "LoadNormalTexture", side_effect = AssertionError("Lighting adjustment re-read the normal map")):
            for values in cases:
                actual = compositing.NormalLightingTile(path, stamp, *values)
                assert actual == PreviousLighting(normal, *values), values
                assert compositing.NormalTextureLookup(path, stamp)[2] is lookup
                assert compositing.NormalTextureLookup(path, stamp)[4] is normalX
        retainedTile = actual
        retainedPixels = bytes(actual.constBits())
        replacement = QtGui.QImage(13, 17, QtGui.QImage.Format.Format_RGBA8888)
        replacement.fill(QtGui.QColor(50, 180, 5))
        assert replacement.save(str(path))
        metadata = path.stat()
        changedStamp = (metadata.st_mtime_ns, metadata.st_size)
        assert changedStamp != stamp
        assert compositing.NormalLightingTile(path, changedStamp, 67, .2, .7, .9) == PreviousLighting(replacement, 67, .2, .7, .9)
        # Neither a cached lookup nor a returned tile may borrow a freed QImage
        # or temporary NumPy buffer when another map evicts the preparation.
        compositing.LoadNormalTexture.cache_clear()
        assert lookup[255, 255] == 65535 and normalX[65535] == 1
        assert bytes(retainedTile.constBits()) == retainedPixels
        assert compositing.NormalTextureLookup.cache_info().currsize == 1
        assert compositing.NormalLightingTile.cache_info().currsize == 1
    print("All 65,536 normal pairs match previous lighting exactly across 32 settings; lazy import, preparation reuse, buffer ownership and file replacement passed")


if __name__ == "__main__":
    Main()
