"""Capture SVG background fills as vector silhouettes using Qt's SVG renderer."""
import math
from PySide6 import QtCore, QtGui


class BackgroundPathEngine(QtGui.QPaintEngine):
    def __init__(self):
        super().__init__(QtGui.QPaintEngine.PaintEngineFeature.AllFeatures)
        self.path = QtGui.QPainterPath()
        self.transform = QtGui.QTransform()
        self.brush = QtGui.QBrush()
        self.opacity = 1.0

    def begin(self, device):
        return True

    def end(self):
        return True

    def type(self):
        return QtGui.QPaintEngine.Type.User

    def updateState(self, state):
        self.transform = state.transform()
        self.brush = state.brush()
        self.opacity = state.opacity()

    def drawPath(self, path):
        if (self.brush.style() == QtCore.Qt.BrushStyle.NoBrush or self.opacity <= 0
                or self.brush.color() != QtGui.QColor("white")):
            return
        mapped = self.transform.map(path)
        painter = self.painter()
        if painter.hasClipping():
            mapped = mapped.intersected(self.transform.map(painter.clipPath()))
        self.path = self.path.united(mapped)

    def drawPolygon(self, points, mode):
        if mode == QtGui.QPaintEngine.PolygonDrawMode.PolylineMode:
            return
        path = QtGui.QPainterPath()
        path.setFillRule(QtCore.Qt.FillRule.WindingFill if mode == QtGui.QPaintEngine.PolygonDrawMode.WindingMode
                         else QtCore.Qt.FillRule.OddEvenFill)
        path.addPolygon(QtGui.QPolygonF(points))
        path.closeSubpath()
        self.drawPath(path)

    def drawRects(self, rects):
        for rect in rects:
            path = QtGui.QPainterPath()
            path.addRect(QtCore.QRectF(rect))
            self.drawPath(path)

    def drawEllipse(self, rect):
        path = QtGui.QPainterPath()
        path.addEllipse(QtCore.QRectF(rect))
        self.drawPath(path)

    def drawPixmap(self, rect, pixmap, source):
        pass


class BackgroundPathDevice(QtGui.QPaintDevice):
    def __init__(self, size):
        super().__init__()
        self.size = size
        self.engine = BackgroundPathEngine()

    def paintEngine(self):
        return self.engine

    def metric(self, metric):
        values = {self.PaintDeviceMetric.PdmWidth: self.size.width(), self.PaintDeviceMetric.PdmHeight: self.size.height(),
                  self.PaintDeviceMetric.PdmWidthMM: max(1, round(self.size.width() * 25.4 / 96)),
                  self.PaintDeviceMetric.PdmHeightMM: max(1, round(self.size.height() * 25.4 / 96)),
                  self.PaintDeviceMetric.PdmDpiX: 96, self.PaintDeviceMetric.PdmDpiY: 96,
                  self.PaintDeviceMetric.PdmPhysicalDpiX: 96, self.PaintDeviceMetric.PdmPhysicalDpiY: 96,
                  self.PaintDeviceMetric.PdmDepth: 32, self.PaintDeviceMetric.PdmNumColors: 0,
                  self.PaintDeviceMetric.PdmDevicePixelRatio: 1, self.PaintDeviceMetric.PdmDevicePixelRatioScaled: 65536}
        return values.get(metric, 0)


def FurnishingBackgroundPath(renderer):
    rect = renderer.viewBoxF()
    device = BackgroundPathDevice(QtCore.QSize(max(1, math.ceil(rect.width())), max(1, math.ceil(rect.height()))))
    painter = QtGui.QPainter(device)
    try:
        renderer.render(painter, rect)
    finally:
        painter.end()
    return device.engine.path
