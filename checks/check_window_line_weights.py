"""Wall faces inside all window types use opening weights, including at zero."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.palette import themeColors
from planner_app.graphics.symbols import DrawOpeningSymbol
from planner_app.models import Wall, Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway
from planner_app.viewport.widget import DrawingViewport


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    themeColors.update(canvas = "#ffffff", wallFill = "#ffffff", wallOutline = "#000000", objectOutline = "#000000")
    viewport = DrawingViewport()
    viewport.resize(700, 500)
    viewport.showGrid = viewport.showMeasurements = False
    viewport.performanceTimer.stop()
    viewport.lineWidths.update(walls = 8, architectural = 1)
    point = QtCore.QPointF
    viewport.show()
    app.processEvents()
    for vertical in (False, True):
        first = point(0, -1400) if vertical else point(-1400, 0)
        second = -first
        wall = Wall(first, second, 240)
        viewport.walls = [wall]
        for openingType in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow):
            viewport.windows = [openingType(wall, .25, .75)]
            viewport.windows[0].swingsOutwards = True
            for zoom in (.5, 1, 2):
                viewport.zoom = zoom
                for weight in (0, 1, 3):
                    viewport.lineWidths["architectural"] = weight
                    image = viewport.grab().toImage()
                    openingSample = viewport.WorldToViewport(point(120, 0) if vertical else point(0, -120)).toPoint()
                    wallSample = viewport.WorldToViewport(point(120, -1000) if vertical else point(-1000, -120)).toPoint()
                    for sample, expected in ((openingSample, weight), (wallSample, 8)):
                        if not image.rect().adjusted(12, 12, -12, -12).contains(sample):
                            continue
                        coverage = sum((255 - image.pixelColor(sample.x() + offset if vertical else sample.x(),
                                                               sample.y() if vertical else sample.y() + offset).red()) / 255
                                       for offset in range(-10, 11))
                        assert abs(coverage - expected) < .08, (openingType.__name__, vertical, zoom, weight, coverage, expected)
    viewport.zoom = 1
    viewport.lineWidths.update(walls = 8, architectural = 0)
    # Distinct inks ensure wall ends do not inherit the opening's brighter color.
    themeColors["objectOutline"] = "#ff0000"
    wall = Wall(point(-1400, 0), point(1400, 0), 240)
    viewport.walls = [wall]
    for openingType in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway):
        opening = openingType(wall, .25, .75)
        viewport.windows = [opening]
        image = viewport.grab().toImage()
        endpoint = opening.firstVertex
        sample = viewport.WorldToViewport(endpoint).toPoint()
        coverage = sum((255 - image.pixelColor(sample.x() + offset, sample.y()).red()) / 255
                       for offset in range(-10, 11))
        assert abs(coverage - 8) < .08, (openingType.__name__, coverage)
    # At intersections, wall crossbars must cover the brighter long frame
    # lines and the casement hinge/swing, in either orientation.
    for vertical in (False, True):
        first, second = (point(150, 100), point(150, 300)) if vertical else (point(100, 150), point(300, 150))
        normal = point(-20, 0) if vertical else point(0, 20)
        for openingType in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow):
            image = QtGui.QImage(400, 400, QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtCore.Qt.GlobalColor.white)
            painter = QtGui.QPainter(image)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            DrawOpeningSymbol(painter, first, second, 40, openingType,
                              color = "#ff0000", wallColor = "#0000ff", lineWidth = 3, wallLineWidth = 8)
            painter.end()
            for endpoint in (first, second):
                for sample in (endpoint - normal, endpoint + normal, endpoint + normal * .35):
                    assert image.pixelColor(sample.toPoint()) == QtGui.QColor("#0000ff"), (openingType.__name__, vertical, sample)
    viewport.close()


if __name__ == "__main__":
    Main()
