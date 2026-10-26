"""SVG furnishing strokes retain export thickness and scale with vector output."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtSvg
from planner_app.graphics.furnishings import FurnishingRenderer
from planner_app.graphics.object_composite import ObjectPaintDevice


def Main():
    app = QtWidgets.QApplication([])
    source = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M10 50 H90" fill="none" stroke="black" vector-effect="non-scaling-stroke"/></svg>'
    sources = (source,
               source.replace(b'vector-effect="non-scaling-stroke"', b'style="vector-effect:none"'),
               source.replace(b'<path ', b'<style>.line {vector-effect:none}</style><path class="line" '))
    for source in sources:
        graphic = FurnishingRenderer(source, lineWidth = 4, palette = {"outline": "#000000", "background": "#ffffff", "missing": "#000000"})
        for captured in (False, True):
            data = QtCore.QByteArray()
            buffer = QtCore.QBuffer(data)
            buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
            generator = QtSvg.QSvgGenerator(QtSvg.QSvgGenerator.SvgVersion.Svg11)
            generator.setOutputDevice(buffer)
            generator.setSize(QtCore.QSize(200, 120))
            generator.setViewBox(QtCore.QRect(0, 0, 200, 120))
            generator.setResolution(96)
            with QtGui.QPainter(generator) as painter:
                if captured:
                    device = ObjectPaintDevice(generator.size(), "white")
                    with QtGui.QPainter(device) as recorder:
                        graphic.render(recorder, QtCore.QRectF(0, 10, 200, 100))
                    device.engine.Replay(painter, QtCore.QRectF(0, 0, 200, 120))
                else:
                    graphic.render(painter, QtCore.QRectF(0, 10, 200, 100))
            assert b"non-scaling-stroke" not in bytes(data), bytes(data).decode()
            renderer = QtSvg.QSvgRenderer(bytes(data))
            assert renderer.isValid()
            for multiplier in (1, 2):
                image = QtGui.QImage(200 * multiplier, 120 * multiplier, QtGui.QImage.Format.Format_ARGB32)
                image.fill(QtGui.QColor("white"))
                with QtGui.QPainter(image) as painter:
                    renderer.render(painter)
                darkRows = [y for y in range(image.height()) if image.pixelColor(100 * multiplier, y).red() < 128]
                assert len(darkRows) == 4 * multiplier, (captured, multiplier, darkRows)
    # Dash offsets, cap/join effects and transformed curved geometry must render
    # identically to an authored non-scaling reference.
    reference = None
    for effect in ("non-scaling-stroke", "none"):
        source = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                  '<g transform="translate(5 5) scale(.8)"><path d="M10 20 H60 Q80 20 80 40 V80" '
                  'style="fill:none;stroke:black;stroke-width:1;stroke-linecap:round;stroke-linejoin:bevel;'
                  f'stroke-dasharray:4,3;stroke-dashoffset:1;vector-effect:{effect}"/></g></svg>').encode()
        graphic = FurnishingRenderer(source, lineWidth = 3, palette = {"outline": "#000000", "background": "#ffffff", "missing": "#ff0000"})
        image = QtGui.QImage(250, 200, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.GlobalColor.white)
        with QtGui.QPainter(image) as painter:
            graphic.render(painter)
        if reference is None:
            reference = image
        else:
            assert image == reference, "Stroke normalization altered dash/cap/join effects or curved geometry"
    # The toilet's mounting shapes have inline vector-effect:none and rounded
    # Inkscape path effects. At 3x geometry scale their stroke must stay 1 pixel.
    toilet = FurnishingRenderer(Path(__file__).resolve().parents[1] / "planner-main/furnishings/images/toilet_hung.svg",
                               lineWidth = 1, palette = {"outline": "#000000", "background": "#ffffff", "missing": "#ff0000"})
    image = QtGui.QImage(160, 205, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.GlobalColor.white)
    with QtGui.QPainter(image) as painter:
        toilet.render(painter, QtCore.QRectF(20, 20, 120, 165))
    for x in (47, 113):
        coverage = sum((255 - image.pixelColor(x, y).red()) / 255 for y in range(35, 44))
        assert abs(coverage - 1) < .05, (x, coverage)
    print("PASS: direct and transparent SVG furnishing strokes bake at export size and resize proportionally.")


if __name__ == "__main__":
    Main()
