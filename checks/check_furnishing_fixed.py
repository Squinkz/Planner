"""Fixed SVG details keep world size, midpoint anchors and proportional shrinking."""
import os
import sys
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner_app.graphics.furnishings import FurnishingRenderer, CompoundFurnishingSvg, FurnishingContainsPoint, DrawFurnishing
from planner_app.models import Furnishing
from planner_app.paths import furnishingsDirectory


def RedBounds(image):
    points = [(x, y) for y in range(image.height()) for x in range(image.width())
              if image.pixelColor(x, y).red() > 200 and image.pixelColor(x, y).green() < 80]
    assert points
    left, right = min(x for x, y in points), max(x for x, y in points)
    top, bottom = min(y for x, y in points), max(y for x, y in points)
    return QtCore.QRectF(left, top, right - left + 1, bottom - top + 1)


def Main():
    app = QtWidgets.QApplication([])
    source = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 60">
        <rect x="5" y="5" width="10" height="10" fill="blue"/>
        <g id="planner-fixed-magazines"><rect x="60" y="25" width="20" height="10" fill="red"/></g>
    </svg>'''
    colors = {"outline": "#000000", "background": "#ffffff", "missing": "#ff00ff"}
    renderer = FurnishingRenderer(source, palette = colors, nominalSize = (1000, 600))
    assert len(renderer.fixedElements) == 1
    plainMarker = FurnishingRenderer(source.replace(b'planner-fixed-magazines', b'planner-fixed'),
                                     palette = colors, nominalSize = (1000, 600))
    assert len(plainMarker.fixedElements) == 1
    for width, length in ((1000, 600), (2000, 1200), (2000, 600), (500, 300), (2000, 300)):
        for pixelScale in (.1, .2):
            image = QtGui.QImage(round(width * pixelScale) + 40, round(length * pixelScale) + 40,
                                 QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QtCore.Qt.GlobalColor.white)
            bounds = QtCore.QRectF(20, 20, width * pixelScale, length * pixelScale)
            with QtGui.QPainter(image) as painter:
                renderer.render(painter, bounds, worldSize = (width, length))
            red = RedBounds(image)
            shrink = min(1, width / 1000, length / 600)
            assert abs(red.width() - 200 * shrink * pixelScale) <= 1, (width, length, red)
            assert abs(red.height() - 100 * shrink * pixelScale) <= 1, (width, length, red)
            assert abs(red.center().x() - (20 + width * pixelScale * .7)) <= 1
            assert abs(red.center().y() - (20 + length * pixelScale * .5)) <= 1
    # Compound ID namespacing retains markers and each child's default dimensions.
    definition = {"key": "Table", "name": "Table", "width": 1000, "length": 600, "graphicData": source}
    compound, width, length, center = CompoundFurnishingSvg([
        {"definition": definition, "x": 0, "y": 0, "width": 2000, "length": 1200, "angle": 0, "zIndex": 0}])
    compoundRenderer = FurnishingRenderer(compound, palette = colors, nominalSize = (width, length))
    assert len(compoundRenderer.fixedElements) == 1
    image = QtGui.QImage(440, 280, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.GlobalColor.white)
    with QtGui.QPainter(image) as painter:
        compoundRenderer.render(painter, QtCore.QRectF(20, 20, 400, 240), worldSize = (2000, 1200))
    assert abs(RedBounds(image).width() - 40) <= 1

    # The authored coffee-table groups use the plain planner-fixed ID.
    for name in ("coffee_table", "coffee_table_round"):
        root = ElementTree.fromstring((furnishingsDirectory / "images" / (name + ".svg")).read_bytes())
        group = next(element for element in root.iter() if element.get("id") == "planner-fixed")
        for element in group.iter():
            for attribute in ("fill", "stroke"):
                if element.get(attribute) not in (None, "none"):
                    element.set(attribute, "red")
            if element.get("style"):
                element.set("style", re.sub(r"((?:fill|stroke)\s*:\s*)(#[0-9a-fA-F]+|black|white)", r"\1red", element.get("style")))
        coffee = FurnishingRenderer(ElementTree.tostring(root), palette = colors, nominalSize = (1200, 600))
        assert len(coffee.fixedElements) == 1
        sizes = []
        for factor in (1, 2, .5):
            sample = QtGui.QImage(520, 280, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            sample.fill(QtCore.Qt.GlobalColor.white)
            with QtGui.QPainter(sample) as painter:
                coffee.render(painter, QtCore.QRectF(20, 20, 240 * factor, 120 * factor), worldSize = (1200 * factor, 600 * factor))
            sizes.append(RedBounds(sample).size())
        assert abs(sizes[0].width() - sizes[1].width()) <= 1, (name, sizes)
        assert abs(sizes[0].height() - sizes[1].height()) <= 1, (name, sizes)
        assert abs(sizes[0].width() - sizes[2].width() * 2) <= 2, (name, sizes)
        assert abs(sizes[0].height() - sizes[2].height() * 2) <= 2, (name, sizes)
    # A nested marker is governed by its outer marked group, not shrunk twice.
    nested = source.replace(b'<rect x="60"', b'<rect id="planner-fixed-inner" x="60"')
    assert len(FurnishingRenderer(nested, palette = colors, nominalSize = (1000, 600)).fixedElements) == 1
    # Authored rotation remains proportional under an anisotropic furnishing resize.
    rotated = source.replace(b'id="planner-fixed-magazines"', b'id="planner-fixed-magazines" transform="rotate(30 70 30)"')
    rotatedRenderer = FurnishingRenderer(rotated, palette = colors, nominalSize = (1000, 600))
    sizes = []
    for physicalWidth, physicalLength in ((1000, 600), (2000, 1200), (2000, 300)):
        sample = QtGui.QImage(440, 280, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        sample.fill(QtCore.Qt.GlobalColor.white)
        with QtGui.QPainter(sample) as painter:
            rotatedRenderer.render(painter, QtCore.QRectF(20, 20, physicalWidth * .2, physicalLength * .2),
                                   worldSize = (physicalWidth, physicalLength))
        sizes.append(RedBounds(sample).size())
    assert sizes[0] == sizes[1]
    assert abs(sizes[2].width() * 2 - sizes[0].width()) <= 2
    assert abs(sizes[2].height() * 2 - sizes[0].height()) <= 2
    # Rotated/flipped compound children retain their own physical defaults.
    compound, width, length, center = CompoundFurnishingSvg([
        {"definition": definition, "x": 0, "y": 0, "width": 2000, "length": 1200,
         "angle": 90, "flipHorizontal": True, "zIndex": 0}])
    rotatedCompound = FurnishingRenderer(compound, palette = colors, nominalSize = (width, length))
    image = QtGui.QImage(280, 440, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.GlobalColor.white)
    with QtGui.QPainter(image) as painter:
        rotatedCompound.render(painter, QtCore.QRectF(20, 20, 240, 400), worldSize = (1200, 2000))
    red = RedBounds(image)
    assert abs(red.width() - 20) <= 1 and abs(red.height() - 40) <= 1
    image = QtGui.QImage(440, 280, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    # Production drawing supplies physical dimensions; picking follows the resized ink.
    obj = Furnishing(definition)
    obj.width = 2000
    obj.firstVertex, obj.secondVertex = QtCore.QPointF(0, -600), QtCore.QPointF(0, 600)
    image.fill(QtCore.Qt.GlobalColor.white)
    with QtGui.QPainter(image) as painter:
        DrawFurnishing(painter, obj, QtCore.QPointF(220, 260), QtCore.QPointF(220, 20), .2, renderer)
    assert abs(RedBounds(image).width() - 40) <= 1
    assert FurnishingContainsPoint(obj, renderer, QtCore.QPointF(400, 0), 0)
    assert not FurnishingContainsPoint(obj, renderer, QtCore.QPointF(570, 0), 0)
    # SVG export bakes the same physical size into ordinary vector geometry.
    data = QtCore.QByteArray()
    buffer = QtCore.QBuffer(data)
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    generator = QtSvg.QSvgGenerator()
    generator.setOutputDevice(buffer)
    generator.setSize(QtCore.QSize(440, 280))
    generator.setViewBox(QtCore.QRect(0, 0, 440, 280))
    with QtGui.QPainter(generator) as painter:
        renderer.render(painter, QtCore.QRectF(20, 20, 400, 240), worldSize = (2000, 1200))
    image.fill(QtCore.Qt.GlobalColor.white)
    with QtGui.QPainter(image) as painter:
        QtSvg.QSvgRenderer(bytes(data)).render(painter)
    assert abs(RedBounds(image).width() - 40) <= 1


if __name__ == "__main__":
    Main()
