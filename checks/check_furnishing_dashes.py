"""Authored dash/width ratios survive SVG units, inheritance and export capture."""
import os
import sys
from itertools import groupby
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.furnishings import FurnishingRenderer
from planner_app.graphics.object_composite import ObjectPaintDevice
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.paths import furnishingsDirectory


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    colors = {"outline": "#000000", "background": "#ffffff", "missing": "#ff0000"}
    for lineWidth in (1, 2, 4):
        for captured in (False, True):
            reference = None
            for scale in (1, .264583333333, .15875):
                width, dash, offset = scale, 4 * scale, 2 * scale
                for style in ("attributes", "inline", "inherited", "override", "css"):
                    paint = f'stroke="black" fill="none" stroke-width="{width}" stroke-dasharray="{dash},{dash}" stroke-dashoffset="{offset}"'
                    geometry = f'd="M {10 * scale} {50 * scale} H {90 * scale}"'
                    if style == "attributes":
                        content = f'<path {paint} {geometry}/>'
                    elif style == "inline":
                        content = f'<path style="stroke:black;fill:none;vector-effect:none;stroke-width:{width};stroke-dasharray:{dash},{dash};stroke-dashoffset:{offset}" {geometry}/>'
                    elif style == "inherited":
                        content = f'<g {paint}><path {geometry}/></g>'
                    elif style == "override":
                        content = f'<g {paint}><path stroke-width="{width * 2}" stroke-dasharray="{dash * 2},{dash * 2}" stroke-dashoffset="{offset * 2}" {geometry}/></g>'
                    else:
                        content = f'<style>.line {{stroke:black;fill:none;vector-effect:none;stroke-width:{width};stroke-dasharray:{dash},{dash};stroke-dashoffset:{offset}}}</style><path class="line" {geometry}/>'
                    source = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {100 * scale} {100 * scale}">{content}</svg>'.encode()
                    renderer = FurnishingRenderer(source, palette = colors, lineWidth = lineWidth)
                    image = QtGui.QImage(240, 120, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                    image.fill(QtCore.Qt.GlobalColor.white)
                    with QtGui.QPainter(image) as painter:
                        if captured:
                            device = ObjectPaintDevice(image.size(), "white")
                            with QtGui.QPainter(device) as recorder:
                                renderer.render(recorder, QtCore.QRectF(0, 0, 240, 120))
                            device.engine.Replay(painter, QtCore.QRectF(0, 0, 240, 120))
                        else:
                            renderer.render(painter, QtCore.QRectF(0, 0, 240, 120))
                    samples = [image.pixelColor(x, 60).red() < 128 for x in range(25, 215)]
                    assert any(samples) and not all(samples)
                    if reference is None:
                        reference = samples
                    assert samples == reference, (lineWidth, captured, scale, style)
    # Real artwork retains its authored dash-to-width ratio, including the oven
    # artwork's shorter pattern. Synthetic cases above still verify all style forms.
    for name, expectedDash in (("oven_built", 1.05833), ("dishwasher_built", 4.0)):
        source = furnishingsDirectory / "images" / (name + ".svg")
        renderer = FurnishingRenderer(source, palette = colors, lineWidth = 1)
        image = QtGui.QImage(400, 400, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.GlobalColor.white)
        with QtGui.QPainter(image) as painter:
            renderer.render(painter, QtCore.QRectF(0, 0, 400, 400))
        image.save(str(Path(__file__).resolve().parent.parent / "screenshots" / (name + "-dashes.png")))
        samples = [image.pixelColor(0, y).red() < 192 for y in range(80, 320)]
        runs = [len(list(values)) for paint, values in groupby(samples)][1:-1]
        assert runs and all(max(1, int(expectedDash)) <= length <= int(expectedDash) + 1 for length in runs), (name, runs)
        assert abs(sum(runs) / len(runs) - expectedDash) < .1, (name, runs)


if __name__ == "__main__":
    Main()
