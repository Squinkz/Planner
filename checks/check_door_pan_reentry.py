"""Door swings entering exposed pan strips must include their hinge offset."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner_app.models import Wall, Door
from planner_app.viewport.widget import DrawingViewport
from check_pan_dpi import CompareDirect


def Main():
    app = QtWidgets.QApplication([])
    v = DrawingViewport()
    v.resize(826, 505)
    v.performanceTimer.stop()
    v.showMeasurements = False
    point = QtCore.QPointF
    wall = Wall(point(-2500, 0), point(2500, 0), 240, material = "Brick")
    v.walls = [wall]
    first, second = Door(wall, .332, .5), Door(wall, .5, .668)
    first.swingsOutwards = second.swingsOutwards = True
    second.hingeAtSecond = True
    v.windows = [first, second]
    v.show()
    app.processEvents()
    v.performanceLabel.hide()
    for zoom in (.75, .833333333333, .862, 1.25):
        v.zoom = zoom
        for step in (point(0, -20), point(0, 20), point(-20, 0), point(20, 0)):
            distance = v.width() if step.x() else v.height()
            v.panOffset = -step * (distance / 20)
            v.viewportPanRaster = None
            v.isPanning = True
            v.grab()
            for frame in range((distance + 19) // 20 + 3):
                v.panOffset += step
                CompareDirect(v)
            v.isPanning = False
            CompareDirect(v)
    v.close()
    print("PASS: mirrored door swings re-enter all viewport edges at varied zooms without clipped cached pixels")


if __name__ == "__main__":
    Main()
