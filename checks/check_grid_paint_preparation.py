"""Grid/ruler preparation retains native pixels across modes and physical scales."""
import math
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.viewport.widget import DrawingViewport
from planner_app.viewport.rendering import RenderingMixin
from fixtures.grid_paint_reference_20261028 import ReferenceDrawGridBackground


def Main():
    app = QtWidgets.QApplication([])
    view = DrawingViewport()
    view.resize(321, 247)
    view.panOffset = QtCore.QPointF(-.37, .81)
    view.gridOrigin = (-12.2, 7.8)
    view.roomDetection.path = QtGui.QPainterPath()
    view.roomDetection.path.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
    view.roomDetection.path.addPolygon(QtGui.QPolygonF([QtCore.QPointF(-500, -300), QtCore.QPointF(650, -175),
        QtCore.QPointF(470, 700), QtCore.QPointF(-500, 600)]))
    view.roomDetection.path.closeSubpath()
    view.roomDetection.path.addRect(QtCore.QRectF(-100, 50, 200, 200))
    modes = ({}, dict(gridOnly = True), dict(drawGrid = False), dict(markingsOnly = True),
             dict(allEdges = True), dict(allEdges = True, markingsOnly = True), dict(gridOnly = True, drawGrid = False))
    originalIntensities = dict(view.gridIntensities)
    cases = 0
    for ratio in (1, 1.25, 2):
        for units in ("Adaptive Metric", "Millimeters", "Inches", "Feet and Inches"):
            view.unitsMode = units
            for grid, solid, floors, zero in ((True, False, True, None), (False, False, True, None),
                    (True, True, True, None), (True, True, False, None), (True, False, True, "minor"),
                    (True, False, True, "overall")):
                view.showGrid, view.solidRooms, view.floors = grid, solid, floors
                view.gridIntensities.update(originalIntensities)
                if zero is not None: view.gridIntensities[zero] = 0
                for options in modes:
                    for pixmap in (False, True):
                        for antialias in (False, True):
                            results = []
                            for function in (ReferenceDrawGridBackground, RenderingMixin.DrawGridBackground):
                                size = QtCore.QSize(math.ceil(view.width() * ratio), math.ceil(view.height() * ratio))
                                image = (QtGui.QPixmap(size) if pixmap else
                                         QtGui.QImage(size, QtGui.QImage.Format.Format_ARGB32))
                                image.setDevicePixelRatio(ratio)
                                image.fill(QtGui.QColor("#d1d3d7"))
                                painter = QtGui.QPainter(image)
                                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, antialias)
                                value = function(view, painter, view.DrawingRect(), view.WorldToViewport(QtCore.QPointF()),
                                                 view.basePixelsPerMillimeter * view.zoom, **options)
                                font = painter.font()
                                painter.end()
                                results.append((image.toImage() if pixmap else image, value, font))
                            assert results[0] == results[1], (ratio, units, grid, solid, floors, zero, options, pixmap, antialias)
                            cases += 1
    view.close()
    print("PASS:", cases, "exact frozen grid images, returned units and painter fonts across flags, units, rooms and DPR")


if __name__ == "__main__": Main()
