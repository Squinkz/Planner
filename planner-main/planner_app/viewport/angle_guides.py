"""Free three-point angular annotations, sharing measurement painting and history."""
from PySide6 import QtCore, QtGui
from planner_app.graphics.angle_guide import AngleGuideLayout
from planner_app.graphics.fonts import fontFamily
from planner_app.graphics.linework import LinePen
from planner_app.graphics.palette import themeColors
from planner_app.models import Arrow, Label, MeasurementGuide, NorthArrow, Wall


class AngleGuidesMixin:
    def AngleLayout(self, guide, metrics = None, selected = None):
        if metrics is None:
            font = QtGui.QFont(self.font())
            font.setFamily(fontFamily)
            metrics = QtGui.QFontMetrics(font)
        middle = self.WorldToViewport(guide.middleVertex)
        offset = self.WorldToViewport(guide.middleVertex + guide.textOffset) - middle
        if selected is None:
            selected = any(obj is guide for obj, index in self.SelectionEntries())
        referenceEdges = []
        if not selected:
            for obj in self.walls + self.windows + self.furnishings:
                if isinstance(obj, (Arrow, Label, MeasurementGuide, NorthArrow)) or not self.IsObjectVisible(obj):
                    continue
                corners = [self.WorldToViewport(point) for point in self.ObjectCorners(obj)]
                if len(corners) >= 2:
                    referenceEdges.extend(zip(corners, corners[1:] + corners[:1]))
                if isinstance(obj, Wall):
                    referenceEdges.append((self.WorldToViewport(obj.firstVertex), self.WorldToViewport(obj.secondVertex)))
        return AngleGuideLayout(self.WorldToViewport(guide.firstVertex), middle,
                                self.WorldToViewport(guide.secondVertex), metrics, offset,
                                drawArms = selected, referenceEdges = referenceEdges)

    def AngleHoverColor(self):
        outline, canvas = QtGui.QColor(themeColors["objectOutline"]), QtGui.QColor(themeColors["canvas"])
        return QtGui.QColor.fromRgbF(outline.redF() * .55 + canvas.redF() * .45,
                                    outline.greenF() * .55 + canvas.greenF() * .45,
                                    outline.blueF() * .55 + canvas.blueF() * .45)

    def DrawAngleGuide(self, painter, guide, selected, hovered = False):
        path, labelRect, label, arcMiddle = self.AngleLayout(guide, painter.fontMetrics(), selected = selected or hovered)
        color = self.SelectionColor(guide) if selected else self.AngleHoverColor() if hovered else themeColors["measurementLine"]
        painter.save()
        painter.setPen(LinePen(color, self.lineWidths["dimensions"]))
        painter.drawPath(path)
        if label:
            painter.fillRect(labelRect, QtGui.QColor(themeColors["canvas"]))
            painter.setPen(QtGui.QColor(color if selected or hovered else themeColors["objectOutline"]))
            painter.drawText(labelRect, QtCore.Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

