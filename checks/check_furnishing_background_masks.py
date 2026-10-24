"""Transparent silhouettes occlude lower furnishings without hiding the canvas."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner import MainWindow
from furnishings import Furnishing
from planner_app.graphics.furnishings import FurnishingRenderer
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from planner_app.export_plan import VectorizeMaterials


def Main():
    app = QtWidgets.QApplication([])
    circle = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="30" fill="white" stroke="black"/></svg>'
    line = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M0 50 H100" fill="none" stroke="black"/></svg>'
    renderer = FurnishingRenderer(circle, solidBackground = False)
    assert renderer.backgroundPath.contains(QtCore.QPointF(50, 50))
    assert not renderer.backgroundPath.contains(QtCore.QPointF(5, 5)), "Mask used the graphic's bounding rectangle"
    transformed = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><style>.bg {fill:white}</style><g transform="translate(20 10)"><path class="bg" fill-rule="evenodd" d="M0 0H60V60H0Z M20 20H40V40H20Z"/></g></svg>'
    mask = FurnishingRenderer(transformed, solidBackground = False).backgroundPath
    assert mask.contains(QtCore.QPointF(25, 15))
    assert not mask.contains(QtCore.QPointF(50, 40)), "Mask lost its internal hole"
    assert not mask.contains(QtCore.QPointF(5, 5)), "Mask lost the SVG transform"
    main = MainWindow()
    v = main.viewport
    for key, graphic in (("desk", line), ("null", circle)):
        v.furnishingDefinitions[key] = dict(v.furnishingDefinitions[key], graphicData = graphic,
                                           width = 2000 if key == "desk" else 1000, length = 1000)
    back = Furnishing(v.furnishingDefinitions["desk"])
    front = Furnishing(v.furnishingDefinitions["null"], QtCore.QPointF(200, 0))
    front.angle = 35
    v.furnishings, v.walls = [back, front], []
    v.solidObjects = False
    main.RefreshFurnishingRenderers()
    v.showMeasurements = False
    v.setMinimumSize(0, 0)
    v.resize(300, 300)
    v.rulerSize = 0
    v.zoom = .1 / v.basePixelsPerMillimeter
    v.panOffset = QtCore.QPointF()
    v.EnsureObjectIds()
    rect = QtCore.QRectF(0, 0, 300, 300)
    def Draw(painter):
        painter.fillRect(rect, QtGui.QColor("#336699"))
        painter.setClipRect(rect)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        v.DrawScene(painter, rect, QtCore.QPointF(150, 150), .1)
    png = QtGui.QImage(300, 300, QtGui.QImage.Format.Format_ARGB32)
    with QtGui.QPainter(png) as painter:
        Draw(painter)
    assert png.pixelColor(170, 150).name() == "#336699", "Lower furnishing leaked through transparent silhouette"
    assert png.pixelColor(100, 150).name() != "#336699", "Non-overlapping lower line disappeared"
    assert png.pixelColor(130, 150).name() != "#336699", "Mask clipped outside the circular background"
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.OpenModeFlag.ReadWrite)
    svg = QtSvg.QSvgGenerator(QtSvg.QSvgGenerator.SvgVersion.Svg11)
    svg.setOutputDevice(buffer)
    svg.setSize(QtCore.QSize(300, 300))
    svg.setViewBox(rect)
    with QtGui.QPainter(svg) as painter:
        Draw(painter)
    rendered = QtGui.QImage(300, 300, QtGui.QImage.Format.Format_ARGB32)
    rendered.fill(QtCore.Qt.GlobalColor.transparent)
    with QtGui.QPainter(rendered) as painter:
        SvgPreviewRenderer(VectorizeMaterials(bytes(buffer.data()), {})).render(painter)
    assert rendered.pixelColor(170, 150).name() == "#336699", "SVG lost the overlap clip"
    assert rendered.pixelColor(100, 150).name() != "#336699"
    v.furnishings = [front, back]
    with QtGui.QPainter(png) as painter:
        Draw(painter)
    assert png.pixelColor(170, 150).name() != "#336699", "Mask ignored furnishing layer order"
    v.furnishings = [back, front]
    v.hiddenObjects, v.hiddenObjectIds = [front], {id(front)}
    with QtGui.QPainter(png) as painter:
        Draw(painter)
    assert png.pixelColor(170, 150).name() != "#336699", "Hidden furnishing still masked lower artwork"
    main.close()
    print("PASS: Curved, transformed and hollow SVG masks; partial rotated overlap in PNG/SVG")


if __name__ == "__main__":
    Main()
