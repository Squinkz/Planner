"""Retained native model command experiment, deliberately outside production.

This measures the potential of native submission. Captured pixel-dependent
clips, pattern origins and SVG fixed-size elements need separate treatment
before this could preserve the production renderer's appearance at every zoom.
"""
import math

from PySide6 import QtCore, QtGui
from planner_app.graphics.text import PathTextPainter


class RetainedModel:
    def __init__(self, viewport):
        self.origin = viewport.WorldToViewport(QtCore.QPointF())
        self.scale = viewport.basePixelsPerMillimeter * viewport.zoom
        drawingRect = QtCore.QRectF(-1e6, -1e6, 2e6, 2e6)
        self.picture = QtGui.QPicture()
        with CosmeticRecorder(self.picture) as painter:
            painter.setFont(viewport.viewportBackgroundFont)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            self.state = viewport.DrawScene(painter, drawingRect, self.origin, self.scale, drawAnnotations = False)
            viewport.DrawLabels(painter, self.scale, self.state[1], drawOutlines = False, drawingRect = drawingRect)

    def Paint(self, viewport, painter):
        origin = viewport.WorldToViewport(QtCore.QPointF())
        ratio = viewport.basePixelsPerMillimeter * viewport.zoom / self.scale
        painter.save()
        painter.translate(origin)
        painter.scale(ratio, ratio)
        painter.translate(-self.origin)
        painter.drawPicture(QtCore.QPointF(), self.picture)
        painter.restore()
        return self.state


class CosmeticRecorder(PathTextPainter):
    def setPen(self, pen):
        pen = QtGui.QPen(pen)
        if pen.style() != QtCore.Qt.PenStyle.NoPen:
            if not pen.isCosmetic():
                pen.setWidthF(pen.widthF() * math.sqrt(abs(self.worldTransform().determinant())))
            pen.setCosmetic(True)
        super().setPen(pen)
