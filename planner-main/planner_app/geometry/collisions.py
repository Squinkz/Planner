"""Collision policy and numeric predicates; native path intersection is a backend."""
import math

# Callers classify their model types once. These flags carry no model references.
northFlag = 1
openingFlag = 2
furnishingFlag = 4
structuralFlag = 8
annotationFlag = 16
railingFlag = 32
wallFlag = 64
elevatorFlag = 128


def AllowsCollision(first, second, settings):
    combined = first | second
    if combined & northFlag:
        return False
    if combined & openingFlag:
        return True
    if combined & furnishingFlag and not settings["furnishings"]:
        return False
    if combined & structuralFlag:
        return settings["walls"]
    return settings["architectural"]


def ExcludesFootprintCollision(first, second):
    if (first | second) & annotationFlag:
        return True
    return bool((first & railingFlag and second & (wallFlag | openingFlag) and not second & elevatorFlag)
                or (second & railingFlag and first & (wallFlag | openingFlag) and not first & elevatorFlag))


def FootprintsOverlap(firstCorners, firstAxes, secondCorners, secondAxes, tolerance):
    # Bounds and empty-geometry rejection happen before the caller prepares data.
    polygons = (firstCorners, secondCorners)
    for axisX, axisY in firstAxes + secondAxes:
        projections = [[x * axisX + y * axisY for x, y in polygon] for polygon in polygons]
        if min(max(projections[0]), max(projections[1])) - max(min(projections[0]), min(projections[1])) <= tolerance:
            return False
    return True


def FootprintContainment(corners, otherCorners, otherAxes, tolerance):
    equal = True
    for axisX, axisY in otherAxes:
        projections = [x * axisX + y * axisY for x, y in corners]
        otherProjections = [x * axisX + y * axisY for x, y in otherCorners]
        low, high = min(projections), max(projections)
        otherLow, otherHigh = min(otherProjections), max(otherProjections)
        if low < otherLow - tolerance or high > otherHigh + tolerance:
            return False, equal
        equal = equal and abs(low - otherLow) <= tolerance and abs(high - otherHigh) <= tolerance
    return True, equal


def SignificantPathOverlap(polygons, tolerance):
    for polygon in polygons:
        area = abs(sum(polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
                       - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
                       for index in range(len(polygon)))) / 2
        perimeter = sum(math.hypot(polygon[index][0] - polygon[(index + 1) % len(polygon)][0],
                                   polygon[index][1] - polygon[(index + 1) % len(polygon)][1])
                        for index in range(len(polygon)))
        if perimeter > 0 and area / perimeter > tolerance / 2:
            return True
    return False


def JunctionReach(rays, scale):
    """Conservative radius; rays are (directionX, directionY, halfWidth, miter)."""
    halfWidth = max(ray[2] for ray in rays)
    radius = halfWidth + max(.01, .0001 / scale)
    maxMiter = max(1, *(abs(ray[3]) for ray in rays))
    for index, first in enumerate(rays):
        for second in rays[index + 1:]:
            cross = abs(first[0] * second[1] - first[1] * second[0])
            if cross >= 1e-6:
                radius = max(radius, (2 * halfWidth + 2 * halfWidth / cross) * maxMiter)
    return radius + .04


def RigidTranslation(previous, current):
    if not previous or len(previous) != len(current):
        return None
    deltaX, deltaY = current[0][1] - previous[0][1], current[0][2] - previous[0][2]
    for old, new in zip(previous, current):
        if old[0] != new[0] or old[5:] != new[5:]:
            return None
        if any(abs(new[index] - old[index] - delta) > 1e-7
               for index, delta in ((1, deltaX), (2, deltaY), (3, deltaX), (4, deltaY))):
            return None
    return deltaX, deltaY
