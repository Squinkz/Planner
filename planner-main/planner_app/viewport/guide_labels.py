"""Shared dragging and linear label layout for manual measurement annotations."""
import math
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.fonts import fontFamily
from planner_app.graphics.measurement_text import MeasurementTextPath
from planner_app.units import FormatLength, GridUnit, imperialModes


class GuideLabelsMixin:
    def MeasurementLabelLayout(self, guide, metrics = None, label = None, labelPath = None):
        font = QtGui.QFont(self.font())
        font.setFamily(fontFamily)
        if metrics is None:
            metrics = QtGui.QFontMetrics(font)
        if label is None:
            unused, unit = GridUnit(self.GridSteps()[0], self.unitsMode)
            label = FormatLength(QtCore.QLineF(guide.firstVertex, guide.secondVertex).length(), self.unitsMode,
                                 adaptive = unit, includeUnit = False, precision = self.measurementPrecision)
        if labelPath is None and self.unitsMode in imperialModes:
            labelPath = MeasurementTextPath(label, font.toString(), self.logicalDpiY())
        width = (labelPath.boundingRect().width() if labelPath is not None else metrics.horizontalAdvance(label)) + 12
        first, last = self.WorldToViewport(guide.firstVertex), self.WorldToViewport(guide.secondVertex)
        direction = last - first
        angle = math.degrees(math.atan2(direction.y(), direction.x()))
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180
        offset = self.WorldToViewport(guide.textOffset) - self.WorldToViewport(QtCore.QPointF())
        center = (first + last) / 2 + offset
        rectangle = QtCore.QRectF(-width / 2, -10, width, 20)
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
