"""Vector symbols for doors, windows and stair treads."""

import math
from PySide6 import QtCore, QtGui
from planner_app.graphics.palette import themeColors
from .linework import LinePen, defaultLineWidths
from planner_app.models import OpenDoorway, Door, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, SlidingDoor, Window, Label


def DrawStairSymbol(painter, firstPoint, secondPoint, width, stepCount = 4,
                    directionReversed = False, color = None, outline = True, firstTrim = 0, secondTrim = 0, clipRect = None, lineWidth = None):
    lineWidth = defaultLineWidths["architectural"] if lineWidth is None else lineWidth
    color = themeColors["objectOutline"] if color is None else color
    direction = secondPoint - firstPoint
    length = math.hypot(direction.x(), direction.y())
    if length < 1e-10:
        return
    normal = QtCore.QPointF(-direction.y(), direction.x()) * (width / (2 * length))
    painter.setPen(LinePen(color, lineWidth))
    if outline:
        painter.setBrush(QtGui.QColor(themeColors["canvas"]))
        painter.drawPolygon(QtGui.QPolygonF([firstPoint + normal, secondPoint + normal,
                                            secondPoint - normal, firstPoint - normal]))
    # The spaces, rather than the dividing lines, represent the steps.
    if firstTrim + secondTrim >= length - 1e-8:
        return
    runLength = length - firstTrim - secondTrim
    spacing = runLength / max(1, stepCount)
    firstStep, lastStep = 1, stepCount - 1
    if clipRect is not None:
        bounds = clipRect.adjusted(-width / 2 - 2, -width / 2 - 2, width / 2 + 2, width / 2 + 2)
        distances = [QtCore.QPointF.dotProduct(point - firstPoint, direction) / length
                     for point in (bounds.topLeft(), bounds.topRight(), bounds.bottomLeft(), bounds.bottomRight())]
        firstStep = max(firstStep, math.floor((min(distances) - firstTrim) / spacing))
        lastStep = min(lastStep, math.ceil((max(distances) - firstTrim) / spacing))
    # Subpixel treads are visually indistinguishable. Keep work proportional to
    # visible pixels, without changing the model's step count.
    stride = max(1, math.ceil(2 / spacing), math.ceil(max(0, lastStep - firstStep + 1) / 8192))
    firstStep = max(1, firstStep + (-firstStep % stride))
    for step in range(firstStep, lastStep + 1, stride):
        distance = firstTrim + (length - firstTrim - secondTrim) * step / stepCount
        center = firstPoint + direction * (distance / length)
        painter.drawLine(QtCore.QLineF(center - normal, center + normal))
    for distance in ((firstTrim,) if firstTrim > 0 else ()) + ((length - secondTrim,) if secondTrim > 0 else ()):
        center = firstPoint + direction * (distance / length)
        painter.drawLine(QtCore.QLineF(center - normal, center + normal))
    runStart = firstPoint + direction * (firstTrim / length)
    runDirection = direction * ((length - firstTrim - secondTrim) / length)
    start = runStart + runDirection if directionReversed else runStart
    tip = runStart if directionReversed else runStart + runDirection
    arrowDirection = direction / length * (-1 if directionReversed else 1)
    arrowNormal = QtCore.QPointF(-arrowDirection.y(), arrowDirection.x())
    # A dark underlay keeps the arrow distinct where it crosses a tread line.
    painter.setPen(LinePen(themeColors["canvas"], lineWidth + 3 if lineWidth > 0 else 0))
    painter.drawLine(QtCore.QLineF(start, tip))
    painter.setPen(LinePen(color, lineWidth))
    painter.drawLine(QtCore.QLineF(start, tip))
    headLength, headWidth = 12, 7
    for side in (-1, 1):
        painter.drawLine(QtCore.QLineF(tip, tip - arrowDirection * headLength
                                      + arrowNormal * (side * headWidth)))


