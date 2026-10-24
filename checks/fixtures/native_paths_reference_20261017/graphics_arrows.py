"""Arrow paths and terminal directions for connected, directed arrow runs."""
import math
from PySide6 import QtCore, QtGui


def ArrowPaths(first, second, thickness, solidTip, tipSize, scale, showTip = True, corners = ()):
    tail = QtGui.QPainterPath()
    head = QtGui.QPainterPath()
    run = second - first
    length = math.hypot(run.x(), run.y())
    if length < 1e-8:
        return tail, head
    direction = run / length
    normal = QtCore.QPointF(-direction.y(), direction.x())
    tail.moveTo(first)
    tail.lineTo(second)
    stroker = QtGui.QPainterPathStroker()
    stroker.setWidth(thickness * scale)
    stroker.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)
    stroker.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
    tail = stroker.createStroke(tail)
    if showTip:
        # Both styles share the same outer triangle. The open head is cut out
        # inside that triangle, so thick strokes cannot project past its tip.
        headWidth = tipSize * scale
        headLength = headWidth * 12 / 7
        base = second - direction * headLength
        head.moveTo(base - normal * (headWidth / 2))
        head.lineTo(second)
        head.lineTo(base + normal * (headWidth / 2))
        if solidTip:
            head.closeSubpath()
            tail = QtGui.QPainterPath()
            tail.moveTo(first)
            tail.lineTo(second - direction * min(length, headLength))
            tail = stroker.createStroke(tail)
        else:
            halfWidth = headWidth / 2
            strokeWidth = min(thickness * scale, headWidth * .2)
            innerHalfWidth = max(0, halfWidth - strokeWidth * math.hypot(headLength, halfWidth) / headLength)
            innerTip = base + direction * (headLength * innerHalfWidth / halfWidth)
            # Trace the two bands directly. Subtracting an inner triangle with
            # a coincident base can produce spurious faces at certain angles.
            head.lineTo(base + normal * innerHalfWidth)
            head.lineTo(innerTip)
            head.lineTo(base - normal * innerHalfWidth)
            head.closeSubpath()
            # End the shaft inside the V, where the two bands meet. Extending
            # a flat, thick shaft to the tip would protrude past its sloping sides.
            tipDepth = max(headLength * (1 - innerHalfWidth / halfWidth),
                           headLength * min(1, thickness / tipSize))
            tail = QtGui.QPainterPath()
            tail.moveTo(first)
            tail.lineTo(second - direction * min(length, tipDepth))
            tail = stroker.createStroke(tail)
    tail.setFillRule(QtCore.Qt.FillRule.WindingFill)
    for vertices in corners:
        polygon = list(vertices)
        area = sum(point.x() * polygon[(index + 1) % len(polygon)].y() -
                   polygon[(index + 1) % len(polygon)].x() * point.y() for index, point in enumerate(polygon))
        if area < 0:
            polygon.reverse()
        tail.addPolygon(QtGui.QPolygonF(polygon))
        tail.closeSubpath()
    return tail, head


def ConnectedArrowCorners(arrows, directions):
    """Miter the exposed corners between adjoining shafts without changing direction."""
    endpoints = {}
    corners = {id(arrow): [] for arrow in arrows}
    for arrow in arrows:
        run = arrow.secondVertex - arrow.firstVertex
        length = math.hypot(run.x(), run.y())
        if length < 1e-8:
            continue
        for index, vertex in enumerate((arrow.firstVertex, arrow.secondVertex)):
            # A terminal head retains its own shape, rather than becoming a tail join.
            if index == 1 and directions[id(arrow)][2]:
                continue
            direction = run / length if index == 0 else -run / length
            bucket = (math.floor(vertex.x() / .01), math.floor(vertex.y() / .01))
            for x in range(bucket[0] - 1, bucket[0] + 2):
                for y in range(bucket[1] - 1, bucket[1] + 2):
                    for other, otherVertex, otherDirection in endpoints.get((x, y), ()):
                        if other is arrow or QtCore.QLineF(vertex, otherVertex).length() > .01:
                            continue
                        cross = direction.x() * otherDirection.y() - direction.y() * otherDirection.x()
                        if abs(cross) < 1e-8:
                            continue
                        side = -1 if cross > 0 else 1
                        junction = (vertex + otherVertex) / 2
                        firstOffset = QtCore.QPointF(-direction.y(), direction.x()) * (arrow.width / 2 * side)
                        secondOffset = QtCore.QPointF(-otherDirection.y(), otherDirection.x()) * (-other.width / 2 * side)
                        delta = secondOffset - firstOffset
                        distance = (delta.x() * otherDirection.y() - delta.y() * otherDirection.x()) / cross
                        miter = firstOffset + direction * distance
                        # Acute turns use a bevel instead of an unbounded spike.
                        if math.hypot(miter.x(), miter.y()) > max(arrow.width, other.width) * 4:
                            miter = (firstOffset + secondOffset) / 2
                        corners[id(arrow)].append((junction, junction + firstOffset, junction + miter))
                        corners[id(other)].append((junction, junction + miter, junction + secondOffset))
            endpoints.setdefault(bucket, []).append((arrow, vertex, direction))
    return corners


def ConnectedArrowDirections(arrows):
    # Direction belongs to each arrow, not its position in the scene list.
    # Hide a tip only when a different arrow's tail continues from that tip.
    tails = {}
    for arrow in arrows:
        vertex = arrow.firstVertex
        bucket = (math.floor(vertex.x() / .01), math.floor(vertex.y() / .01))
        tails.setdefault(bucket, []).append(arrow)
    result = {}
    for arrow in arrows:
        tip = arrow.secondVertex
        bucket = (math.floor(tip.x() / .01), math.floor(tip.y() / .01))
        continues = any(other is not arrow and QtCore.QLineF(tip, other.firstVertex).length() <= .01
                        for x in range(bucket[0] - 1, bucket[0] + 2)
                        for y in range(bucket[1] - 1, bucket[1] + 2)
                        for other in tails.get((x, y), ()))
        result[id(arrow)] = (arrow.firstVertex, arrow.secondVertex, not continues)
    return result
