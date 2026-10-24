"""Presentation borders shared by raster/vector exports and viewport previews."""
import math
from PySide6 import QtCore, QtGui
from planner_app.graphics.palette import themeColors


def DrawRulerZones(painter, crop, size, source, origin, pixelsPerMillimeter):
    """Place an ordinary ruler inside a separate outer reference-zone band."""
    rulerSize = size // 2
    zonesSize = size - rulerSize
    frameOrigin = crop.topLeft() - QtCore.QPointF(rulerSize, rulerSize)
    previousSize, previousRulerSize = source.size(), source.rulerSize
    painter.save()
    try:
        source.rulerSize = rulerSize
        source.resize(math.ceil(crop.width()) + 2 * rulerSize, math.ceil(crop.height()) + 2 * rulerSize)
        painter.translate(frameOrigin)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        rect = QtCore.QRectF(rulerSize, rulerSize, crop.width(), crop.height())
        unit = source.DrawGridBackground(painter, rect, origin - frameOrigin, pixelsPerMillimeter,
                                         drawGrid = False, allEdges = True)
        source.DrawRulerFrame(painter, unit, allEdges = True)
    finally:
        painter.restore()
        source.rulerSize = previousRulerSize
        source.resize(previousSize)
    painter.save()
    try:
        font = QtGui.QFont(source.font())
        font.setPointSizeF(8)
        painter.setFont(font)
        DrawExportBorder(painter, crop.adjusted(-rulerSize, -rulerSize, rulerSize, rulerSize), zonesSize, "Reference Zones",
                         backgroundColor = QtGui.QColor(themeColors["rulerBackground"]).darker(110))
    finally:
        painter.restore()


def DrawExportBorder(painter, crop, size, style, backgroundColor = None):
    outer = crop.adjusted(-size, -size, size, size)
    painter.save()
    try:
        background = QtGui.QPainterPath()
        background.addRect(outer)
        background.addRect(crop)
        background.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
        painter.fillPath(background, backgroundColor if backgroundColor is not None else QtGui.QColor(themeColors["rulerBackground"]))
        if style == "Plain":
            return
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["rulerMajorTick"]), 1))
        frame = crop.adjusted(-size / 2, -size / 2, size / 2, size / 2)
        if style == "Frame":
            painter.drawRect(frame)
        elif style == "Corner Marks":
            arm = min(max(8, size), frame.width() / 4, frame.height() / 4)
            for corner, directionX, directionY in (
                    (frame.topLeft(), 1, 1), (frame.topRight(), -1, 1),
                    (frame.bottomLeft(), 1, -1), (frame.bottomRight(), -1, -1)):
                painter.drawLine(corner, corner + QtCore.QPointF(directionX * arm, 0))
                painter.drawLine(corner, corner + QtCore.QPointF(0, directionY * arm))
        elif style == "Reference Zones":
            painter.drawRect(outer.adjusted(1, 1, -1, -1))
            painter.drawRect(crop)
            for x, outerX in ((crop.left(), outer.left()), (crop.right(), outer.right())):
                for y, outerY in ((crop.top(), outer.top()), (crop.bottom(), outer.bottom())):
                    corner = QtCore.QPointF(x, y)
                    painter.drawLine(corner, QtCore.QPointF(x, outerY))
                    painter.drawLine(corner, QtCore.QPointF(outerX, y))
            columns = max(1, math.ceil(crop.width() / 200))
            rows = max(1, math.ceil(crop.height() / 200))
            painter.setPen(QtGui.QColor(themeColors["rulerText"]))
            for horizontal, count in ((True, columns), (False, rows)):
                for index in range(count):
                    if horizontal:
                        label = str(index + 1)
                        start = crop.left() + crop.width() * index / count
                        extent = crop.width() / count
                        cells = (QtCore.QRectF(start, outer.top(), extent, size),
                                 QtCore.QRectF(start, crop.bottom(), extent, size))
                    else:
                        # Alphabetic row IDs continue as AA, AB, ... after Z.
                        label = ""
                        number = index + 1
                        while number:
                            number, remainder = divmod(number - 1, 26)
                            label = chr(65 + remainder) + label
                        start = crop.top() + crop.height() * index / count
                        extent = crop.height() / count
                        cells = (QtCore.QRectF(outer.left(), start, size, extent),
                                 QtCore.QRectF(crop.right(), start, size, extent))
                    for cell in cells:
                        painter.drawText(cell, QtCore.Qt.AlignmentFlag.AlignCenter, label)
                        if index:
                            painter.drawLine(cell.topLeft(), cell.bottomLeft() if horizontal else cell.topRight())
    finally:
        painter.restore()
