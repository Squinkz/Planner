"""A print preview page sharing model vectors while retaining local decorations."""
from PySide6 import QtCore, QtGui


class PrintVectorPage(QtCore.QObject):
    def __init__(self, scene, sceneBounds, drawingBounds, grid, decorations, layout, border, canvas, parent = None):
        super().__init__(parent)
        self.scene = scene
        self.sceneBounds = sceneBounds
        self.drawingBounds = drawingBounds
        self.grid = grid
        self.decorations = decorations
        self.size = QtCore.QSize(*layout["baselinePixels"])
        self.plot = QtCore.QRectF(border, border, *layout["drawingPixels"])
        self.canvas = QtGui.QColor(canvas)

    def defaultSize(self):
        return self.size

    def isValid(self):
        return self.scene is None or self.scene.isValid()

    def render(self, painter, target = None):
        if target is None:
            target = QtCore.QRectF(0, 0, painter.device().width(), painter.device().height())
        painter.save()
        try:
            painter.translate(target.topLeft())
            painter.scale(target.width() / self.size.width(), target.height() / self.size.height())
            painter.save()
            try:
                painter.setClipRect(self.plot, QtCore.Qt.ClipOperation.IntersectClip)
                painter.fillRect(self.plot, self.canvas)
                painter.drawPicture(QtCore.QPointF(), self.grid)
                if self.scene is not None:
                    x, y, width, height = self.drawingBounds
                    sx, sy, sw, sh = self.sceneBounds
                    scale = self.plot.width() / width
                    frame = QtCore.QRectF(self.plot.left() + (sx - x) * scale,
                                          self.plot.top() + (y + height - sy - sh) * scale,
                                          self.scene.viewBox.width(), self.scene.viewBox.height())
                    self.scene.render(painter, frame)
            finally:
                painter.restore()
            painter.drawPicture(QtCore.QPointF(), self.decorations)
        finally:
            painter.restore()
