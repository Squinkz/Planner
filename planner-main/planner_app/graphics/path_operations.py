"""Qt implementation of the native path contract; native algorithms and handles."""
from PySide6 import QtCore, QtGui


class QtPathOperations:
    # Bind native descriptors directly: no copies, flattening, caches or Python
    # dispatch wrappers around boolean/query operations in the painting hot path.
    Empty = staticmethod(QtGui.QPainterPath)
    Union = staticmethod(QtGui.QPainterPath.united)
    Intersection = staticmethod(QtGui.QPainterPath.intersected)
    Difference = staticmethod(QtGui.QPainterPath.subtracted)
    Contains = staticmethod(QtGui.QPainterPath.contains)
    Intersects = staticmethod(QtGui.QPainterPath.intersects)
    Contours = staticmethod(QtGui.QPainterPath.toSubpathPolygons)
    FillPolygons = staticmethod(QtGui.QPainterPath.toFillPolygons)

    @staticmethod
    def PrepareStroke(width = None, cap = None, join = None, miterLimit = None,
                      dashPattern = None, dashOffset = None, curveThreshold = None):
        stroke = QtGui.QPainterPathStroker()
        if width is not None:
            stroke.setWidth(width)
        if cap is not None:
            stroke.setCapStyle({"flat": QtCore.Qt.PenCapStyle.FlatCap,
                                "square": QtCore.Qt.PenCapStyle.SquareCap,
                                "round": QtCore.Qt.PenCapStyle.RoundCap}[cap])
        if join is not None:
            stroke.setJoinStyle({"miter": QtCore.Qt.PenJoinStyle.MiterJoin,
                                 "bevel": QtCore.Qt.PenJoinStyle.BevelJoin,
                                 "round": QtCore.Qt.PenJoinStyle.RoundJoin,
                                 "svg-miter": QtCore.Qt.PenJoinStyle.SvgMiterJoin}[join])
        if miterLimit is not None:
            stroke.setMiterLimit(miterLimit)
        if dashPattern is not None:
            stroke.setDashPattern(dashPattern)
        if dashOffset is not None:
            stroke.setDashOffset(dashOffset)
        if curveThreshold is not None:
            stroke.setCurveThreshold(curveThreshold)
        # The bound method owns its stroker; it remains reusable by the caller.
        return stroke.createStroke

    @staticmethod
    def PreparePenStroke(pen, width = None):
        """Desktop-only pen adapter, retaining Qt dash/cosmetic/default behavior."""
        stroke = QtGui.QPainterPathStroker(pen)
        if width is not None:
            stroke.setWidth(width)
        return stroke.createStroke


Paths = QtPathOperations()
