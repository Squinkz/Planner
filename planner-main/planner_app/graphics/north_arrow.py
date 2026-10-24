"""Split north arrow with an upright, outlined N for raster/vector output."""
from PySide6 import QtCore, QtGui
from . import palette
from .linework import LinePen


def DrawNorthArrow(painter, center, width, length, angle, color, lineWidth, solidBackground = True):
    rotation = QtGui.QTransform().translate(center.x(), center.y()).rotate(-angle)
    tip = QtCore.QPointF(0, -length * .20)
    notch = QtCore.QPointF(0, length * .28)
    left = QtCore.QPointF(-width * .42, length * .44)
    right = QtCore.QPointF(width * .42, length * .44)
    painter.save()
    try:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(LinePen(color, lineWidth))
        painter.setBrush(QtGui.QColor(palette.themeColors["canvas"]) if solidBackground else QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPolygon(rotation.map(QtGui.QPolygonF([tip, left, notch])))
        painter.setBrush(QtGui.QColor(color))
        painter.drawPolygon(rotation.map(QtGui.QPolygonF([tip, notch, right])))
        font = QtGui.QFont(palette.labelFont)
        font.setPixelSize(100)
        font.setBold(True)
        letter = QtGui.QPainterPath()
        letter.addText(QtCore.QPointF(), font, "N")
        bounds = letter.boundingRect()
        scale = min(width * .34 / bounds.width(), length * .20 / bounds.height())
        position = rotation.map(QtCore.QPointF(0, -length * .36))
        transform = QtGui.QTransform().translate(position.x(), position.y()).scale(scale, scale)
        transform.translate(-bounds.center().x(), -bounds.center().y())
        painter.fillPath(transform.map(letter), QtGui.QColor(color))
    finally:
        painter.restore()
