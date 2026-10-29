"""Numeric dimension-chain coverage, displayed rounding and visible span clipping."""
import math
from planner_app.measurement_units import imperialModes, measurementPrecisions


def ComputeStackedDimensionLengths(inner, additional, unitsMode, precision):
    """Points are coordinate pairs; owners are canonical, hashable identity keys."""
    if not additional:
        return []
    step = (25.4 / {"High": 16, "Medium": 4, "Low": 1}[precision]
            if unitsMode in imperialModes else measurementPrecisions[precision])
    byOwner, geometry = {}, []
    for index, (first, second, owners) in enumerate(inner):
        deltaX, deltaY = second[0] - first[0], second[1] - first[1]
        ticks = math.floor(math.hypot(deltaX, deltaY) / step + .5 + 1e-9)
        geometry.append((first[0], first[1], second[0], second[1], deltaX, deltaY, ticks))
        for owner in owners:
            byOwner.setdefault(owner, set()).add(index)
    result = []
    for first, second, owners, tier in additional:
        length = math.hypot(second[0] - first[0], second[1] - first[1])
        if length < .0001:
            result.append(length)
            continue
        inverseLength = 1 / length
        directionX = (second[0] - first[0]) * inverseLength
        directionY = (second[1] - first[1]) * inverseLength
        indices = set()
        for owner in owners:
            indices.update(byOwner.get(owner, ()))
        segments = []
        for index in indices:
            startX, startY, endX, endY, deltaX, deltaY, ticks = geometry[index]
            offsetX, offsetY = startX - first[0], startY - first[1]
            if abs(deltaX * directionY - deltaY * directionX) > .01:
                continue
            if abs(offsetX * directionY - offsetY * directionX) > .01:
                continue
            low = offsetX * directionX + offsetY * directionY
            high = (endX - first[0]) * directionX + (endY - first[1]) * directionY
            low, high = sorted((low, high))
            if low >= -.01 and high <= length + .01:
                segments.append((low, high, ticks))
        covered, totalTicks = 0.0, 0
        for low, high, ticks in sorted(segments):
            if abs(low - covered) > .01:
                break
            covered = high
            totalTicks += ticks
        result.append(totalTicks * step if abs(covered - length) <= .01 else length)
    return result


def VisibleDimensionPieces(first, second, owners):
    """Owners supply opaque key, endpoints and visibility; key equality is retained."""
    length = math.hypot(second[0] - first[0], second[1] - first[1])
    if length < .0001:
        return []
    inverseLength = 1 / length
    directionX = (second[0] - first[0]) * inverseLength
    directionY = (second[1] - first[1]) * inverseLength
    intervals = []
    for owner, start, end, visible in owners:
        low = (start[0] - first[0]) * directionX + (start[1] - first[1]) * directionY
        high = (end[0] - first[0]) * directionX + (end[1] - first[1]) * directionY
        intervals.append((min(low, high), max(low, high), owner, visible))
    if not intervals:
        return []
    low = min(start for start, end, owner, visible in intervals)
    high = max(end for start, end, owner, visible in intervals)
    intervals = [(0 if abs(start - low) < .01 else max(0, start),
                  length if abs(end - high) < .01 else min(length, end), owner, visible)
                 for start, end, owner, visible in intervals]
    stops = sorted({0.0, length, *(value for start, end, owner, visible in intervals for value in (start, end) if 0 < value < length)})
    pieces = []
    for start, end in zip(stops, stops[1:]):
        midpoint = (start + end) / 2
        members = [owner for low, high, owner, visible in intervals if low <= midpoint <= high and visible]
        if not members or end - start < .0001:
            continue
        a = (first[0] + directionX * start, first[1] + directionY * start)
        b = (first[0] + directionX * end, first[1] + directionY * end)
        if pieces and pieces[-1][2] == members and math.hypot(pieces[-1][1][0] - a[0], pieces[-1][1][1] - a[1]) < .0001:
            pieces[-1] = pieces[-1][0], b, members
        else:
            pieces.append((a, b, members))
    return pieces
