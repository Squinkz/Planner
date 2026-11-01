"""Isolated CPU retained-annotation experiment. No production code imports this."""
import math

from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.fonts import fontFamily
from planner_app.graphics.linework import LinePen
from planner_app.graphics.measurement_text import MeasurementTextPath
from planner_app.graphics.palette import themeColors
from planner_app.graphics.text import TextPath
from planner_app.models import MeasurementGuide, AngleGuide
from planner_app.units import FormatLength, GridUnit, imperialModes


class RetainedAnnotations:
    def __init__(self, viewport, painter):
        self.scene = QtWidgets.QGraphicsScene()
        self.scene.setSceneRect(-1e8, -1e8, 2e8, 2e8)
        self.scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)
        self.entries = []
        self.viewport = viewport
        self.font = QtGui.QFont(painter.font())
        self.font.setFamily(fontFamily)
        self.dpi = painter.device().logicalDpiY()
        records = viewport.measurementLabelRecords[4]
        assert not any(isinstance(guide, AngleGuide) for guide in viewport.viewportSceneState[-1])
        assert not any(isinstance(owners[0], MeasurementGuide) for first, second, owners, tier, overlay, length in records)
        assert not viewport.SelectionEntries(), "This frozen-scene prototype does not support selections or edits."
        pen = LinePen(themeColors["measurementLine"], viewport.lineWidths["dimensions"])
        pen.setWidthF(pen.widthF() * viewport.devicePixelRatioF())
        pen.setCosmetic(True)
        for index, (first, second, owners, tier, overlay, displayLength) in enumerate(records):
            dx, dy = second.x() - first.x(), first.y() - second.y()
            worldLength = math.hypot(dx, dy)
            if worldLength < 1e-8:
                continue
            normalX, normalY = dy / worldLength, -dx / worldLength
            offset = 20 + 30 * tier
            ox, oy = normalX * offset, normalY * offset
            tickX, tickY = (dx / worldLength + normalX) * 3, (dy / worldLength + normalY) * 3
            parent = QtWidgets.QGraphicsPathItem()
            parent.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            parent.setPos(first.x(), -first.y())
            parent.setZValue(index)
            self.scene.addItem(parent)
            mainLine = QtWidgets.QGraphicsLineItem(parent)
            mainLine.setPen(pen)
            end = QtWidgets.QGraphicsPathItem(parent)
            for anchor in (parent, end):
                extension = QtWidgets.QGraphicsLineItem(normalX * 4, normalY * 4,
                    ox + normalX * 4, oy + normalY * 4, anchor)
                extension.setPen(pen)
                tick = QtWidgets.QGraphicsLineItem(ox - tickX, oy - tickY, ox + tickX, oy + tickY, anchor)
                tick.setPen(pen)
            label = QtWidgets.QGraphicsRectItem(parent)
            label.setPen(QtCore.Qt.PenStyle.NoPen)
            label.setBrush(QtGui.QColor(themeColors["canvas"]))
            angle = math.degrees(math.atan2(dy, dx))
            label.setRotation(angle - 180 if angle > 90 else angle + 180 if angle < -90 else angle)
            glyphs = QtWidgets.QGraphicsPathItem(label)
            glyphs.setPen(QtCore.Qt.PenStyle.NoPen)
            glyphs.setBrush(QtGui.QColor(themeColors["objectOutline"]))
            self.entries.append((first, second, tier, displayLength, parent, mainLine, end, label, glyphs,
                                 dx, dy, worldLength, ox, oy, -1, None))

    def Paint(self, painter, drawingRect):
        viewport = self.viewport
        scale = viewport.basePixelsPerMillimeter * viewport.zoom
        origin = viewport.WorldToViewport(QtCore.QPointF())
        unit = GridUnit(viewport.GridSteps()[0], viewport.unitsMode)[1]
        metrics = QtGui.QFontMetrics(self.font, painter.device())
        for position, entry in enumerate(self.entries):
            (first, second, tier, displayLength, parent, mainLine, end, label, glyphs,
             dx, dy, worldLength, ox, oy, previousScale, textUnit) = entry
            firstX, firstY = origin.x() + first.x() * scale, origin.y() - first.y() * scale
            secondX, secondY = firstX + dx * scale, firstY + dy * scale
            margin = max(80, 40 + 30 * tier)
            visible = (worldLength * scale >= 24 - 1e-6
                and min(firstX, secondX) - margin <= drawingRect.right()
                and max(firstX, secondX) + margin >= drawingRect.left()
                and min(firstY, secondY) - margin <= drawingRect.bottom()
                and max(firstY, secondY) + margin >= drawingRect.top())
            if parent.isVisible() != visible:
                parent.setVisible(visible)
            if not visible:
                continue
            if previousScale != scale:
                mainLine.setLine(ox, oy, dx * scale + ox, dy * scale + oy)
                end.setPos(dx * scale, dy * scale)
                label.setPos(dx * scale / 2 + ox, dy * scale / 2 + oy)
            if textUnit != unit:
                text = FormatLength(worldLength if displayLength is None else displayLength, viewport.unitsMode,
                    adaptive = unit, includeUnit = False, precision = viewport.measurementPrecision)
                if viewport.unitsMode in imperialModes:
                    path = MeasurementTextPath(text, self.font.toString(), self.dpi)
                    width = path.boundingRect().width() + 12
                    path = QtGui.QTransform.fromTranslate(-path.boundingRect().center().x(),
                        -path.boundingRect().center().y()).map(path)
                else:
                    width = metrics.horizontalAdvance(text) + 12
                    path, advance, height, ascent = TextPath(text, self.font.toString(), self.dpi, width)
                    path = QtGui.QTransform.fromTranslate(-advance / 2, -height / 2 + ascent).map(path)
                glyphs.setPath(path)
                label.setRect(-width / 2, -10, width, 20)
            self.entries[position] = entry[:-2] + (scale, unit)
        # Scene.render's source-rectangle query does not account for the full
        # device footprint of transform-ignoring children anchored offscreen.
        # Explicit visibility above handles this experimental scene instead.
        source = self.scene.sceneRect()
        target = QtCore.QRectF(source.x() * scale + origin.x(), source.y() * scale + origin.y(),
                              source.width() * scale, source.height() * scale)
        painter.save()
        self.scene.render(painter, target, source, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio)
        painter.restore()
