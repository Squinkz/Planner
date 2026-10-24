"""Small native wall drawing surfaces versus the same retained pan history."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Door, Window, PocketDoor, Railing
from planner_app.viewport import rendering
from planner_app.viewport.widget import DrawingViewport


def CompareNativePatch(v, delta):
    before = (v.viewportPanRaster.copy(), v.viewportPanKey, v.viewportPanOrigin, v.viewportPanState)
    v.panOffset += delta
    actual = v.grab().toImage()
    after = (v.viewportPanRaster, v.viewportPanKey, v.viewportPanOrigin, v.viewportPanState)
    v.viewportPanRaster, v.viewportPanKey, v.viewportPanOrigin, v.viewportPanState = before
    with patch.object(v, "DrawPanWallStroke", side_effect = lambda painter, path, brush, *unused: painter.fillPath(path, brush)):
        expected = v.grab().toImage()
    v.viewportPanRaster, v.viewportPanKey, v.viewportPanOrigin, v.viewportPanState = after
    first, second = memoryview(actual.constBits()), memoryview(expected.constBits())
    changed = [index for index, (a, b) in enumerate(zip(first.cast("I"), second.cast("I"))) if a != b]
    if changed:
        maximum = max(abs(first[index * 4 + channel] - second[index * 4 + channel]) for index in changed for channel in range(4))
        assert maximum <= 3 and len(changed) <= max(64, actual.width() * actual.height() // 1000), (v.devicePixelRatioF(), delta, maximum, len(changed))


def Main():
    app = QtWidgets.QApplication([])
    v = DrawingViewport()
    v.performanceTimer.stop()
    v.showTips = v.showMeasurements = False
    point = QtCore.QPointF
    vertices = [point(-19000, -7000), point(-15000, -3000), point(-19000, -1900), point(-23000, -5900)]
    v.walls = [Wall(vertices[index], vertices[(index + 1) % 4], 240, material = "Brick") for index in range(4)]
    v.windows = [Door(v.walls[0], .2, .4), Window(v.walls[1], .3, .6), PocketDoor(v.walls[3], .25, .55)]
    v.zoom = .8
    scale = v.zoom * v.basePixelsPerMillimeter
    v.panOffset = point(19000 * scale, -4500 * scale)
    v.show()
    app.processEvents()
    v.performanceLabel.hide()
    ratio = v.devicePixelRatioF()
    originalCopy = QtGui.QPixmap.copy
    copies = []

    def Copy(source, *args):
        if source.paintingActive():
            copies.append(args[0])
        return originalCopy(source, *args)

    for width, height in ((1000, 700), (1001, 701)):
        v.resize(width, height)
        v.isPanning = True
        v.viewportPanRaster = None
        v.grab()
        with patch.object(QtGui.QPixmap, "copy", Copy):
            for delta in (point(3, 1), point(-7, 2), point(0, -5), point(16, 0), point(-5, -3)):
                CompareNativePatch(v, delta / ratio)
    assert copies, 'Fixture did not exercise patch painting'
    assert all(rect.width() <= 64 or rect.height() <= 64 for rect in copies), copies
    farRailing = Railing(point(10000, 15000), point(13000, 15000))
    v.walls.append(farRailing)
    v.viewportPanRaster = None
    v.grab()
    with patch.object(rendering.Paths, "Difference", wraps = rendering.Paths.Difference) as difference:
        v.panOffset += point(3, 1) / ratio
        v.grab()
        assert difference.call_count == 0, 'Offscreen railings built an unused wall mask'
    assert farRailing in v.viewportPanState[10], 'Culling removed railing handle/measurement state'
    nearRailing = Railing(v.ViewportToWorld(point(29, 100)), v.ViewportToWorld(point(29, 500)))
    v.walls.append(nearRailing)
    v.viewportPanRaster = None
    v.grab()
    with patch.object(rendering.Paths, "Difference", wraps = rendering.Paths.Difference) as difference:
        v.panOffset += point(3, 1) / ratio
        v.grab()
        assert difference.call_count > 0, 'Visible railing lost its wall occlusion'
    v.resize(1000, 700)
    v.viewportPanRaster = None
    v.grab()
    v.viewportRasterByteLimit = v.rasterCacheBudget.RetainedBytes()
    copies.clear()
    with patch.object(QtGui.QPixmap, "copy", Copy):
        CompareNativePatch(v, point(3, 1) / ratio)
    assert not copies, 'Patch allocation exceeded the aggregate surface budget'
    v.close()
    print("PASS: guarded wall patches preserve native pan history, clip masks, overlaps and viewport fringes")


if __name__ == "__main__":
    Main()
