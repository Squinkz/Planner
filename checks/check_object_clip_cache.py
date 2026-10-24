"""Transparent overlap clips reuse color-independent geometry and invalidate edits."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics import object_composite


def Main():
    app = QtWidgets.QApplication([])
    cache = {}
    for case, (color, offset, width) in enumerate((("black", 0, 1), ("#2468ab", 0, 1),
                                                 ("#ab6824", 13, 1), ("#2468ab", 13, 3))):
        device = object_composite.ObjectPaintDevice(QtCore.QSize(300, 250), "white")
        with QtGui.QPainter(device) as painter:
            painter.setPen(QtGui.QPen(QtGui.QColor(color), width))
            painter.setBrush(QtGui.QColor("white"))
            painter.drawRoundedRect(QtCore.QRectF(30 + offset, 30, 180, 150), 25, 25)
            painter.drawEllipse(QtCore.QRectF(120, 110, 120, 100))
            painter.drawLine(10, 125, 290, 125)
        images = []
        with patch.object(object_composite, "ClipPathCoverage", wraps = object_composite.ClipPathCoverage) as coverage:
            image = QtGui.QImage(300, 250, QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtGui.QColor("white"))
            with QtGui.QPainter(image) as painter:
                device.engine.Replay(painter, QtCore.QRectF(0, 0, 300, 250), clipCache = cache)
            if case == 1:
                assert coverage.call_count == 0, "Recolor recomputed native overlap masks"
            else:
                assert coverage.call_count > 0, "Geometry or line width edit reused stale masks"
            images.append(image)
        image = QtGui.QImage(300, 250, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor("white"))
        with QtGui.QPainter(image) as painter:
            device.engine.Replay(painter, QtCore.QRectF(0, 0, 300, 250))
        assert image == images[0], ("Cached clip changed pixels", case)
    assert len(cache["geometry"]) <= 8192
    # Ink-envelope culling depends on the actual stroke, even if a reshape
    # preserves its bounding rectangle and every background mask is unchanged.
    cache = {}
    for flipped in (False, True):
        device = object_composite.ObjectPaintDevice(QtCore.QSize(300, 250), "white")
        with QtGui.QPainter(device) as painter:
            painter.setPen(QtGui.QPen(QtGui.QColor("black"), 2))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            path = QtGui.QPainterPath(QtCore.QPointF(10, 10))
            path.lineTo(10 if flipped else 290, 240 if flipped else 10)
            path.lineTo(290, 240)
            painter.drawPath(path)
            painter.setBrush(QtGui.QColor("white"))
            for x in range(30, 280, 45):
                for y in range(30, 230, 40):
                    painter.drawEllipse(QtCore.QRectF(x, y, 30, 25))
        images = []
        for storage in (cache, None):
            image = QtGui.QImage(300, 250, QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtGui.QColor("white"))
            with patch.object(object_composite, "ClipPathCoverage", wraps = object_composite.ClipPathCoverage) as coverage:
                with QtGui.QPainter(image) as painter:
                    device.engine.Replay(painter, QtCore.QRectF(0, 0, 300, 250), clipCache = storage)
                assert coverage.call_count > 0, "Same-bounds reshape reused old ink coverage"
            images.append(image)
        assert images[0] == images[1], "Ink-envelope cache changed pixels after a reshape"


if __name__ == "__main__":
    Main()
