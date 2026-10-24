"""Furnishing lettering stays centered, uniform and screen-sized across views."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtSvg
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.furnishings import FurnishingRenderer, CompoundFurnishingSvg
from planner_app.graphics.object_composite import ObjectPaintDevice
from planner_app.graphics import palette


def Render(renderer, width, height):
    image = QtGui.QImage(width + 20, height + 20, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    with QtGui.QPainter(image) as painter:
        renderer.render(painter, QtCore.QRectF(10, 10, width, height))
    return image


def InkBounds(image):
    points = []
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() > 128 and max(color.red(), color.green(), color.blue()) < 192:
                points.append((x, y))
    assert points, "Lettering disappeared"
    left, right = min(x for x, y in points), max(x for x, y in points)
    top, bottom = min(y for x, y in points), max(y for x, y in points)
    return QtCore.QRectF(left, top, right - left + 1, bottom - top + 1)


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    font = QtGui.QFont("Noto Sans")
    font.setPixelSize(35)
    glyphs = QtGui.QPainterPath()
    glyphs.addText(0, 0, font, "REF")
    anchor = QtCore.QPointF(50, 50) - glyphs.boundingRect().center()
    source = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" preserveAspectRatio="none">
        <rect width="100" height="100" fill="white" stroke="#00ff00"/>
        <text x="{anchor.x()}" y="{anchor.y()}" font-family="Noto Sans" font-size="35" fill="black">REF</text>
    </svg>'''.encode()
    colors = {"outline": "#000000", "background": "#ffffff", "missing": "#ff0000"}
    renderer = FurnishingRenderer(source, palette = colors)
    reference = InkBounds(Render(renderer, 200, 100))
    with patch.object(palette, "labelFont", "Courier New"):
        themed = FurnishingRenderer(source, palette = colors)
        assert themed.letteringFont == "Courier New"
        assert all(element.get("font-family") == "Courier New" for element in themed.letteringRoot.iter()
                   if element.tag.rsplit("}", 1)[-1] in ("text", "tspan"))
        themedImage = Render(themed, 200, 100)
        assert themedImage != Render(renderer, 200, 100), "The theme font did not change the lettering"
        for width, height in ((30, 20), (200, 100), (400, 400), (100, 400)):
            ink = InkBounds(Render(themed, width, height))
            assert abs(ink.center().x() - (10 + width / 2)) <= 1.5, ink
            assert abs(ink.center().y() - (10 + height / 2)) <= 1.5, ink
    for width, height in ((400, 100), (100, 400), (400, 400)):
        ink = InkBounds(Render(renderer, width, height))
        assert abs(ink.width() - reference.width()) <= 1, (reference, ink)
        assert abs(ink.height() - reference.height()) <= 1, (reference, ink)
        assert abs(ink.center().x() - (10 + width / 2)) <= 1, ink
        assert abs(ink.center().y() - (10 + height / 2)) <= 1, ink
    small = InkBounds(Render(renderer, 30, 20))
    assert small.width() < reference.width() and small.height() < reference.height()
    assert abs(small.width() / small.height() - reference.width() / reference.height()) < .25
    # Zooming out shrinks lettering proportionally while there is ample room.
    for size in (75, 50, 25):
        ink = InkBounds(Render(renderer, size, size))
        assert abs(ink.width() - reference.width() * size / 100) <= 1.5, ink
        assert abs(ink.height() - reference.height() * size / 100) <= 1.5, ink
        assert abs(ink.center().x() - (10 + size / 2)) <= 1, ink
        assert abs(ink.center().y() - (10 + size / 2)) <= 1, ink
    narrow = InkBounds(Render(renderer, 50, 200))
    assert abs(narrow.width() - reference.width() / 2) <= 1.5, narrow
    assert abs(narrow.height() - reference.height() / 2) <= 1.5, narrow
    with patch("planner_app.graphics.furnishings.ElementTree.tostring", side_effect = AssertionError("Repeated SVG preparation")):
        Render(renderer, 30, 20)
    for width in range(110, 130):
        Render(renderer, width, 100)
    assert len(renderer.letteringVariants) == 16

    # Flattened and nested components retain their own centers and source font size.
    component = {"definition": {"graphicData": source}, "x": 150, "y": -75,
                 "width": 200, "length": 100, "angle": 0, "zIndex": 0}
    compound, width, height, center = CompoundFurnishingSvg([component])
    compoundRenderer = FurnishingRenderer(compound, palette = colors)
    compoundInk = InkBounds(Render(compoundRenderer, 400, 100))
    assert abs(compoundInk.width() - reference.width()) <= 1, compoundInk
    assert abs(compoundInk.center().x() - 210) <= 3, compoundInk
    component["definition"] = {"graphicData": compound}
    component["angle"] = 90
    nested, width, height, center = CompoundFurnishingSvg([component])
    nestedRenderer = FurnishingRenderer(nested, palette = colors)
    nestedInk = InkBounds(Render(nestedRenderer, 100, 400))
    assert abs(nestedInk.width() - reference.width()) <= 1, nestedInk
    assert abs(nestedInk.height() - reference.height()) <= 1, nestedInk

    component["definition"] = {"graphicData": source}
    component["angle"] = 35
    rotated = FurnishingRenderer(CompoundFurnishingSvg([component])[0], palette = colors)
    device = ObjectPaintDevice(QtCore.QSize(500, 200), "#ffffff")
    with QtGui.QPainter(device) as painter:
        rotated.render(painter, QtCore.QRectF(0, 0, 500, 200))
    glyphTransforms = [command[3] for command in device.engine.commands
                       if command[2].style() == QtCore.Qt.BrushStyle.SolidPattern
                       and command[2].color() == QtGui.QColor("black")]
    assert glyphTransforms
    for transform in glyphTransforms:
        xLength = transform.m11() ** 2 + transform.m12() ** 2
        yLength = transform.m21() ** 2 + transform.m22() ** 2
        dot = transform.m11() * transform.m21() + transform.m12() * transform.m22()
        assert abs(xLength - yLength) < 1e-6 and abs(dot) < 1e-6, transform
        assert abs(transform.m12()) < 1e-6 and abs(transform.m21()) < 1e-6, transform
        assert transform.m11() > 0 and transform.m22() > 0, transform

    for angle in (0, 35, 90, 180, 270, 35):
        image = QtGui.QImage(320, 320, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        with QtGui.QPainter(image) as painter:
            painter.translate(160, 160)
            painter.rotate(angle)
            renderer.render(painter, QtCore.QRectF(-100, -50, 200, 100))
        ink = InkBounds(image)
        assert abs(ink.width() - reference.width()) <= 1, (angle, ink)
        assert abs(ink.height() - reference.height()) <= 1, (angle, ink)
        assert abs(ink.center().x() - 160) <= 1 and abs(ink.center().y() - 160) <= 1, (angle, ink)

    # Authored text transforms preserve font size while their rotation is cancelled.
    transformedSource = source.replace(b'<text x=', b'<text transform="translate(50 50) rotate(90) scale(.5) translate(-50 -50)" x=')
    transformedInk = InkBounds(Render(FurnishingRenderer(transformedSource, palette = colors), 200, 100))
    assert abs(transformedInk.width() - reference.width() / 2) <= 1.5, transformedInk
    assert abs(transformedInk.height() - reference.height() / 2) <= 1.5, transformedInk
    assert abs(transformedInk.center().x() - 110) <= 1 and abs(transformedInk.center().y() - 60) <= 1, transformedInk

    # A later shape still covers lettering; text is not painted as an overlay.
    coveredSource = source.replace(b'</svg>', b'<rect width="100" height="100" fill="white"/></svg>')
    coveredImage = Render(FurnishingRenderer(coveredSource, palette = colors), 200, 100)
    assert coveredImage.pixelColor(110, 60) == QtGui.QColor("white")

    # SVG output retains the compensated glyphs as vector text.
    data = QtCore.QByteArray()
    buffer = QtCore.QBuffer(data)
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    generator = QtSvg.QSvgGenerator()
    generator.setOutputDevice(buffer)
    generator.setSize(QtCore.QSize(420, 120))
    generator.setViewBox(QtCore.QRect(0, 0, 420, 120))
    with QtGui.QPainter(generator) as painter:
        renderer.render(painter, QtCore.QRectF(10, 10, 400, 100))
    exported = QtSvg.QSvgRenderer(bytes(data))
    svgImage = QtGui.QImage(420, 120, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    svgImage.fill(QtCore.Qt.GlobalColor.transparent)
    with QtGui.QPainter(svgImage) as painter:
        exported.render(painter, QtCore.QRectF(0, 0, 420, 120))
    assert abs(InkBounds(svgImage).width() - reference.width()) <= 2
    # The washer's drum is below the furnishing center. Its authored W anchor
    # must stay there across zoom and nonuniform stretching.
    washerSource = (Path(__file__).resolve().parent.parent / "planner-main" / "furnishings" / "images" / "washer.svg").read_bytes()
    washerSource = washerSource.replace(b'stroke="#000000"', b'stroke="#00ff00"').replace(b"stroke:#000000", b"stroke:#00ff00")
    original = QtSvg.QSvgRenderer(washerSource)
    device = ObjectPaintDevice(QtCore.QSize(100, 100), "white")
    with QtGui.QPainter(device) as painter:
        original.render(painter, QtCore.QRectF(0, 0, 100, 100))
    authoredInk = QtCore.QRectF()
    for path, pen, brush, transform, *unused in device.engine.commands:
        if brush.style() == QtCore.Qt.BrushStyle.SolidPattern and brush.color() == QtGui.QColor("black"):
            authoredInk = authoredInk.united(transform.map(path).boundingRect())
    assert not authoredInk.isEmpty() and authoredInk.center().y() > 53
    washer = FurnishingRenderer(washerSource, palette = colors)
    for width, height in ((60, 60), (100, 100), (300, 300), (600, 600), (160, 300)):
        ink = InkBounds(Render(washer, width, height))
        expected = QtCore.QPointF(10 + authoredInk.center().x() * width / 100,
                                  10 + authoredInk.center().y() * height / 100)
        assert QtCore.QLineF(ink.center(), expected).length() <= 1.5, (width, height, ink.center(), expected)
    print("PASS: centered lettering, authored proportion cap, zoom shrinkage, nested compounds, vector output and bounded renderer reuse.")


if __name__ == "__main__":
    Main()
