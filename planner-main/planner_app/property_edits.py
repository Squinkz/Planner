"""Numeric property edits and bulk-target policy without widgets or models."""
import math
from .measurement_units import MetricUnit

furnishingKinds = ("Furnishing", "NorthArrow", "Label", "RoomLabel")


def PropertyScale(fieldName, kind):
    return 10.0 if (fieldName in ("sillDepth", "wellDepth", "stepSize")
                    or fieldName == "width" and kind != "Stair"
                    or fieldName == "length" and kind in furnishingKinds) else 1000.0


def PlanPropertyTargets(entries, fieldName):
    """Entries carry (opaque identity, type name, vertex); return source positions.

    None means the ordinary single-target handler should run. False
    consumes incompatible mixed selections. Duplicate bodies retain their last
    vertex entry while preserving first-seen object order.
    """
    if len(entries) <= 1:
        return None
    kinds = {"Wall" if kind in ("Wall", "Pillar", "Column") else kind for key, kind, vertex in entries}
    if len(kinds) > 1:
        return False
    if fieldName in ("x", "y", "miter"):
        return [position for position, (key, kind, vertex) in enumerate(entries) if vertex is not None]
    return list({key: position for position, (key, kind, vertex) in enumerate(entries)}.values())


def RequestedPropertyMatches(fieldName, kind, rawValue, requested, unitsMode):
    if fieldName in ("length", "doorSize"):
        actual = rawValue / (2000 if fieldName == "doorSize" else 10 if kind in furnishingKinds else 1000)
    elif fieldName == "width":
        actual = rawValue / (1000 if kind == "Stair" else 10)
    elif fieldName == "miter":
        actual = rawValue
    else:
        actual = rawValue / 1000
    if fieldName != "miter":
        adaptive = "cm" if PropertyScale(fieldName, kind) == 10 else "m"
        oldDivisor, unused = MetricUnit("Adaptive Metric", adaptive)
        divisor, unused = MetricUnit(unitsMode, adaptive)
        actual *= oldDivisor / divisor
    return math.isclose(actual, requested, abs_tol = 1e-6)


def LinkedPropertySizes(width, length, fieldName, millimeters):
    if min(width, length) <= 0:
        return None
    original = width if fieldName == "width" else length
    factor = millimeters / original
    return width * factor, length * factor


def PlanLinearPropertySize(first, second, millimeters, minimumLength, centered = False):
    millimeters = max(millimeters, minimumLength)
    directionX, directionY = second[0] - first[0], second[1] - first[1]
    oldLength = math.hypot(directionX, directionY)
    if oldLength > 0:
        if centered:
            centerX, centerY = (first[0] + second[0]) / 2, (first[1] + second[1]) / 2
            factor = millimeters / oldLength / 2
            halfX, halfY = directionX * factor, directionY * factor
            return (centerX - halfX, centerY - halfY), (centerX + halfX, centerY + halfY)
        factor = millimeters / oldLength
        return None, (first[0] + directionX * factor, first[1] + directionY * factor)
    return None, (first[0] + millimeters, first[1])
