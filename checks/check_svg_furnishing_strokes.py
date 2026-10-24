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
    print("PASS: direct and transparent SVG furnishing strokes bake at export size and resize proportionally.")


if __name__ == "__main__":
    Main()
