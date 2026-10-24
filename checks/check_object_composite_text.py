"""Transparent-object replay must fill text glyphs without outlining them."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.object_composite import ObjectPaintDevice
from planner_app.graphics.fonts import LoadApplicationFonts


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts()
    size = QtCore.QSize(360, 110)
    native = QtGui.QImage(size, QtGui.QImage.Format.Format_ARGB32)
    native.fill(QtGui.QColor("white"))
    device = ObjectPaintDevice(size, "#ffffff")
    for target in (native, device):
        with QtGui.QPainter(target) as painter:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            painter.setFont(QtGui.QFont("Noto Sans", 36))
            painter.setPen(QtGui.QPen(QtGui.QColor("#222222"), 6))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawText(QtCore.QPointF(15, 75), "Oven")
    replay = QtGui.QImage(size, QtGui.QImage.Format.Format_ARGB32)
    replay.fill(QtGui.QColor("white"))
    with QtGui.QPainter(replay) as painter:
        device.engine.Replay(painter, QtCore.QRectF(0, 0, size.width(), size.height()))
    ink = []
    for image in (native, replay):
        ink.append(sum((255 - image.pixelColor(x, y).red()) / 255
                       for y in range(image.height()) for x in range(image.width())))
    assert abs(ink[1] / ink[0] - 1) < .08, ink
    assert device.engine.commands and all(command[1].style() == QtCore.Qt.PenStyle.NoPen
                                         for command in device.engine.commands), "Text received an outline stroke"
    native.save(str(Path(__file__).resolve().parent.parent / "screenshots" / "object-text-solid.png"))
    replay.save(str(Path(__file__).resolve().parent.parent / "screenshots" / "object-text-transparent.png"))
    print("PASS: replay text matches native weight and foreground fill.")


if __name__ == "__main__":
    Main()
