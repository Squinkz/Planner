"""SVG furnishing fills retain their palette and transparent interiors."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtSvg
from planner_app.graphics.furnishings import FurnishingRenderer
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from planner import MainWindow
from furnishings import Furnishing
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.graphics import palette


def RenderImage(renderer):
    image = QtGui.QImage(renderer.defaultSize(), QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    with QtGui.QPainter(image) as painter:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
    return image


def Main():
    app = QtWidgets.QApplication([])
    source = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect x="10" y="10" width="80" height="80" rx="8" fill="white" stroke="black"/><circle cx="50" cy="50" r="20" fill="none" stroke="black"/></svg>'
    colors = {"outline": "#60586c", "background": "#f1ecdf", "missing": "#ff0000"}
    for solid in (True, False):
        graphic = FurnishingRenderer(source, lineWidth = 2, palette = colors, solidBackground = solid)
        data = QtCore.QByteArray()
        buffer = QtCore.QBuffer(data)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        generator = QtSvg.QSvgGenerator(QtSvg.QSvgGenerator.SvgVersion.Svg11)
        generator.setOutputDevice(buffer)
        generator.setSize(QtCore.QSize(200, 200))
        generator.setViewBox(QtCore.QRect(0, 0, 200, 200))
        with QtGui.QPainter(generator) as painter:
            graphic.render(painter, QtCore.QRectF(0, 0, 200, 200))
        for renderer in (QtSvg.QSvgRenderer(bytes(data)), SvgPreviewRenderer(bytes(data))):
            image = QtGui.QImage(200, 200, QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtGui.QColor("#87bcde"))
            with QtGui.QPainter(image) as painter:
                renderer.render(painter, QtCore.QRectF(0, 0, 200, 200))
            expected = colors["background"] if solid else "#87bcde"
            assert image.pixelColor(100, 100).name() == expected, (solid, type(renderer).__name__, image.pixelColor(100, 100).name(), bytes(data).decode())
    ApplyApplicationTheme(app)
    main = MainWindow()
    v, panel = main.viewport, main.exportPanel
    v.walls = []
    v.furnishings = [Furnishing(v.furnishingDefinitions["desk"]),
                    Furnishing(v.furnishingDefinitions["washer"], QtCore.QPointF(1400, 0))]
    v.EnsureObjectIds()
    v.sceneRevision += 1
    main.sidebarTabs.setCurrentWidget(panel)
    panel.borderField.setCurrentText("None")
    panel.SetOverride("measurementVisibility", {key: False for key in v.measurementVisibility})
    panel.SetOverride("visibility", True, "Furnishings")
    panel.scaleField.setValue(100)
    for solid in (True, False):
        panel.solidObjectsField.setChecked(solid)
        panel.PreviewColor("canvas", QtGui.QColor("#f1ecdf"))
        panel.PreviewColor("lines", QtGui.QColor("#60586c"))
        preview = SvgPreviewRenderer(panel.Render("svg", preview = True, previewScene = True))
        exported = SvgPreviewRenderer(panel.Render("svg"))
        assert RenderImage(preview) == RenderImage(exported), (solid, "Initial preview differs from saved SVG")
        # Retained layers must also recolor furnishing fills, strokes and text.
        for name, color in (("canvas", "#183243"), ("lines", "#fedcba")):
            panel.PreviewColor(name, QtGui.QColor(color))
            preview.Recolor(palette.themeColors)
            exported = SvgPreviewRenderer(panel.Render("svg"))
            assert RenderImage(preview) == RenderImage(exported), (solid, name, "Recolored preview differs from saved SVG")
    main.MarkProjectClean()
    main.close()
    print("PASS: SVG furnishing backgrounds and unfilled details preserve their paints.")


if __name__ == "__main__":
    Main()
