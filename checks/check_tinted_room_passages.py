"""Passage outline changes preserve floor backgrounds, grid policy and jambs."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner_app.models import Wall, Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway, Window
from planner_app.viewport.widget import DrawingViewport
from planner_app.graphics.palette import themeColors
from planner_app.graphics.symbols import DrawOpeningSymbol
from check_room_detection import Rectangle
from check_pan_dpi import CompareDirect
from fixtures.grid_paint_reference_20261028 import ReferenceDrawGridBackground


def Background(view, vector = False, reference = False):
    image = QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtGui.QColor(themeColors["canvas"]))
    data = QtCore.QByteArray()
    buffer = QtCore.QBuffer(data)
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    device = image
    if vector:
        device = QtSvg.QSvgGenerator()
        device.setOutputDevice(buffer)
        device.setSize(view.size())
        device.setViewBox(view.rect())
    with QtGui.QPainter(device) as painter:
        function = ReferenceDrawGridBackground if reference else type(view).DrawGridBackground
        function(view, painter, view.DrawingRect(), view.WorldToViewport(QtCore.QPointF()), view.basePixelsPerMillimeter * view.zoom)
    if vector:
        with QtGui.QPainter(image) as painter:
            QtSvg.QSvgRenderer(data).render(painter)
    return image


def Main():
    app = QtWidgets.QApplication([])
    view = DrawingViewport()
    view.resize(1000, 700)
    view.performanceTimer.stop()
    view.showTips = view.showMeasurements = False
    view.unitsMode = "Millimeters"
    view.zoom = 1
    point = QtCore.QPointF
    divider = Wall(point(-2000, 0), point(2000, 0), 200)
    view.walls = Rectangle(-2000, -2000, 4000, 4000) + [divider]
    view.gridOrigin = (0, 100)
    view.gridIntensities = dict.fromkeys(view.gridIntensities, 1)
    for kind in (Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway):
        opening = kind(divider, .35, .65)
        view.windows = [opening]
        view.roomDetection.Check()
        for vector in (False, True):
            for floors, solid in ((False, False), (False, True), (True, False), (True, True)):
                view.floors, view.solidRooms = floors, solid
                assert Background(view, vector) == Background(view, vector, True), (kind.__name__, vector, floors, solid)
    # Native doorway faces are optional, but its jambs remain drawn.
    images = []
    for edges in (False, True):
        image = QtGui.QImage(200, 100, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.white)
        with QtGui.QPainter(image) as painter:
            DrawOpeningSymbol(painter, point(30, 50), point(170, 50), 40, OpenDoorway,
                              drawPassageEdges = edges, color = "#000000", wallColor = "#000000", lineWidth = 2, wallLineWidth = 2)
        assert image.pixelColor(30, 50) != QtGui.QColor("white"), "Door jamb disappeared"
        assert (image.pixelColor(100, 30) != QtGui.QColor("white")) == edges
        images.append(image)
    assert images[0] != images[1]
    view.windows = [Door(divider, .35, .65)]
    view.show()
    app.processEvents()
    view.performanceLabel.hide()
    view.isPanning = True
    for delta in (point(3, 1), point(.31, .43), point(-3, -1)):
        view.panOffset += delta
        CompareDirect(view)
    view.isPanning = False
    view.close()
    print("PASS: unchanged backgrounds in all tint/Solid Rooms combinations, eight passage types, jambs and panning")


if __name__ == "__main__":
    Main()
