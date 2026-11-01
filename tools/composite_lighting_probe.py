"""Compare exact lighting pixels and CPU frame time with four A4 sheets at 300 PPI."""
import argparse
import codecs
import ctypes
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import statistics
import sys
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
if sys.platform == "win32":
    ctypes.windll.kernel32.SetErrorMode(3)
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow
from check_normal_lighting_cache import PreviousLighting
from planner_app.ui.main_window import MainWindow
from planner_app.project_codec import DecodeProject
from planner_app.graphics import compositing
from planner_app.paths import texturesDirectory


@lru_cache(maxsize = 1)
def PreviousLookup(path, stamp):
    normal = compositing.LoadNormalTexture(path, stamp)
    source = normal.constBits()
    keys = bytearray(normal.sizeInBytes())
    keys[0::4] = source[0::4]
    keys[1::4] = source[1::4]
    lookup = keys.decode("utf-32-le", "surrogatepass")
    return normal.width(), normal.height(), lookup, tuple(map(ord, set(lookup)))


@lru_cache(maxsize = 1)
def PreviousTile(path, stamp, angle, highlights = 1, midtones = 1, shadows = 1):
    """Frozen standard-library palette implementation immediately before NumPy."""
    width, height, lookup, keys = PreviousLookup(path, stamp)
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    colors = {}
    for key in keys:
        red, green = key & 255, key >> 8
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
        colors[key] = bytes((value, value, value, round(255 * alpha)))
    pixels = codecs.charmap_encode(lookup, "strict", colors)[0]
    return QtGui.QImage(pixels, width, height, width * 4, QtGui.QImage.Format.Format_RGBA8888).copy()


@lru_cache(maxsize = 1)
def OriginalTile(path, stamp, angle, highlights = 1, midtones = 1, shadows = 1):
    return PreviousLighting(compositing.LoadNormalTexture(path, stamp), angle, highlights, midtones, shadows)


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--baseline", choices = ("palette", "original"), default = "palette")
    args = parser.parse_args()
    previous = PreviousTile if args.baseline == "palette" else OriginalTile
    project = json.loads((Path(os.environ["LOCALAPPDATA"]) / "Planner/session.json").read_text(encoding = "utf-8-sig"))["project"]
    project.pop("history", None)
    project.pop("activityLog", None)
    current = compositing.NormalLightingTile
    result = dict(baseline = args.baseline, pages = 4, paper = "A4", ppi = 300, viewport = [1000, 800], cases = {})
    with patch.object(MainWindow, "show", lambda self: None), ExampleWindow() as (main, folder):
        v, panel = main.viewport, main.exportPanel
        main.ApplyProject(DecodeProject(project, v.furnishingDefinitions), None)
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetScaleOption("pageSize", "A4")
        panel.SetScaleOption("pageOrientation", "Landscape")
        panel.SetScaleOption("dpi", 300)
        panel.SetOverride("texture", "wrinkled_paper_t1.33_5_5_5_5.png")
        panel.SetOverride("vignetteEnabled", False)
        panel.SetActive(True)
        overlay = v.exportOverlay
        result["pagePixels"] = list(panel.PrintLayout()["pixels"])
        width, height = panel.PrintLayout()["paperTile"]
        overlay.bounds = (*overlay.pageOrigin, width * 2, height * 2)
        panel.SetBounds(overlay.bounds)
        v.zoom = min(v.DrawingRect().width() / (width * 2), v.DrawingRect().height() / (height * 2)) * .9 / v.basePixelsPerMillimeter
        center = QtCore.QPointF(overlay.pageOrigin[0] + width, overlay.pageOrigin[1] + height)
        v.panOffset += v.DrawingRect().center() - v.WorldToViewport(center)
        overlay.printPreviewTimer.stop()
        v.grab()
        assert len(overlay.printPageCache) == 4, (overlay.previewError, len(overlay.printPageCache))
        result["objects"] = len(v.walls) + len(v.windows) + len(v.furnishings) + len(v.labels)
        path = texturesDirectory / overlay.texture
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        result["texture"] = path.name
        result["texturePixels"] = [compositing.LoadNormalTexture(path, stamp).width(), compositing.LoadNormalTexture(path, stamp).height()]
        result["tileMs"] = {}
        for name, method in (("previous", previous), ("current", current)):
            method(path, stamp, 123, .5, .5, .5)
            times = []
            for angle in (124, 125, 126, 127, 128, 129):
                started = perf_counter()
                method(path, stamp, angle, .5, .5, .5)
                times.append((perf_counter() - started) * 1000)
            result["tileMs"][name] = statistics.median(times)
        for field in ("Angle", "Highlights", "Midtones", "Shadows"):
            values = list(range(110, 126, 2)) if field == "Angle" else list(range(300, 700, 50))
            slider = panel.textureSliders[field]
            slider.setSliderDown(True)
            assert overlay.compositeGesture
            parity = []
            for method in (previous, current):
                with patch.object(compositing, "NormalLightingTile", method):
                    slider.setSliderPosition(values[0])
                    parity.append(v.grab().toImage())
            assert parity[0] == parity[1], (field, "Whole preview pixels changed")
            times = dict(previous = [], current = [])
            with patch.object(overlay, "renderPrintPage", wraps = overlay.renderPrintPage) as pages:
                for repeat in range(2):
                    methods = [("previous", previous), ("current", current)]
                    if repeat:
                        methods.reverse()
                    for name, method in methods:
                        with patch.object(compositing, "NormalLightingTile", method):
                            for value in values:
                                started = perf_counter()
                                slider.setSliderPosition(value)
                                v.grab()
                                times[name].append((perf_counter() - started) * 1000)
                assert not pages.called, "Lighting adjustment rebuilt page decorations"
            result["cases"][field] = {name: round(statistics.median(samples), 2) for name, samples in times.items()}
            print(field, result["cases"][field], flush = True)
            slider.setSliderDown(False)
        result["wholePreviewPixelParity"] = True
        result["scope"] = "Synchronous held-slider updates and viewport grabs; isolated recovery-scene copy. Four selected A4 sheets at 300 PPI. Not input-to-display latency."
    print("tileMs", result["tileMs"], flush = True)
    output = root / "diagnostics"
    output.mkdir(exist_ok = True)
    (output / "composite-lighting-results.json").write_text(json.dumps(result, indent = 2), encoding = "utf-8")


if __name__ == "__main__":
    Main()
