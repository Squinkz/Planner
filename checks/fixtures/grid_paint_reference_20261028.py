"""Frozen grid painter before the October 28 pan-grid optimizations."""
import math
from PySide6 import QtCore, QtGui
from planner_app.graphics.palette import themeColors
from planner_app.measurement_units import GridUnit, FormatLength, imperialModes


def ReferenceDrawGridBackground(self, painter, drawingRect, origin, pixelsPerMillimeter, gridOnly = False, drawGrid = True,
                       allEdges = False, markingsOnly = False):
    # Choose a metric 1/2/5 interval with enough room for ruler labels.
    majorStep, minorStep = self.GridSteps()
    roomClip = QtGui.QPainterPath()
    if drawGrid and (self.floors or self.solidRooms):
        cachedRooms = self.roomDetection.path
        if not cachedRooms.isEmpty():
            transform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(pixelsPerMillimeter, -pixelsPerMillimeter)
            roomClip = transform.map(cachedRooms)
    if self.floors and not roomClip.isEmpty():
        painter.save()
        painter.setClipRect(drawingRect, QtCore.Qt.ClipOperation.IntersectClip)
        painter.fillPath(roomClip, QtGui.QColor(themeColors["roomFill"]))
        painter.restore()
    origin = origin + QtCore.QPointF(self.gridOrigin[0] * pixelsPerMillimeter, -self.gridOrigin[1] * pixelsPerMillimeter)
    gridSpacing = minorStep * pixelsPerMillimeter
    majorEvery = max(1, round(majorStep / minorStep))
    millimetersPerUnit, rulerUnit = GridUnit(majorStep, self.unitsMode)
    labelStep = majorStep / millimetersPerUnit
    decimalPlaces = max(0, -math.floor(math.log10(labelStep)))
    if self.unitsMode == "Millimeters":
        decimalPlaces = 0

    if drawGrid and not markingsOnly and self.referenceImage is not None:
        self.referenceImage.Draw(painter, drawingRect)

    if not gridOnly:
        painter.fillRect(QtCore.QRectF(0, 0, self.width(), self.rulerSize), QtGui.QColor(themeColors["rulerBackground"]))
        painter.fillRect(QtCore.QRectF(0, 0, self.rulerSize, self.height()), QtGui.QColor(themeColors["rulerBackground"]))
        if allEdges:
            painter.fillRect(QtCore.QRectF(0, self.height() - self.rulerSize, self.width(), self.rulerSize),
                             QtGui.QColor(themeColors["rulerBackground"]))
            painter.fillRect(QtCore.QRectF(self.width() - self.rulerSize, 0, self.rulerSize, self.height()),
                             QtGui.QColor(themeColors["rulerBackground"]))
    rulerFont = QtGui.QFont(self.font())
    rulerFont.setPointSizeF(8.0)
    painter.setFont(rulerFont)
    # Keep the ordinary 28-pixel label/tick band against the canvas edge;
    # additional border width extends outward beyond the ruler labels.
    labelOffset = max(0, self.rulerSize - 28)

    for axis in (0, 1):
        axisOrigin = origin.x() if axis == 0 else origin.y()
        extent = drawingRect.right() if axis == 0 else drawingRect.bottom()
        # Include strokes whose centers lie just outside the canvas.
        # Their visible fringe must exist before a cached pan scrolls it
        # inward. The widest grid pen (the origin) is 1.5 logical pixels.
        firstIndex = math.ceil(((drawingRect.left() if axis == 0 else drawingRect.top()) - axisOrigin - .75) / gridSpacing)
        lastIndex = math.floor((extent - axisOrigin + .75) / gridSpacing)
        gridLines = {"origin": [], "major": [], "minor": []}
        tickLines = {True: [], False: []}
        majorLabels = []
        for gridIndex in range(firstIndex, lastIndex + 1):
            position = axisOrigin + gridIndex * gridSpacing
            # Stabilize aliased grid strokes at fractional DPI. Equivalent
            # whole-device-pixel positions can otherwise land on opposite
            # sides of a floating-point stroke-coverage threshold.
            ratio = painter.device().devicePixelRatioF()
            position = (round(position * ratio, 6) + .000001) / ratio
            isMajor = gridIndex % majorEvery == 0
            gridKind = "origin" if gridIndex == 0 else "major" if isMajor else "minor"
            tickLength = 9 if isMajor else 4
            if axis == 0:
                gridLines[gridKind].append(QtCore.QLineF(position, drawingRect.top(), position, drawingRect.bottom()))
                tickLines[isMajor].append(QtCore.QLineF(position, self.rulerSize - tickLength, position, self.rulerSize))
            else:
                gridLines[gridKind].append(QtCore.QLineF(drawingRect.left(), position, drawingRect.right(), position))
                tickLines[isMajor].append(QtCore.QLineF(self.rulerSize - tickLength, position, self.rulerSize, position))
            if isMajor:
                if self.unitsMode in imperialModes:
                    label = FormatLength(abs(gridIndex * minorStep), self.unitsMode, decimals = 4)
                else:
                    value = abs(gridIndex * minorStep) / millimetersPerUnit
                    label = f"{value:,.{decimalPlaces}f}"
                    if decimalPlaces:
                        label = label.rstrip("0").rstrip(".")
                majorLabels.append((position, label))

        # Batch each pen/clip combination instead of resetting painter state
        # for every line. Grid pan cost then scales mainly with line drawing.
        if self.showGrid and drawGrid:
            painter.save()
            painter.setClipRect(drawingRect, QtCore.Qt.ClipOperation.IntersectClip)
            for gridKind, lines in gridLines.items():
                intensity = self.gridIntensities["overall"] * self.gridIntensities[gridKind]
                if lines and intensity > 0:
                    color = QtGui.QColor(themeColors["grid"])
                    color.setAlphaF(min(1.0, intensity))
                    width = 1.5 if gridKind == "origin" else 1.0
                    if self.solidRooms and not roomClip.isEmpty():
                        # Subtract actual stroke geometry: SVG generators do
                        # not consistently preserve nonrectangular painter clips.
                        linePath = QtGui.QPainterPath()
                        for line in lines:
                            linePath.moveTo(line.p1())
                            linePath.lineTo(line.p2())
                        stroker = QtGui.QPainterPathStroker()
                        stroker.setWidth(width)
                        stroker.setCapStyle(QtCore.Qt.PenCapStyle.SquareCap)
                        painter.fillPath(stroker.createStroke(linePath).subtracted(roomClip), color)
                    else:
                        painter.setPen(QtGui.QPen(color, width))
                        painter.drawLines(lines)
            painter.restore()

        if gridOnly:
            continue
        painter.save()
        painter.setClipRect(QtCore.QRectF(self.rulerSize, 0, self.width() - self.rulerSize, self.rulerSize) if axis == 0 else
                            QtCore.QRectF(0, self.rulerSize, self.rulerSize, self.height() - self.rulerSize))
        for isMajor, lines in tickLines.items():
            if lines:
                painter.setPen(QtGui.QColor(themeColors["rulerMajorTick"] if isMajor else themeColors["rulerMinorTick"]))
                painter.drawLines(lines)
        painter.setPen(QtGui.QColor(themeColors["rulerText"]))
        for position, label in (() if markingsOnly else majorLabels):
            if axis == 0:
                painter.drawText(QtCore.QRectF(position - 42, labelOffset, 84, 18), QtCore.Qt.AlignmentFlag.AlignCenter, label)
            else:
                painter.save()
                painter.translate(labelOffset, position)
                painter.rotate(-90)
                painter.drawText(QtCore.QRectF(-42, 0, 84, 18), QtCore.Qt.AlignmentFlag.AlignCenter, label)
                painter.restore()
        painter.restore()

        if allEdges:
            painter.save()
            edge = self.height() - self.rulerSize if axis == 0 else self.width() - self.rulerSize
            painter.setClipRect(QtCore.QRectF(self.rulerSize, edge, drawingRect.width(), self.rulerSize) if axis == 0 else
                                QtCore.QRectF(edge, self.rulerSize, self.rulerSize, drawingRect.height()))
            for isMajor, lines in tickLines.items():
                if lines:
                    painter.setPen(QtGui.QColor(themeColors["rulerMajorTick"] if isMajor else themeColors["rulerMinorTick"]))
                    if axis == 0:
                        oppositeLines = [QtCore.QLineF(line.x1(), self.height() - line.y1(), line.x2(), self.height() - line.y2())
                                         for line in lines]
                    else:
                        oppositeLines = [QtCore.QLineF(self.width() - line.x1(), line.y1(), self.width() - line.x2(), line.y2())
                                         for line in lines]
                    painter.drawLines(oppositeLines)
            painter.setPen(QtGui.QColor(themeColors["rulerText"]))
            for position, label in (() if markingsOnly else majorLabels):
                if axis == 0:
                    painter.drawText(QtCore.QRectF(position - 42, self.height() - 18 - labelOffset, 84, 18),
                                     QtCore.Qt.AlignmentFlag.AlignCenter, label)
                else:
                    painter.save()
                    painter.translate(self.width() - 18 - labelOffset, position)
                    painter.rotate(-90)
                    painter.drawText(QtCore.QRectF(-42, 0, 84, 18), QtCore.Qt.AlignmentFlag.AlignCenter, label)
                    painter.restore()
            painter.restore()

    return rulerUnit
