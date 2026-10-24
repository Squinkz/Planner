"""Qt path adapter for the numeric tapered fireplace body."""
from PySide6 import QtGui
from planner_app.geometry.footprints import FireplacePolygon


def FireplacePath(fireplace):
    direction, normal = fireplace.Axes()
    polygon = FireplacePolygon((fireplace.firstVertex.x(), fireplace.firstVertex.y()),
                               (fireplace.secondVertex.x(), fireplace.secondVertex.y()),
                               (direction.x(), direction.y()), (normal.x(), normal.y()),
                               fireplace.width, fireplace.depth, fireplace.depthOffset, fireplace.swingsOutwards)
    path = QtGui.QPainterPath()
    for index, point in enumerate(polygon):
        path.moveTo(*point) if index == 0 else path.lineTo(*point)
    path.closeSubpath()
    return path
