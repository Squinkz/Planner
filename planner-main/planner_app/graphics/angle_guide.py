"""Shared screen-space layout for angle rendering, picking and label dragging."""
import math
from PySide6 import QtCore, QtGui


def AngleGuideLayout(first, middle, last, metrics, textOffset = None, drawArms = False, referenceEdges = ()):
    path = QtGui.QPainterPath()
    if drawArms:
        path.moveTo(first)
        path.lineTo(middle)
        path.lineTo(last)
    firstArm, lastArm = first - middle, last - middle
    firstLength, lastLength = math.hypot(firstArm.x(), firstArm.y()), math.hypot(lastArm.x(), lastArm.y())
    if min(firstLength, lastLength) < 1e-8:
        return path, QtCore.QRectF(), "", None
    start = math.atan2(firstArm.y(), firstArm.x())
    sweep = math.atan2(firstArm.x() * lastArm.y() - firstArm.y() * lastArm.x(),
                       QtCore.QPointF.dotProduct(firstArm, lastArm))
    radius = max(0, min(firstLength, lastLength) - 8)
    # Allow floating-point noise from rotations, but never use the rounded label
    # to decide whether the geometry is a right angle.
    rightAngle = math.isclose(abs(sweep), math.pi / 2, rel_tol = 0, abs_tol = 1e-10)
    if rightAngle:
        radius = min(12, radius)
        firstSide = firstArm / firstLength * radius
        lastSide = lastArm / lastLength * radius
        path.moveTo(middle + firstSide)
        path.lineTo(middle + firstSide + lastSide)
        path.lineTo(middle + lastSide)
    else:
        arc = QtGui.QPainterPath()
        arc.arcMoveTo(QtCore.QRectF(middle.x() - radius, middle.y() - radius, radius * 2, radius * 2), -math.degrees(start))
        arc.arcTo(QtCore.QRectF(middle.x() - radius, middle.y() - radius, radius * 2, radius * 2),
                  -math.degrees(start), -math.degrees(sweep))
        path.addPath(arc)
    if not drawArms and radius > 0:
        for arm, length in ((firstArm, firstLength), (lastArm, lastLength)):
            direction = arm / length
            endpoint = middle + direction * radius
            referenced = False
            for edgeFirst, edgeLast in referenceEdges:
                edge = edgeLast - edgeFirst
                edgeLength = math.hypot(edge.x(), edge.y())
                if edgeLength < 1e-8:
                    continue
                # Only nearby edges following this arm explain its direction.
                # A perpendicular edge crossing the arc must not hide the marker.
                if abs(edge.x() * direction.y() - edge.y() * direction.x()) / edgeLength > math.sin(math.radians(10)):
                    continue
                fraction = max(0, min(1, QtCore.QPointF.dotProduct(endpoint - edgeFirst, edge) / edgeLength ** 2))
                if QtCore.QLineF(endpoint, edgeFirst + edge * fraction).length() <= 5:
                    referenced = True
                    break
            if not referenced:
                path.moveTo(middle + direction * max(0, radius - 6))
                path.lineTo(middle + direction * (radius + 10))
    label = f"{abs(math.degrees(sweep)):.1f}".rstrip("0").rstrip(".") + "°"
    labelWidth, labelHeight = metrics.horizontalAdvance(label) + 10, metrics.height() + 4
    direction = QtCore.QPointF(math.cos(start + sweep / 2), math.sin(start + sweep / 2))
    arcMiddle = middle + direction * radius
    if rightAngle:
        arcMiddle = middle + firstSide + lastSide
    outside = rightAngle or radius * abs(sweep) < labelWidth + 24
    labelCenter = arcMiddle + direction * (labelHeight + 8 if outside else 0)
    if textOffset is not None:
        labelCenter += textOffset
    labelRect = QtCore.QRectF(labelCenter.x() - labelWidth / 2, labelCenter.y() - labelHeight / 2, labelWidth, labelHeight)
    if outside or textOffset is not None and math.hypot(textOffset.x(), textOffset.y()) > .01:
        path.moveTo(arcMiddle)
        path.lineTo(labelCenter)
    if not rightAngle and radius > 5 and abs(sweep) * radius > 12:
        for angle, sign in ((start, 1), (start + sweep, -1)):
            endpoint = middle + QtCore.QPointF(math.cos(angle), math.sin(angle)) * radius
            tangent = QtCore.QPointF(-math.sin(angle), math.cos(angle)) * (sign * math.copysign(1, sweep))
            normal = QtCore.QPointF(-tangent.y(), tangent.x())
            path.moveTo(endpoint + tangent * 6 + normal * 2.5)
            path.lineTo(endpoint)
            path.lineTo(endpoint + tangent * 6 - normal * 2.5)
    return path, labelRect, label, arcMiddle