def DrawOpeningSymbol(painter, firstPoint, secondPoint, width, openingType = Window,
                      hingeAtSecond = False, swingsOutwards = False, color = None, panelsFlipped = False,
                      pixelsPerMillimeter = .2, sillDepth = 40.0, lineWidth = None, wallLineWidth = None, wallColor = None):
    lineWidth = defaultLineWidths["architectural"] if lineWidth is None else lineWidth
    wallLineWidth = defaultLineWidths["walls"] if wallLineWidth is None else wallLineWidth
    wallColor = themeColors["wallOutline"] if wallColor is None else wallColor
    color = themeColors["invalidOutline"] if color is None else color
    direction = secondPoint - firstPoint
    length = math.hypot(direction.x(), direction.y())
    if length < 1e-10:
        return
    normal = QtCore.QPointF(-direction.y(), direction.x()) * (width / (2 * length))
    painter.setPen(LinePen(color, lineWidth))
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    if openingType is BarnDoor:
        midpoint = (firstPoint + secondPoint) / 2
        parkingEnd = firstPoint if hingeAtSecond else secondPoint
        openingEnd = secondPoint if hingeAtSecond else firstPoint
        facingNormal = normal * (1 if swingsOutwards else -1)
        halfThickness = facingNormal / (width / 2) * (15 * pixelsPerMillimeter)
        panelStart = midpoint + (openingEnd - midpoint) * .75
        panelEnd = panelStart + parkingEnd - midpoint
        offset = facingNormal + halfThickness
        painter.setBrush(QtGui.QColor(themeColors["canvas"]))
        painter.drawPolygon(QtGui.QPolygonF([panelStart + offset + halfThickness, panelEnd + offset + halfThickness,
                                            panelEnd + offset - halfThickness, panelStart + offset - halfThickness]))
        painter.setPen(LinePen(wallColor, wallLineWidth))
        painter.drawLine(QtCore.QLineF(openingEnd - normal, openingEnd + normal))
        painter.drawLine(QtCore.QLineF(midpoint - normal, midpoint + normal))
        return
    if openingType is PocketDoor:
        midpoint = (firstPoint + secondPoint) / 2
        pocketEnd = firstPoint if hingeAtSecond else secondPoint
        openingEnd = secondPoint if hingeAtSecond else firstPoint
        lip = direction / length * (20 * pixelsPerMillimeter) * (1 if hingeAtSecond else -1)
        panelStart = midpoint + lip
        panelNormal = normal * .4
        painter.setBrush(QtGui.QColor(themeColors["canvas"]))
        painter.drawPolygon(QtGui.QPolygonF([panelStart + panelNormal, pocketEnd + panelNormal,
                                            pocketEnd - panelNormal, panelStart - panelNormal]))
        painter.setPen(LinePen(wallColor, wallLineWidth))
        painter.drawLine(QtCore.QLineF(openingEnd - normal, openingEnd + normal))
        # Outline the exposed wall shoulders on either side of the pocket panel.
        painter.setPen(LinePen(wallColor, wallLineWidth))
        for side in (-1, 1):
            painter.drawLine(QtCore.QLineF(midpoint + panelNormal * side, midpoint + normal * side))
        return
    if openingType not in (BifoldDoor, SlidingDoor, Window, SilledWindow, CasementWindow):
        painter.setPen(LinePen(wallColor, wallLineWidth))
        painter.drawLine(QtCore.QLineF(firstPoint - normal, firstPoint + normal))
        painter.drawLine(QtCore.QLineF(secondPoint - normal, secondPoint + normal))
    painter.setPen(LinePen(color, lineWidth))
    if openingType is BifoldDoor:
        facingNormal = normal * (1 if swingsOutwards else -1)
        facingUnit = facingNormal / (width / 2)
        projection = length / (4 * math.sqrt(2))
        panelThickness = 30 * pixelsPerMillimeter
        for endpoint, inward in ((firstPoint, direction / length), (secondPoint, -direction / length)):
            hinge = endpoint + facingNormal
            fold = hinge + inward * projection + facingUnit * projection
            tip = fold + inward * projection - facingUnit * projection
            # The fold is the shared inner corner; each leaf extends outwards
            # from its inner edge so the two rectangles only touch at that corner.
            for start, end, offset in ((hinge, fold, (facingUnit - inward) * (panelThickness / math.sqrt(2))),
                                       (fold, tip, (facingUnit + inward) * (panelThickness / math.sqrt(2)))):
                painter.setBrush(QtGui.QColor(themeColors["canvas"]))
                painter.drawPolygon(QtGui.QPolygonF([start, end, end + offset, start + offset]))
        painter.setPen(LinePen(wallColor, wallLineWidth))
        painter.drawLine(QtCore.QLineF(firstPoint - normal, firstPoint + normal))
        painter.drawLine(QtCore.QLineF(secondPoint - normal, secondPoint + normal))
        return
    if openingType is OpenDoorway:
        # Keep the wall faces visible without filling the opening over the grid.
        painter.drawLine(QtCore.QLineF(firstPoint - normal, secondPoint - normal))
        painter.drawLine(QtCore.QLineF(firstPoint + normal, secondPoint + normal))
        return
    if openingType is SlidingDoor:
        midpoint = (firstPoint + secondPoint) / 2
        panelNormal = normal * (-.84 if hingeAtSecond != panelsFlipped else .84)
        overlap = direction * .05
        painter.setBrush(QtGui.QColor(themeColors["canvas"]))
        for start, end, offset in ((firstPoint, midpoint + overlap, panelNormal), (midpoint - overlap, secondPoint, -panelNormal)):
            painter.drawPolygon(QtGui.QPolygonF([start, end, end + offset, start + offset]))
        # Wall ends sit above panel fills, retaining their complete thickness.
        painter.setPen(LinePen(wallColor, wallLineWidth))
        painter.drawLine(QtCore.QLineF(firstPoint - normal, firstPoint + normal))
        painter.drawLine(QtCore.QLineF(secondPoint - normal, secondPoint + normal))
        arrowDirection = direction / length * (1 if hingeAtSecond else -1)
        arrowOffset = panelNormal if hingeAtSecond else -panelNormal
        panelEdge = midpoint + (overlap if hingeAtSecond else -overlap) + arrowOffset
        travelTip = (secondPoint if hingeAtSecond else firstPoint) + arrowOffset - arrowDirection * min(4, length * .01)
        # Extend the moving panel's outer edge as a dashed travel line.
        dashedPen = LinePen(color, lineWidth, QtCore.Qt.PenStyle.DashLine)
        if lineWidth > 0:
            dashedPen.setDashPattern([8, 5])
        painter.setPen(dashedPen)
        painter.drawLine(QtCore.QLineF(panelEdge, travelTip))
        painter.setPen(LinePen(color, lineWidth, QtCore.Qt.PenStyle.SolidLine,
                                QtCore.Qt.PenCapStyle.RoundCap, QtCore.Qt.PenJoinStyle.RoundJoin))
        arrowNormal = QtCore.QPointF(-arrowDirection.y(), arrowDirection.x())
        # The arrow sits beyond the moving panel, separate from its travel line.
        frontOffset = arrowOffset / math.hypot(arrowOffset.x(), arrowOffset.y()) * (width / 2 + 12)
        arrowStart = midpoint + (overlap if hingeAtSecond else -overlap) + frontOffset
        arrowTip = (secondPoint if hingeAtSecond else firstPoint) + frontOffset - arrowDirection * min(4, length * .01)
        painter.drawLine(QtCore.QLineF(arrowStart, arrowTip))
        headLength = min(12, QtCore.QLineF(arrowStart, arrowTip).length() * .25)
        headWidth = headLength * 7 / 12
        for side in (-1, 1):
            painter.drawLine(QtCore.QLineF(arrowTip, arrowTip - arrowDirection * headLength + arrowNormal * (side * headWidth)))
    elif openingType is Door:
        swingNormal = QtCore.QPointF(direction.y(), -direction.x()) / length
        if swingsOutwards:
            swingNormal = -swingNormal
        hinge = (secondPoint if hingeAtSecond else firstPoint) + swingNormal * (width / 2)
        closedDirection = direction / length * (-1 if hingeAtSecond else 1)
        startAngle = -math.degrees(math.atan2(closedDirection.y(), closedDirection.x()))
        sweep = -math.degrees(math.atan2(closedDirection.x() * swingNormal.y() - closedDirection.y() * swingNormal.x(),
                                        QtCore.QPointF.dotProduct(closedDirection, swingNormal)))
        arc = QtGui.QPainterPath(hinge + closedDirection * length)
        arc.arcTo(QtCore.QRectF(hinge.x() - length, hinge.y() - length, 2 * length, 2 * length), startAngle, sweep)
        painter.drawPath(arc)
        painter.drawLine(QtCore.QLineF(hinge, hinge + swingNormal * length))
    else:
        # Window perimeter belongs to the opening, including both wall faces.
        for side in (-1, 1):
            painter.drawLine(QtCore.QLineF(firstPoint + normal * side, secondPoint + normal * side))
        facingNormal = normal * (-1 if swingsOutwards else 1)
        crossbarOffset = facingNormal * .35
        crossbarSpacing = facingNormal / (width / 2) * min(width / 8, 10 * pixelsPerMillimeter)
        for side in (-2, 1):
            offset = crossbarOffset + crossbarSpacing * side
            painter.drawLine(QtCore.QLineF(firstPoint + offset, secondPoint + offset))
        if openingType is CasementWindow:
            hinge = (secondPoint if hingeAtSecond else firstPoint) + facingNormal
            closedDirection = direction / length * (-1 if hingeAtSecond else 1)
            facingUnit = facingNormal / (width / 2)
            tip = hinge + closedDirection * (length * math.cos(math.pi / 6)) + facingUnit * (length * .5)
            startAngle = -math.degrees(math.atan2(closedDirection.y(), closedDirection.x()))
            sweep = -30 if closedDirection.x() * facingUnit.y() - closedDirection.y() * facingUnit.x() > 0 else 30
            arc = QtGui.QPainterPath(hinge + closedDirection * length)
            arc.arcTo(QtCore.QRectF(hinge.x() - length, hinge.y() - length, 2 * length, 2 * length), startAngle, sweep)
            painter.drawPath(arc)
            painter.drawLine(QtCore.QLineF(hinge, tip))
        if openingType is SilledWindow:
            sillNormal = facingNormal
            lip = sillNormal / (width / 2) * (sillDepth * pixelsPerMillimeter)
            firstSillPoint = firstPoint + sillNormal
            secondSillPoint = secondPoint + sillNormal
            # Cover the wall outline beneath the sill without outlining its base.
            inset = sillNormal / (width / 2) * (defaultLineWidths["walls"] if wallLineWidth is None else wallLineWidth)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QColor(themeColors["canvas"]))
            painter.drawPolygon(QtGui.QPolygonF([firstSillPoint - inset, secondSillPoint - inset,
                                                secondSillPoint + lip, firstSillPoint + lip]))
            painter.setPen(LinePen(color, lineWidth))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPolyline(QtGui.QPolygonF([firstSillPoint, firstSillPoint + lip,
                                                 secondSillPoint + lip, secondSillPoint]))
        # Wall crossbars cover the frame, glazing and swing strokes at each
        # end of the window, retaining a continuous wall-colored junction.
        painter.setPen(LinePen(wallColor, wallLineWidth))
        painter.drawLine(QtCore.QLineF(firstPoint - normal, firstPoint + normal))
        painter.drawLine(QtCore.QLineF(secondPoint - normal, secondPoint + normal))
