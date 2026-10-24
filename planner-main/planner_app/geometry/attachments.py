"""Attachment selection, lazy connected traversal and wall-mounted opening fitting."""
import math


def AttachedVertexIndices(first, second, width, vertices, anchor = None):
    deltaX, deltaY = second[0] - first[0], second[1] - first[1]
    length = math.hypot(deltaX, deltaY)
    axisX, axisY = (deltaX / length, deltaY / length) if length > 1e-10 else (0.0, 0.0)
    attached = []
    for index, (x, y) in enumerate(vertices):
        if anchor is not None:
            connected = math.hypot(x - anchor[0], y - anchor[1]) <= .01
        else:
            offsetX, offsetY = x - first[0], y - first[1]
            along = offsetX * axisX + offsetY * axisY
            across = abs(offsetX * axisY - offsetY * axisX)
            connected = length > 1e-10 and -.01 <= along <= length + .01 and across <= width / 2 + .01
        if connected:
            attached.append(index)
    return attached


def ConnectedAttachments(seed, candidates, intersects = None):
    """Ordered breadth-first discovery with a lazy optional shape-contact backend.

    Seed and candidates are (opaque key, first point, second point). Without a backend,
    connections use coincident endpoints. The callback accepts two opaque keys;
    traversal preserves query order and never materializes a full adjacency graph.
    """
    objects = {entry[0]: entry for entry in candidates}
    objects[seed[0]] = seed
    pending, visited = [seed[0]], {seed[0]}
    for parent in pending:
        for key, first, second in candidates:
            if key in visited:
                continue
            if intersects is not None:
                connected = intersects(parent, key)
            else:
                connected = any(math.hypot(a[0] - b[0], a[1] - b[1]) <= .01
                                for a in objects[parent][1:] for b in (first, second))
            if connected:
                visited.add(key)
                pending.append(key)
    return pending[1:]


def FitOpeningCenters(first, second, parentLength, openings, remainingLength,
                      previous = None, fixedEnd = 0):
    """Fit ordered (key, fraction, length, previousFraction) records to a wall.

    Remaining length retains the caller's original summation order. Previous
    geometry is supplied only when openings should keep their physical position.
    Qt's endpoint equality policy is resolved by the adapter as fixedEnd 1 or 2.
    """
    if parentLength < remainingLength - .01:
        return None
    cursor = 0.0
    centers = []
    for key, fraction, length, oldCenter in openings:
        center = fraction * parentLength
        if previous is not None:
            oldFirst, oldSecond, oldLength = previous
            if fixedEnd == 1:
                center = oldCenter * oldLength
            elif fixedEnd == 2:
                center = parentLength - (1 - oldCenter) * oldLength
            elif abs(parentLength - oldLength) > .01:
                oldX = oldFirst[0] + (oldSecond[0] - oldFirst[0]) * oldCenter
                oldY = oldFirst[1] + (oldSecond[1] - oldFirst[1]) * oldCenter
                translationX = (first[0] - oldFirst[0] + second[0] - oldSecond[0]) / 2
                translationY = (first[1] - oldFirst[1] + second[1] - oldSecond[1]) / 2
                directionX, directionY = (second[0] - first[0]) / parentLength, (second[1] - first[1]) / parentLength
                center = ((oldX + translationX - first[0]) * directionX
                          + (oldY + translationY - first[1]) * directionY)
        desiredStart = center - length / 2
        start = max(cursor, min(parentLength - remainingLength, desiredStart))
        centers.append((key, (start + length / 2) / parentLength))
        cursor = start + length
        remainingLength -= length
    return centers


def OpeningWithinWall(parentLength, length, center):
    if parentLength < 1 or length < 1:
        return False
    halfSpan = length / (2 * parentLength)
    return not (center - halfSpan < -1e-8 or center + halfSpan > 1 + 1e-8)


def OpeningIntervalsOverlap(firstStart, firstEnd, secondStart, secondEnd):
    return min(firstEnd, secondEnd) - max(firstStart, secondStart) > 1e-8
