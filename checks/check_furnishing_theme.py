"""Neutral SVG assets map consistently to theme, selection and missing colors."""
import os
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.catalog import LoadFurnishings, furnishingsFolder
from planner_app.graphics.furnishings import CompoundFurnishingSvg, FurnishingRenderer, SelectedFurnishingRenderer
from planner_app.ui.widgets import FurnishingButton
from planner_app.graphics.palette import themeColors


def Render(renderer):
    image = QtGui.QImage(120, 120, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    renderer.render(painter, QtCore.QRectF(10, 10, 100, 100))
    painter.end()
    return image


def Main():
    app = QtWidgets.QApplication([])

    def CheckOutline(image, expected):
        color = image.pixelColor(9, 60)
        reference = QtGui.QColor(expected)
        assert color.alpha() > 0
        assert all(abs(channel - target) <= 2 for channel, target in zip(color.getRgb()[:3], reference.getRgb()[:3]))

    definitions = {item["key"]: item for item in LoadFurnishings()}
    originals = {}
    for path in (furnishingsFolder / "images").glob("*.svg"):
        originals[path] = path.read_bytes()
        for element in ElementTree.fromstring(originals[path]).iter():
            for attribute in ("fill", "stroke"):
                assert element.get(attribute) in (None, "none", "#000000", "#ffffff")
    square = furnishingsFolder / "images/square.svg"
    normal = Render(FurnishingRenderer(square))
    assert normal.pixelColor(60, 60).name() == themeColors["canvas"]
    CheckOutline(normal, themeColors["objectOutline"])
    assert normal.pixelColor(0, 0).alpha() == 0
    selected = Render(SelectedFurnishingRenderer(square))
    assert selected.pixelColor(60, 60).name() == themeColors["canvas"]
    CheckOutline(selected, themeColors["selectionOutline"])
    grouped = Render(SelectedFurnishingRenderer(square, "#a6d5ff"))
    CheckOutline(grouped, "#a6d5ff")
    light = Render(FurnishingRenderer(square, palette = {
        "outline": "#101010", "background": "#ffffff", "missing": "#cc0000"}))
    assert light.pixelColor(60, 60).name() == "#ffffff"
    CheckOutline(light, "#101010")
    null = Render(FurnishingRenderer(definitions["null"]["imagePath"]))
    assert any(null.pixelColor(x, y).name() == themeColors["missing"]
               for x in range(120) for y in range(120))
    selectedNull = Render(SelectedFurnishingRenderer(definitions["null"]["imagePath"]))
    assert any(selectedNull.pixelColor(x, y).name() == themeColors["missing"]
               for x in range(120) for y in range(120))
    for sample in (null, selectedNull):
        assert not any(sample.pixelColor(x, y).alpha() > 0 and sample.pixelColor(x, y).name() in
                       (themeColors["objectOutline"], themeColors["selectionOutline"])
                       for x in range(120) for y in range(120))
    circle = Render(FurnishingRenderer(furnishingsFolder / "images/circle.svg"))
    assert circle.pixelColor(11, 11).alpha() == 0 and circle.pixelColor(60, 60).name() == themeColors["canvas"]
    # Paint in inline styles and CSS receives the same mapping as attributes.
    styled = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><style>.shape {fill: white; stroke: black; stroke-width: 4}</style><rect class="shape" x="0" y="0" width="100" height="100"/></svg>'
    styledImage = Render(FurnishingRenderer(styled))
    assert styledImage.pixelColor(60, 60).name() == themeColors["canvas"]
    CheckOutline(styledImage, themeColors["objectOutline"])
    inline = styled.replace(b'class="shape"', b'style="fill: #fff; stroke: #000; stroke-width: 4"')
    CheckOutline(Render(SelectedFurnishingRenderer(inline)), themeColors["selectionOutline"])
    # Null's semantic paint marker survives composition without coloring its siblings.
    components = [{"definition": definitions["null"], "x": -500, "y": 0, "width": 1000,
                   "length": 1000, "angle": 0, "zIndex": 0},
                  {"definition": definitions["desk"], "x": 600, "y": 0, "width": 1200,
                   "length": 600, "angle": 0, "zIndex": 1}]
    data, width, length, center = CompoundFurnishingSvg(components)
    image = Render(FurnishingRenderer(data))
    assert any(image.pixelColor(x, y).name() == themeColors["missing"]
               for x in range(120) for y in range(120))
    assert any(image.pixelColor(x, y).name() == themeColors["objectOutline"]
               for x in range(120) for y in range(120))
    # Palette icons also go through the theme mapper, rather than raw QIcon SVGs.
    button = FurnishingButton(definitions["desk"])
    icon = button.icon().pixmap(80, 80).toImage()
    assert icon.pixelColor(40, 40).name() == themeColors["fieldBackground"]
    assert all(path.read_bytes() == original for path, original in originals.items())
    app.processEvents()


if __name__ == "__main__":
    Main()
