"""Project line weights and SVG stroke widths survive resizing and composition."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics import palette
from planner_app.graphics.linework import defaultLineWidths, LinePen
from planner_app.graphics.furnishings import FurnishingRenderer, CompoundFurnishingSvg
from planner_app.viewport.widget import DrawingViewport
from planner_app.models import Wall, Door, Window, Stair, Counter, Railing, Furnishing


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    source = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><style>.ink {stroke:black; stroke-width:9; fill:none}</style><path class="ink" d="M 10,50 L 90,50"/></svg>'
    compound, width, length, center = CompoundFurnishingSvg([
        {"definition": {"graphicData": source}, "x": 0, "y": 0, "width": 1000,
         "length": 1000, "angle": 0, "zIndex": 0}])
    for graphic in (source, source.replace(b'class="ink"', b'style="stroke:black;stroke-width:9;fill:none"'), compound):
        hidden = FurnishingRenderer(graphic, lineWidth = 0)
        image = QtGui.QImage(120, 120, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        hidden.render(painter, QtCore.QRectF(10, 10, 100, 100))
        painter.end()
        assert all(image.pixelColor(x, y).alpha() == 0 for x in range(120) for y in range(120))
        assert LinePen(palette.themeColors["wallOutline"], 0).style() == QtCore.Qt.PenStyle.NoPen
        renderer = FurnishingRenderer(graphic)
        for size in (100, 200, 400):
            image = QtGui.QImage(500, 500, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QtCore.Qt.GlobalColor.transparent)
            painter = QtGui.QPainter(image)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            renderer.render(painter, QtCore.QRectF(10, 10, size, size / 2))
            painter.end()
            x = 10 + size // 2
            coverage = sum(image.pixelColor(x, y).alpha() / 255 for y in range(500))
            assert abs(coverage - defaultLineWidths["furnishings"]) < .06, (size, coverage)
    viewport = DrawingViewport()
    key = viewport.SceneRenderKey(())
    viewport.lineWidths["walls"] = 3
    assert viewport.SceneRenderKey(()) != key
    viewport.lineWidths = dict(defaultLineWidths)
    viewport.resize(1200, 850)
    viewport.zoom = .75
    viewport.showGrid = False
    viewport.performanceTimer.stop()
    point = QtCore.QPointF
    wall = Wall(point(-2400, 1000), point(2400, 1000), 240)
    viewport.walls = [wall, Wall(point(2400, 1000), point(2400, -2200), 120),
                      Stair(point(-2000, -400), point(-2000, -2400), 800),
                      Counter(point(-1000, -2000), point(1000, -2000), 600),
                      Railing(point(-600, -3000), point(2000, -3000))]
    viewport.windows = [Door(wall, .1, .3), Window(wall, .55, .8)]
    viewport.furnishings = [Furnishing(viewport.furnishingDefinitions["desk"], point(0, -400))]
    viewport.EnsureObjectIds()
    viewport.show()
    app.processEvents()
    Path("screenshots").mkdir(exist_ok = True)
    assert viewport.grab().save("screenshots/linework-weights.png")
    viewport.close()


if __name__ == "__main__":
    Main()
