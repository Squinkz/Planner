"""Transparent replay preserves chair curves at large export-bitmap origins."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.furnishings import FurnishingRenderer
from planner_app.graphics.object_composite import ObjectPaintDevice
from planner_app.paths import furnishingsDirectory


def Main():
    app = QtWidgets.QApplication([])
    colors = {"outline": "#333333", "background": "#ffffff", "missing": "#333333"}
    for name, angle in (("office_chair", -7.124), ("office_chair_armless", -165), ("office_chair_armless", 0)):
        renderer = FurnishingRenderer(furnishingsDirectory / f"images/{name}.svg", palette = colors, lineWidth = 1)
        for scale in (100, 250, 500):
            extent = 600 * scale / 1000
            size = round(extent + 30)
            baseline = QtGui.QImage(size, size, QtGui.QImage.Format.Format_ARGB32)
            baseline.fill(QtGui.QColor("white"))
            with QtGui.QPainter(baseline) as painter:
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                painter.translate(size / 2, size / 2)
                painter.rotate(angle)
                renderer.render(painter, QtCore.QRectF(-extent / 2, -extent / 2, extent, extent))
            for origin in (QtCore.QPointF(2300.127, 1275.654), QtCore.QPointF(4700.375, 3432.125)):
                device = ObjectPaintDevice(QtCore.QSize(6000, 6000), "white")
                with QtGui.QPainter(device) as painter:
                    painter.setClipRect(QtCore.QRectF(0, 0, 6000, 6000))
                    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                    painter.translate(origin)
                    painter.rotate(angle)
                    renderer.render(painter, QtCore.QRectF(-extent / 2, -extent / 2, extent, extent))
                replay = QtGui.QImage(size, size, QtGui.QImage.Format.Format_ARGB32)
                replay.fill(QtGui.QColor("white"))
                with QtGui.QPainter(replay) as painter:
                    painter.translate(size / 2 - origin.x(), size / 2 - origin.y())
                    device.engine.Replay(painter, QtCore.QRectF(0, 0, 6000, 6000))
                ink = missing = 0
                for y in range(size):
                    for x in range(size):
                        if baseline.pixelColor(x, y).lightness() < 180:
                            ink += 1
                            missing += replay.pixelColor(x, y).lightness() > 235
                assert missing <= max(5, ink * .02), (name, angle, scale, origin, missing, ink)
    print("PASS: armed/armless chair curves survive 100/250/500 px/m and large translated bitmap origins")


if __name__ == "__main__":
    Main()
