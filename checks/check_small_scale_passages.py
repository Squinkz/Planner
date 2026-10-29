"""Low-scale tinted passages have no short wall-stroke remnants near jambs."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Door
from planner_app.viewport.widget import DrawingViewport
from planner_app.graphics.palette import themeColors
from check_room_detection import Rectangle
from check_tinted_passage_outlines import AssertNoOutline
from check_pan_dpi import CompareDirect


def Main():
    app = QtWidgets.QApplication([])
    view = DrawingViewport()
    view.performanceTimer.stop()
    view.resize(1001, 701)
    point = QtCore.QPointF
    divider = Wall(point(-2000, 0), point(2000, 0), 200)
    view.walls = Rectangle(-2000, -2000, 4000, 4000) + [divider]
    view.windows = [Door(divider, .35, .65)]
    view.showGrid = view.showMeasurements = view.showTips = False
    view.floors = True
    view.show()
    app.processEvents()
    view.performanceLabel.hide()
    fill, canvas = QtGui.QColor(themeColors["roomFill"]), QtGui.QColor(themeColors["canvas"])
    ratio = view.devicePixelRatioF()
    samples = 0
    for scale in (40, 60, 100, 150, 199):
        view.zoom = scale / (1000 * view.basePixelsPerMillimeter)
        for solid in (False, True):
            view.solidRooms = solid
            for phase in (0, .31, .77):
                view.panOffset = point(.31, phase)
                image = view.grab().toImage()
                first = view.WorldToViewport(point(-600, -100)) * ratio
                second = view.WorldToViewport(point(600, -100)) * ratio
                margin = int((view.lineWidths["walls"] / 2 + 1.5) * ratio) + 1
                for x in range(round(first.x()) + margin, round(second.x()) - margin):
                    AssertNoOutline(image, x, round(first.y()), 2, fill, canvas, (scale, solid, phase, x))
                    samples += 1
                view.isPanning = True
                view.panOffset += point(3, 1) / ratio
                CompareDirect(view)
                view.isPanning = False
    view.close()
    print("PASS:", samples, "near-jamb pixels below 200 px/m, both grid policies and pan parity")


if __name__ == "__main__":
    Main()
