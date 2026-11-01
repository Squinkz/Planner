"""Sampling widths share compatible preparation and retain exact artwork."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg
from fixtures.parity_examples import ExampleWindow
from planner_app.graphics import furnishings


def Pixels(renderer, vector):
    image = QtGui.QImage(420, 300, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    device = image
    if vector:
        data = QtCore.QByteArray()
        buffer = QtCore.QBuffer(data)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        device = QtSvg.QSvgGenerator()
        device.setOutputDevice(buffer)
        device.setSize(image.size())
        device.setViewBox(QtCore.QRect(0, 0, 420, 300))
    with QtGui.QPainter(device) as painter:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.translate(70, 40)
        painter.rotate(13)
        renderer.render(painter, QtCore.QRectF(0, 0, 280, 180), worldSize = (900, 600))
    if vector:
        native = QtSvg.QSvgRenderer(data)
        assert native.isValid()
        with QtGui.QPainter(image) as painter:
            native.render(painter)
    return image


def Main():
    with ExampleWindow() as (main, folder):
        sources = [b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="white" stroke="black"/><text x="35" y="55">W</text></svg>',
                   b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect id="planner-bounds" x="10" y="10" width="80" height="80"/><g id="planner-fixed"><circle cx="50" cy="50" r="15" fill="white" stroke="black"/></g><text x="35" y="55">FIX</text></svg>',
                   b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><style>.line{stroke:black;fill:none;stroke-width:2;stroke-dasharray:6,4}</style><path class="line" d="M5 5 L95 95"/><text x="20" y="40">DASH</text></svg>',
                   Path(main.viewport.furnishingDefinitions["washer"]["imagePath"]).read_bytes()]
        for index, source in enumerate(sources):
            furnishings.preparedFurnishingCache.clear()
            with patch.object(furnishings, "ValidateFurnishingSvg", wraps = furnishings.ValidateFurnishingSvg) as validate:
                for width in (.35, .7, 1.4):
                    furnishings.FurnishingRenderer(source, lineWidth = width, nominalSize = (600, 600))
                if index < 3:
                    assert validate.call_count == (3 if index == 2 else 1), "Incompatible dash preparation reused or ordinary artwork prepared repeatedly"
            for solid in (False, True):
                furnishings.preparedFurnishingCache.clear()
                furnishings.FurnishingRenderer(source, lineWidth = .35, nominalSize = (600, 600))
                reused = furnishings.FurnishingRenderer(source, lineWidth = 1.4, nominalSize = (600, 600), solidBackground = solid)
                furnishings.preparedFurnishingCache.clear()
                fresh = furnishings.FurnishingRenderer(source, lineWidth = 1.4, nominalSize = (600, 600), solidBackground = solid)
                assert reused.artworkBounds == fresh.artworkBounds
                for vector in (False, True):
                    assert Pixels(reused, vector) == Pixels(fresh, vector), (index, solid, vector, "Prepared artwork changed")
        furnishings.preparedFurnishingCache.clear()
    print("Width-independent preparation reused; dashed widths remain separate; exact PNG/SVG lettering, bounds and fixed-detail parity passed")


if __name__ == "__main__":
    Main()
