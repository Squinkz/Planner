"""Numeric opening projection and free-space clipping, independent of UI snapping."""
import math
from .polygons import SplitPolygon


def ProjectOpening(first, second, position):
    directionX, directionY = second[0] - first[0], second[1] - first[1]
    lengthSquared = directionX * directionX + directionY * directionY
    if lengthSquared < 1.0:
        return None
    offsetX, offsetY = position[0] - first[0], position[1] - first[1]
    fraction = max(0.0, min(1.0, (offsetX * directionX + offsetY * directionY) / lengthSquared))
    projected = (first[0] + directionX * fraction, first[1] + directionY * fraction)
    return (directionX, directionY), lengthSquared, fraction, projected


def OpeningGap(fraction, intervals, gapStart = 0.0, gapEnd = 1.0):
    for start, end in intervals:
        if end <= fraction + 1e-8:
            gapStart = max(gapStart, end)
        elif start >= fraction - 1e-8:
            gapEnd = min(gapEnd, start)
        else:
            gapEnd = gapStart
            break
    return gapStart, gapEnd


def BlockedOpeningIntervals(parentCorners, first, direction, lengthSquared, polygons):
    area = sum(parentCorners[index][0] * parentCorners[(index + 1) % 4][1]
               - parentCorners[(index + 1) % 4][0] * parentCorners[index][1] for index in range(4))
    orientation = 1 if area > 0 else -1
    blocked = []
    for polygon in polygons:
        points = polygon
        for index, edgeFirst in enumerate(parentCorners):
            points, outside = SplitPolygon(points, edgeFirst, parentCorners[(index + 1) % 4], orientation)
            if len(points) < 3:
                break
        if len(points) < 3:
            continue
        overlapArea = abs(sum(points[index][0] * points[(index + 1) % len(points)][1]
                              - points[(index + 1) % len(points)][0] * points[index][1]
                              for index in range(len(points))))
        if overlapArea < 1e-6:
            continue
        bounds = [((point[0] - first[0]) * direction[0] + (point[1] - first[1]) * direction[1]) / lengthSquared
                  for point in points]
        blocked.append((max(0.0, min(bounds)), min(1.0, max(bounds))))
    return blocked


def OpeningPlacementSpan(length, parentLength, fraction, gapStart, gapEnd):
    span = min(length / parentLength, gapEnd - gapStart)
    minimumCenter, maximumCenter = gapStart + span / 2, gapEnd - span / 2
    center = max(minimumCenter, min(maximumCenter, fraction))
    return span, minimumCenter, maximumCenter, center


def OpeningVertexFraction(first, second, position, vertexIndex, oppositeFraction):
    directionX, directionY = second[0] - first[0], second[1] - first[1]
    lengthSquared = directionX * directionX + directionY * directionY
    if lengthSquared < 1e-10:
        return None
    fraction = ((position[0] - first[0]) * directionX + (position[1] - first[1]) * directionY) / lengthSquared
    minimumSpan = min(1.0, 1.0 / math.sqrt(lengthSquared))
    if vertexIndex == 0:
        return max(0.0, min(oppositeFraction - minimumSpan, fraction))
    return min(1.0, max(oppositeFraction + minimumSpan, fraction))


def CenteredOpeningSpan(first, second, position, vertexIndex, center, gapStart, gapEnd):
    """Resize around a fixed center, stopping both ends at the nearest limit."""
    projection = ProjectOpening(first, second, position)
    if projection is None:
        return None
    direction, lengthSquared, fraction, projected = projection
    minimumHalf = .5 / math.sqrt(lengthSquared)
    maximumHalf = min(center - gapStart, gapEnd - center)
    if maximumHalf < minimumHalf:
        return None
    halfSpan = center - fraction if vertexIndex == 0 else fraction - center
    halfSpan = max(minimumHalf, min(maximumHalf, halfSpan))
    return center - halfSpan, center + halfSpan


def FireplaceCenter(first, direction, normal, wallLength, width, position):
    halfSpan = width / (2 * max(wallLength, 1e-8))
    offsetX, offsetY = position[0] - first[0], position[1] - first[1]
    fraction = max(halfSpan, min(1 - halfSpan,
        (offsetX * direction[0] + offsetY * direction[1]) / max(wallLength, 1e-8)))
    return fraction, offsetX * normal[0] + offsetY * normal[1]
