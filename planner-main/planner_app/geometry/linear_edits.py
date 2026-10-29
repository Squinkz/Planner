"""Numeric proposals for linear subdivision and dissolution; no scene mutation."""
import math


def PlanSubdivision(segments, openings):
    """Segments contain key, endpoints, endpoint miters and split fraction.

    Openings contain key, parent key and center fraction. Keys are opaque;
    adapters retain responsibility for identities, model creation and collision
    validation. Only selected segments and affected opening moves are retained.
    """
    halves = {}
    for key, first, second, firstMiter, secondMiter, fraction in segments:
        directionX, directionY = second[0] - first[0], second[1] - first[1]
        if math.hypot(directionX, directionY) < 2e-8 or not 0 < fraction < 1:
            raise ValueError("Cannot subdivide a degenerate segment.")
        midpoint = (first[0] + directionX * fraction, first[1] + directionY * fraction)
        halves[key] = ((first, midpoint, firstMiter, 0.0), (midpoint, second, 0.0, secondMiter), fraction)
    moves = []
    for key, parent, center in openings:
        parts = halves.get(parent)
        if parts is None:
            continue
        fraction = parts[2]
        secondHalf = center > fraction
        target = (center - fraction) / (1 - fraction) if secondHalf else center / fraction
        moves.append((key, parent, int(secondHalf), target))
    return halves, moves


def PlanDissolution(vertex, source, other):
    """Preserve the chosen source's direction and the two outer endpoint miters."""
    sourceFirst, sourceSecond, sourceFirstMiter, sourceSecondMiter = source
    otherFirst, otherSecond, otherFirstMiter, otherSecondMiter = other
    sourceFirstShared = math.hypot(vertex[0] - sourceFirst[0], vertex[1] - sourceFirst[1]) <= .01
    otherFirstShared = math.hypot(vertex[0] - otherFirst[0], vertex[1] - otherFirst[1]) <= .01
    otherOuter = otherSecond if otherFirstShared else otherFirst
    otherMiter = otherSecondMiter if otherFirstShared else otherFirstMiter
    first = otherOuter if sourceFirstShared else sourceFirst
    second = sourceSecond if sourceFirstShared else otherOuter
    direction = (second[0] - first[0], second[1] - first[1])
    length = math.hypot(*direction)
    if length < 1e-8:
        raise ValueError("Cannot dissolve: the new object would have zero length.")
    return (first, second, otherMiter if sourceFirstShared else sourceFirstMiter,
            sourceSecondMiter if sourceFirstShared else otherMiter, direction, length)
