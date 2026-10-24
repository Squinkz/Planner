"""Native column curves and cached tolerance-based collision approximations."""
import math
from PySide6 import QtCore, QtGui
from planner_app.geometry.footprints import ColumnPolygon as BuildColumnPolygon, ColumnContains as ContainsColumn


def ColumnPath(column):
    center = (column.firstVertex + column.secondVertex) / 2
    along = (column.secondVertex - column.firstVertex) / 2
    length = math.hypot(along.x(), along.y())
    if length < 1e-8 or column.width <= 0:
        return QtGui.QPainterPath()
    key = (along.x(), along.y(), column.width)
    cached = getattr(column, "ellipsePathCache", None)
    if cached is None or cached[0] != key:
        across = QtCore.QPointF(-along.y(), along.x()) * (column.width / (2 * length))
        ellipse = QtGui.QPainterPath()
        ellipse.addEllipse(QtCore.QRectF(-1, -1, 2, 2))
        # Use a positive determinant so native ellipses match wall winding.
        transform = QtGui.QTransform(across.x(), across.y(), -along.x(), -along.y(), 0, 0)
        cached = (key, transform.map(ellipse))
        column.ellipsePathCache = cached
    return QtGui.QTransform().translate(center.x(), center.y()).map(cached[1])


def ColumnContains(column, position):
    return ContainsColumn((column.firstVertex.x(), column.firstVertex.y()),
                          (column.secondVertex.x(), column.secondVertex.y()), column.width,
                          (position.x(), position.y()))


def ColumnPolygon(column, tolerance = .5):
    center = (column.firstVertex + column.secondVertex) / 2
    along = (column.secondVertex - column.firstVertex) / 2
    length = math.hypot(along.x(), along.y())
    if length < 1e-8 or column.width <= 0:
        return QtGui.QPolygonF()
    key = (along.x(), along.y(), column.width, tolerance)
    cached = getattr(column, "ellipsePolygonCache", None)
    if cached is None or cached[0] != key:
        polygon = QtGui.QPolygonF([QtCore.QPointF(*point) for point in
                                  BuildColumnPolygon((along.x(), along.y()), column.width, tolerance)])
        cached = (key, polygon)
        column.ellipsePolygonCache = cached
    return cached[1].translated(center)
