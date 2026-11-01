"""Retained CPU dimension items with the viewport picture's exact primitives."""
import math

from PySide6 import QtCore, QtGui, QtWidgets
from .linework import LinePen
from .measurement_text import MeasurementTextPath
from .palette import themeColors
from .text import TextPath
from planner_app.units import FormatLength, GridUnit, imperialModes


class DimensionLines(QtWidgets.QGraphicsRectItem):
    def paint(self, painter, option, widget = None):
        painter.setPen(self.stroke)
        # QPicture replays recorded drawLines as separate two-point polylines.
        # Qt rasterizes those differently from drawLine at fractional DPI.
        for line in self.lines:
            painter.drawPolyline(line)


class RetainedDimensions:
    def __init__(self, viewport, layout, style, font, device, sceneState):
        self.layout = layout
        self.style = style
        self.labelStyle = (font.toString(), device.logicalDpiX(), device.logicalDpiY(), device.devicePixelRatioF())
        self.metrics = QtGui.QFontMetrics(font, device)
        self.scene = QtWidgets.QGraphicsScene()
        self.scene.setSceneRect(-1e8, -1e8, 2e8, 2e8)
        self.scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)
        self.entries = []
        highlightedIds, invalidWalls, invalidCounterIds = sceneState[1], sceneState[3], sceneState[4]
        for index, record in enumerate(layout[4]):
            first, second, owners, tier, overlay, displayLength = record
            isSelected = overlay and any(id(obj) in highlightedIds and id(obj) not in invalidWalls
                                        and id(obj) not in invalidCounterIds for obj in owners)
            selectedColor = next((viewport.SelectionColor(obj) for obj in owners if id(obj) in highlightedIds
                and id(obj) not in invalidWalls and id(obj) not in invalidCounterIds), themeColors["selectionOutline"])
            parent = DimensionLines()
            parent.stroke = LinePen(selectedColor if isSelected else themeColors["measurementLine"], viewport.lineWidths["dimensions"])
            parent.setPen(parent.stroke)
            parent.lines = []
            parent.setZValue(index)
            self.scene.addItem(parent)
            # A filled path reproduces QPicture's fillRect replay. A native
            # rectangle item takes another raster path and changes edge pixels.
            label = QtWidgets.QGraphicsPathItem(parent)
            label.setPen(QtCore.Qt.PenStyle.NoPen)
            label.setBrush(QtGui.QColor(themeColors["canvas"]))
            glyph = QtWidgets.QGraphicsPathItem(label)
            glyph.setPen(QtCore.Qt.PenStyle.NoPen)
            glyph.setBrush(QtGui.QColor(selectedColor if isSelected else themeColors["objectOutline"]))
            self.entries.append([record, parent, label, glyph, isSelected, None])

    def Paint(self, viewport, painter, drawingRect, cull):
        measurementUnit = GridUnit(viewport.GridSteps()[0], viewport.unitsMode)[1]
        labels = self.layout[5]
        for position, entry in enumerate(self.entries):
            (first, second, owners, tier, overlay, displayLength), parent, label, glyph, isSelected, textUnit = entry
            firstPoint, secondPoint = viewport.WorldToViewport(first), viewport.WorldToViewport(second)
            firstX, firstY = firstPoint.toTuple()
            secondX, secondY = secondPoint.toTuple()
            directionX, directionY = secondX - firstX, secondY - firstY
            screenLength = math.hypot(directionX, directionY)
            margin = max(80, 40 + 30 * tier)
            bounds = QtCore.QRectF(firstPoint, secondPoint).normalized().adjusted(-margin, -margin, margin, margin)
            visible = ((screenLength >= 24 - 1e-6 or isSelected and screenLength > 1e-8)
                       and (not cull or bounds.intersects(drawingRect)))
            parent.setVisible(visible)
            if not visible:
                continue
            # Use the original projected endpoints and operation order. Building
            # a local shape and scaling it introduces subpixel rounding changes.
            normalX, normalY = directionY / screenLength, -directionX / screenLength
            offset = 20 + 30 * tier
            startX, startY = firstX + normalX * offset, firstY + normalY * offset
            endX, endY = secondX + normalX * offset, secondY + normalY * offset
            normalPadX, normalPadY = normalX * 4, normalY * 4
            tickX = (directionX / screenLength + normalX) * 3
            tickY = (directionY / screenLength + normalY) * 3
            lines = [(startX, startY, endX, endY)]
            for x, y, dimensionX, dimensionY in ((firstX, firstY, startX, startY), (secondX, secondY, endX, endY)):
                lines.append((x + normalPadX, y + normalPadY, dimensionX + normalPadX, dimensionY + normalPadY))
                lines.append((dimensionX - tickX, dimensionY - tickY, dimensionX + tickX, dimensionY + tickY))
            parent.lines = [QtGui.QPolygonF([QtCore.QPointF(x, y), QtCore.QPointF(u, v)]) for x, y, u, v in lines]
            parent.setRect(bounds)
            angle = math.degrees(math.atan2(directionY, directionX))
            if angle > 90:
                angle -= 180
            elif angle < -90:
                angle += 180
            transform = QtGui.QTransform().translate((startX + endX) / 2, (startY + endY) / 2).rotate(angle)
            label.setTransform(transform)
            if textUnit != measurementUnit:
                labelKey = (position, measurementUnit, self.labelStyle)
                cachedLabel = labels.get(labelKey)
                text = (cachedLabel[0] if cachedLabel is not None else FormatLength(
                    QtCore.QLineF(first, second).length() if displayLength is None else displayLength,
                    viewport.unitsMode, adaptive = measurementUnit, includeUnit = False, precision = viewport.measurementPrecision))
                if viewport.unitsMode in imperialModes:
                    path = MeasurementTextPath(text, self.labelStyle[0], self.labelStyle[2])
                    width = path.boundingRect().width() + 12
                    glyph.setPos(-path.boundingRect().center())
                else:
                    width = self.metrics.horizontalAdvance(text) + 12
                    path, advance, height, ascent = TextPath(text, self.labelStyle[0], self.labelStyle[2], width)
                    glyph.setPos(-advance / 2, -height / 2 + ascent)
                glyph.setPath(path)
                background = QtGui.QPainterPath()
                background.addRect(QtCore.QRectF(-width / 2, -10, width, 20))
                label.setPath(background)
                entry[-1] = measurementUnit
                if cachedLabel is None and len(labels) < 4096:
                    labels[labelKey] = (text, width)
        painter.save()
        try:
            # Items use absolute viewport coordinates. The identity mapping
            # retains the existing clip, glyph transforms and logical pen widths.
            self.scene.render(painter, drawingRect, drawingRect, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio)
        finally:
            painter.restore()
