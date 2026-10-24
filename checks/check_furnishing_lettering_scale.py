"""SVG coordinate units do not change lettering caps or authored anchors."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.catalog import LoadFurnishings
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.furnishings import FurnishingRenderer, SelectedFurnishingRenderer, CompoundFurnishingSvg
from planner_app.graphics.object_composite import ObjectPaintDevice


def LetterBounds(renderer, width, height, angle = 0):
    device = ObjectPaintDevice(QtCore.QSize(3000, 3000), "white")
    with QtGui.QPainter(device) as painter:
        painter.translate(1500, 1500)
        painter.rotate(angle)
        renderer.render(painter, QtCore.QRectF(-width / 2, -height / 2, width, height))
    ink = QtCore.QRectF()
    for path, pen, brush, transform, *unused in device.engine.commands:
        if brush.style() == QtCore.Qt.BrushStyle.SolidPattern and brush.color() == QtGui.QColor("black"):
            ink = ink.united(transform.map(path).boundingRect())
    assert not ink.isEmpty()
    return ink


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    colors = {"outline": "#000000", "background": "#ffffff", "missing": "#ff0000"}
    sources = []
    for factor in (.5, 1, 6, 10):
        # Both common coordinate conversions: rewriting every coordinate, and
        # wrapping the original drawing in a scale transform.
        for grouped in (False, True):
            units = 1 if grouped else factor
            body = f'''<rect width="{100 * units}" height="{100 * units}" fill="white"/>
                <text x="{23 * units}" y="{60 * units}" font-family="Noto Sans"
                      font-size="{36 * units}" fill="black">REF</text>'''
            if grouped:
                body = f'<g transform="scale({factor})">{body}</g>'
            source = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {100 * factor} {100 * factor}" preserveAspectRatio="none">{body}</svg>'.encode()
            sources.append(source)
    for nominalSize in (None, (600, 600)):
        renderers = [FurnishingRenderer(source, palette = colors, nominalSize = nominalSize) for source in sources]
        for width, height, angle in ((40, 40, 0), (100, 100, 0), (600, 600, 0), (400, 100, 35), (100, 400, 90)):
            reference = LetterBounds(renderers[0], width, height, angle)
            for renderer in renderers[1:]:
                ink = LetterBounds(renderer, width, height, angle)
                assert abs(ink.width() - reference.width()) <= 1.5, (nominalSize, width, height, reference, ink)
                assert abs(ink.height() - reference.height()) <= 1.5, (nominalSize, width, height, reference, ink)
                assert QtCore.QLineF(ink.center(), reference.center()).length() <= 1.5, (reference, ink)
    for source in sources:
        component = {"definition": {"graphicData": source, "width": 600, "length": 600},
                     "x": 0, "y": 0, "width": 300, "length": 150, "angle": 35, "zIndex": 0}
        compound, width, height, center = CompoundFurnishingSvg([component])
        renderer = FurnishingRenderer(compound, palette = colors, nominalSize = (width, height))
        ink = LetterBounds(renderer, width, height)
        baseline = LetterBounds(FurnishingRenderer(CompoundFurnishingSvg([{**component,
            "definition": {"graphicData": sources[2], "width": 600, "length": 600}}])[0], palette = colors), width, height)
        assert abs(ink.height() - baseline.height()) <= 1.5 and abs(ink.width() - baseline.width()) <= 1.5
        assert QtCore.QLineF(ink.center(), baseline.center()).length() <= 1.5
        nestedDefinition = {"graphicData": compound, "width": width, "length": height}
        nestedComponent = {"definition": nestedDefinition, "x": 0, "y": 0, "width": width * 1.7,
                           "length": height * .8, "angle": 90, "zIndex": 0}
        nested, nestedWidth, nestedHeight, center = CompoundFurnishingSvg([nestedComponent])
        nestedInk = LetterBounds(FurnishingRenderer(nested, palette = colors), nestedWidth, nestedHeight)
        if source == sources[0]:
            nestedBaseline = nestedInk
        else:
            assert abs(nestedInk.height() - nestedBaseline.height()) <= 1.5
            assert abs(nestedInk.width() - nestedBaseline.width()) <= 1.5
            assert QtCore.QLineF(nestedInk.center(), nestedBaseline.center()).length() <= 1.5

    # Real appliance labels have the same physical font size, despite their
    # 100-unit, centimetre and millimetre SVG coordinate conventions.
    definitions = {item["key"]: item for item in LoadFurnishings()}
    appliances = []
    for key in ("washer", "dryer", "freezer_chest", "fridge", "fridge_double"):
        definition = definitions[key]
        source = Path(definition["imagePath"]).read_bytes()
        source = source.replace(b'stroke="#000000"', b'stroke="#00ff00"').replace(b"stroke:#000000", b"stroke:#00ff00")
        size = (definition["width"], definition["length"])
        renderer = FurnishingRenderer(source, palette = colors, nominalSize = size)
        # Selection and transparent replay must use the same normalized cap.
        selected = SelectedFurnishingRenderer(source, selectionColor = "black", nominalSize = size)
        transparent = FurnishingRenderer(source, palette = colors, nominalSize = size, solidBackground = False)
        anchor = LetterBounds(renderer, size[0] * .05, size[1] * .05).center() - QtCore.QPointF(1500, 1500)
        for scale in (.05, .1, .25, 1):
            width, height = size[0] * scale, size[1] * scale
            ink = LetterBounds(renderer, width, height)
            expectedCenter = QtCore.QPointF(1500, 1500) + anchor * (scale / .05)
            assert QtCore.QLineF(ink.center(), expectedCenter).length() <= 1.5, (key, scale, ink.center(), expectedCenter)
            assert abs(LetterBounds(selected, width, height).height() - ink.height()) <= 1.5
            assert abs(LetterBounds(transparent.solidRenderer, width, height).height() - ink.height()) <= 1.5
        appliances.append((key, renderer, size))
    for scale in (.05, .1, .25, 1):
        heights = [LetterBounds(renderer, size[0] * scale, size[1] * scale).height()
                   for key, renderer, size in appliances]
        assert max(heights) - min(heights) <= 1.5, (scale, heights)


if __name__ == "__main__":
    Main()
