"""Vector stroke reuse, fractional camera accuracy and native appearance."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner_app.models import Wall, Window, Door, PocketDoor
from planner_app.viewport.widget import DrawingViewport
from check_pan_dpi import CompareDirect


def CompareFreshNative(v):
    # Existing strip tests cover retained scene pixels. This check isolates the
    # vector stroke against the native renderer at each exact camera position.
    v.viewportPanRaster = None
    CompareDirect(v)


def Main():
    app = QtWidgets.QApplication([])
    v = DrawingViewport()
    v.performanceTimer.stop()
    v.resize(1001, 701)
    v.showTips = v.showMeasurements = False
    point = QtCore.QPointF
    vertices = [point(-19000, -7000), point(-15000, -3000), point(-19000, -1900), point(-23000, -5900)]
    v.walls = [Wall(vertices[index], vertices[(index + 1) % 4], 240, material = "Brick") for index in range(4)]
    v.walls.append(Wall(point(10000, 8000), point(14000, 8000), 200, material = "Lumber"))
    v.windows = [Window(v.walls[0], .2, .4), Door(v.walls[1], .3, .6), PocketDoor(v.walls[3], .2, .5)]
    v.zoom = .8
    scale = v.zoom * v.basePixelsPerMillimeter
    v.panOffset = point(19000 * scale, -4500 * scale)
    v.show()
    app.processEvents()
    v.performanceLabel.hide()
    v.isPanning = True
    CompareFreshNative(v)
    stroke = v.scenePreparation[1]['wallStroke'][1]
    for delta in (point(3, 1), point(-7, 2), point(16, -5), point(.25, .3), point(400, -300)):
        v.panOffset += delta / v.devicePixelRatioF()
        CompareFreshNative(v)
        assert v.scenePreparation[1]['wallStroke'][1] is stroke, 'Camera movement regenerated the vector stroke'
    for change in ('geometry', 'width', 'zoom', 'visibility', 'viewport', 'no-ink'):
        previous = v.scenePreparation[1]['wallStroke'][1]
        if change == 'geometry':
            v.walls[0].firstVertex += point(40, -20)
        elif change == 'width':
            v.lineWidths['walls'] += 1
        elif change == 'zoom':
            v.zoom *= 1.1
        elif change == 'visibility':
            v.visibility['Windows'] = False
        elif change == 'viewport':
            v.resize(1100, 750)
        else:
            v.lineWidths['walls'] = 0
        CompareFreshNative(v)
        if change in ('geometry', 'width', 'zoom'):
            assert v.scenePreparation[1]['wallStroke'][1] is not previous, change
    v.viewportRasterByteLimit = v.width() * v.height() * 4
    CompareFreshNative(v)
    v.grab()
    assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
    v.isPanning = False
    CompareDirect(v)
    v.close()
    print("PASS: pan vector stroke reuse, fractional motion, appearance, invalidation and memory fallback")


if __name__ == "__main__":
    Main()
