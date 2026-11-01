"""Shared dragging and linear label layout for manual measurement annotations."""
import math
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.measurement_text import MeasurementTextPath, MeasurementFontStyle
from planner_app.graphics.fonts import fontFamily
from planner_app.units import FormatLength, GridUnit, imperialModes


class GuideLabelsMixin:
    def MeasurementFont(self, font = None, device = None, textSize = None):
        exporting = getattr(self, "exportRender", False) or self.exportOverlay.active
        if exporting:
            # Opening symbols can leave a smaller font on the painter. Keep
            # export dimensions and their spacing independent of prior artwork.
            font = self.font()
        fontKey, labelScale = MeasurementFontStyle((self.font() if font is None else font).toString(),
            (self if device is None else device).logicalDpiY(), (self.measurementTextSize if textSize is None else textSize) * self.measurementPixelsPerMillimeter,
            "D-DIN Condensed" if exporting else fontFamily)
        if exporting:
            # Grow the empty spacing at half the font's rate, keeping larger
            # labels and stacked rows compact without reducing their ink height.
            labelScale = 1 + max(0, labelScale - 1) * .5
        font = QtGui.QFont()
        font.fromString(fontKey)
        return font, labelScale

    def MeasurementLabelLayout(self, guide, metrics = None, label = None, labelPath = None):
        font, labelScale = self.MeasurementFont()
        if metrics is None:
            metrics = QtGui.QFontMetrics(font)
        if label is None:
            unused, unit = GridUnit(self.GridSteps()[0], self.unitsMode)
            label = FormatLength(QtCore.QLineF(guide.firstVertex, guide.secondVertex).length(), self.unitsMode,
                                 adaptive = unit, includeUnit = False, precision = self.measurementPrecision)
        if labelPath is None and self.unitsMode in imperialModes:
            labelPath = MeasurementTextPath(label, font.toString(), self.logicalDpiY())
        width = (labelPath.boundingRect().width() if labelPath is not None else metrics.horizontalAdvance(label)) + 12 * labelScale
        first, last = self.WorldToViewport(guide.firstVertex), self.WorldToViewport(guide.secondVertex)
        direction = last - first
        angle = math.degrees(math.atan2(direction.y(), direction.x()))
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180
        offset = self.WorldToViewport(guide.textOffset) - self.WorldToViewport(QtCore.QPointF())
        center = (first + last) / 2 + offset
        rectangle = QtCore.QRectF(-width / 2, -10 * labelScale, width, 20 * labelScale)
        transform = QtGui.QTransform().translate(center.x(), center.y()).rotate(angle)
        hitPath = QtGui.QPainterPath()
        hitPath.addRect(rectangle)
        return center, angle, rectangle, transform.map(hitPath)

    def UpdateGuideTextDrag(self, position):
        if (position - self.dragStart).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
            self.isDragging = True
        if self.isDragging:
            self.selectedWall.textOffset = self.guideTextDrag + self.ViewportToWorld(position) - self.ViewportToWorld(self.dragStart)
            self.alignmentGuides = []
            self.update()
