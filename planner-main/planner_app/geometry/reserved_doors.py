"""Pocket/barn-door reserved space, distinct from the actual doorway aperture."""
import math


def ReservedDoorSupportBounds(first, second, walls):
    dx, dy = second[0] - first[0], second[1] - first[1]
    length = math.hypot(dx, dy)
    if length < 1e-8:
        return 0.0, 1.0
    dx, dy = dx / length, dy / length
    intervals = [(0.0, length)]
    for start, end in walls:
        if any(abs((point[0] - first[0]) * dy - (point[1] - first[1]) * dx) > .01 for point in (start, end)):
            continue
        intervals.append(tuple(sorted((point[0] - first[0]) * dx + (point[1] - first[1]) * dy for point in (start, end))))
    intervals.sort()
    low, high = intervals[0]
    for start, end in intervals[1:]:
        if start <= high + .01:
            high = max(high, end)
        else:
            if low <= 0 and high >= length - .01:
                break
            low, high = start, end
    return min(0.0, low / length), max(1.0, high / length)


def ReservedDoorWallContact(first, second, width, start, end, bounds):
    dx, dy = second[0] - first[0], second[1] - first[1]
    length = math.hypot(dx, dy)
    if length < 1e-8:
        return None
    sides = [((point[0] - first[0]) * dy - (point[1] - first[1]) * dx) / length for point in (start, end)]
    if max(abs(side) for side in sides) <= .01:
        return "collinear"
    cross = dx * (end[1] - start[1]) - dy * (end[0] - start[0])
    otherLength = math.hypot(end[0] - start[0], end[1] - start[1])
    if abs(cross) <= length * max(otherLength, 1e-8) * 1e-6:
        return None
    along = ((start[0] - first[0]) * (end[1] - start[1]) - (start[1] - first[1]) * (end[0] - start[0])) / cross
    if (bounds[0] + .01 / length < along < bounds[1] - .01 / length
            and min(abs(side) for side in sides) <= width / 2 + .01
            and not (min(sides) < -width / 2 - .01 and max(sides) > width / 2 + .01)):
        return "branch"
    return None


def ReservedDoorWithinHost(parentLength, length, center, hingeAtSecond, bounds):
    if parentLength < 1 or length < 1:
        return False
    half = length / (2 * parentLength)
    first, second = center - half, center + half
    apertureFirst, apertureSecond = (center, second) if hingeAtSecond else (first, center)
    return (first >= bounds[0] - 1e-8 and second <= bounds[1] + 1e-8
            and apertureFirst >= -1e-8 and apertureSecond <= 1 + 1e-8)


def ReservedDoorPlacementBounds(parentLength, length, hingeAtSecond, bounds):
    half = length / (2 * max(parentLength, 1e-8))
    return ((max(bounds[0], -half), min(bounds[1], 1.0)) if hingeAtSecond else
            (max(bounds[0], 0.0), min(bounds[1], 1 + half)))


def ReservedDoorEditCenter(oldFirst, oldSecond, first, second, center, followMovement):
    """Keep a sliding division from stretching the door's world-space span."""
    oldX, oldY = oldSecond[0] - oldFirst[0], oldSecond[1] - oldFirst[1]
    dx, dy = second[0] - first[0], second[1] - first[1]
    oldLength = math.hypot(oldX, oldY)
    lengthSquared = dx * dx + dy * dy
    if oldLength < 1 or lengthSquared < 1:
        return None
    firstMove = first[0] - oldFirst[0], first[1] - oldFirst[1]
    secondMove = second[0] - oldSecond[0], second[1] - oldSecond[1]
    rigid = math.hypot(firstMove[0] - secondMove[0], firstMove[1] - secondMove[1]) <= 1e-8
    if rigid and followMovement:
        return center
    collinear = all(abs(move[0] * oldY - move[1] * oldX) / oldLength <= .01 for move in (firstMove, secondMove))
    if collinear:
        x, y = oldFirst[0] + oldX * center, oldFirst[1] + oldY * center
        return ((x - first[0]) * dx + (y - first[1]) * dy) / lengthSquared
    # An attached door can follow a rotated wall. A detached door cannot stay
    # at its old location after its supporting axis moves away from it.
    return center if followMovement else None
