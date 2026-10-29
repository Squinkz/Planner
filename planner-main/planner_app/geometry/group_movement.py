"""Numeric group travel and attachment constraints; no models or view state."""
import math


def OpeningTransferLength(direction, delta, pixelsPerMillimeter, zoom):
    length = math.hypot(*direction)
    if length <= 1e-10:
        return None
    across = abs(direction[0] * delta[1] - direction[1] * delta[0]) / length
    return None if across * pixelsPerMillimeter * zoom <= 1 else length


def PlanOpeningTransfer(sourceLength, sourceFraction, targetLength, targetFraction, openings, reversedAlongWall):
    """Fit a rigid opening group without changing order or relative distances."""
    sign = -1 if reversedAlongWall else 1
    offsets = [(fraction - sourceFraction) * sourceLength * sign for fraction, length in openings]
    lower = max(length / 2 - offset for (fraction, length), offset in zip(openings, offsets))
    upper = min(targetLength - length / 2 - offset for (fraction, length), offset in zip(openings, offsets))
    if lower > upper:
        return None
    distance = max(lower, min(upper, targetFraction * targetLength))
    fractions = [(distance + offset) / targetLength for offset in offsets]
    return fractions, abs(distance - targetFraction * targetLength) > .01


def ProjectGroupTravel(delta, parentDirections):
    """Sequentially project onto fixed parent axes, retaining the last axis.

    Opposing axes are compatible. Nonparallel nondegenerate axes block travel.
    Repeated projection is intentional: collapsing parallel axes changes rounding.
    """
    travel = None
    for directionX, directionY in parentDirections:
        length = math.hypot(directionX, directionY)
        if length > 1e-10:
            direction = directionX / length, directionY / length
            if travel is not None and abs(travel[0] * direction[1] - travel[1] * direction[0]) > 1e-6:
                return (0.0, 0.0), travel, True
            travel = direction
            distance = delta[0] * direction[0] + delta[1] * direction[1]
            delta = direction[0] * distance, direction[1] * distance
    return delta, travel, False


def GroupOpeningLimits(travel, openings, stationary, duplicate = False):
    """Intersect fixed-parent travel limits in original opening/blocker order.

    Openings: (parent key, direction, length, original fraction, size, vertex index).
    An optional seventh field supplies reserved-space bounds for pocket/barn doors.
    Stationary: parent key -> ordered (center, first fraction, second fraction).
    A selected endpoint constrains the axis, but does not add whole-opening bounds.
    Copies ignore source/neighbour intervals; final collision validation decides.
    """
    minimum, maximum = -float("inf"), float("inf")
    for record in openings:
        parent, direction, length, fraction, size, vertexIndex = record[:6]
        if vertexIndex is not None:
            continue
        sign = 1 if direction[0] * travel[0] + direction[1] * travel[1] >= 0 else -1
        center = fraction * length
        low, high = record[6] if len(record) > 6 else (0, 1)
        lower, upper = low * length + size / 2 - center, high * length - size / 2 - center
        for otherCenter, firstFraction, secondFraction in (() if duplicate else stationary.get(parent, ())):
            if otherCenter < fraction:
                lower = max(lower, secondFraction * length + size / 2 - center)
            else:
                upper = min(upper, firstFraction * length - size / 2 - center)
        if sign < 0:
            lower, upper = -upper, -lower
        minimum, maximum = max(minimum, lower), min(maximum, upper)
    return minimum, maximum


def BoundGroupTravel(delta, travel, minimum, maximum):
    distance = delta[0] * travel[0] + delta[1] * travel[1]
    distance = max(minimum, min(maximum, distance)) if minimum <= maximum else 0
    return travel[0] * distance, travel[1] * distance


def TranslatedOpeningFraction(originalFraction, delta, direction):
    lengthSquared = direction[0] * direction[0] + direction[1] * direction[1]
    if lengthSquared <= 1e-10:
        return None
    return originalFraction + (delta[0] * direction[0] + delta[1] * direction[1]) / lengthSquared


def AttachedConstraintPoint(first, second, fraction, normalOffset):
    directionX, directionY = second[0] - first[0], second[1] - first[1]
    length = math.hypot(directionX, directionY)
    normalX, normalY = (-directionY / length, directionX / length) if length > 1e-10 else (0.0, 0.0)
    return (first[0] + directionX * fraction + normalX * normalOffset,
            first[1] + directionY * fraction + normalY * normalOffset)
