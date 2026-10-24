"""Qt point adapters for the numeric polygon operations."""
from PySide6 import QtCore
from planner_app.geometry.polygons import SplitPolygon as SplitCoordinates, SubtractConvexPolygon as SubtractCoordinates


def SplitPolygon(points, first, second, orientation):
    coordinates = [(point.x(), point.y()) for point in points]
    inside, outside = SplitCoordinates(coordinates, (first.x(), first.y()), (second.x(), second.y()), orientation)
    return ([QtCore.QPointF(x, y) for x, y in inside], [QtCore.QPointF(x, y) for x, y in outside])


def SubtractConvexPolygon(points, cutter):
    coordinates = [(point.x(), point.y()) for point in points]
    cutterCoordinates = [(point.x(), point.y()) for point in cutter]
    fragments = SubtractCoordinates(coordinates, cutterCoordinates)
    if len(fragments) == 1 and fragments[0] is coordinates:
        return [points]
    return [[QtCore.QPointF(x, y) for x, y in polygon] for polygon in fragments]
