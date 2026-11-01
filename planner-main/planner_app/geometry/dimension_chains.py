"""Numeric dimension-chain coverage, displayed rounding and visible span clipping."""
import math
from planner_app.measurement_units import imperialModes, measurementPrecisions


def ComputeStackedDimensionLengths(inner, additional, unitsMode, precision, includeInner = False):
    """Balance shared display positions against each measured overall span.

    Points are coordinate pairs; owners are canonical, hashable identity keys.
    Incomplete chains retain ordinary geometric labels. Geometry is never edited.
    includeInner also returns inner-label overrides; None keeps ordinary rounding
    for a span outside a complete stack. Otherwise only upper lengths are returned.
    """
    if not additional:
        return ([None for span in inner], []) if includeInner else []
    step = (25.4 / {"High": 16, "Medium": 4, "Low": 1}[precision]
            if unitsMode in imperialModes else measurementPrecisions[precision])
    byOwner, geometry = {}, []
    for index, (first, second, owners) in enumerate(inner):
        deltaX, deltaY = second[0] - first[0], second[1] - first[1]
        geometry.append((first[0], first[1], second[0], second[1], deltaX, deltaY))
        for owner in owners:
            byOwner.setdefault(owner, set()).add(index)
    result, complete = [], []
    for rowIndex, (first, second, owners, tier) in enumerate(additional):
        length = math.hypot(second[0] - first[0], second[1] - first[1])
        result.append(length)
        if length < .0001:
            continue
        inverseLength = 1 / length
        directionX = (second[0] - first[0]) * inverseLength
        directionY = (second[1] - first[1]) * inverseLength
        indices = set()
        for owner in owners:
            indices.update(byOwner.get(owner, ()))
        segments = []
        for index in indices:
            startX, startY, endX, endY, deltaX, deltaY = geometry[index]
            offsetX, offsetY = startX - first[0], startY - first[1]
            if abs(deltaX * directionY - deltaY * directionX) > .01:
                continue
            if abs(offsetX * directionY - offsetY * directionX) > .01:
                continue
            low = offsetX * directionX + offsetY * directionY
            high = (endX - first[0]) * directionX + (endY - first[1]) * directionY
            low, high = sorted((low, high))
            if low >= -.01 and high <= length + .01:
                segments.append((low, high, index))
        # Use a canonical direction so input ordering and reversed dimension
        # arrows cannot choose different sides of a rounding tie.
        if first > second:
            segments = [(length - high, length - low, index) for low, high, index in segments]
        segments.sort()
        covered = 0.0
        for low, high, index in segments:
            if abs(low - covered) > .01:
                break
            covered = high
        else:
            if segments and abs(covered - length) <= .01:
                complete.append((rowIndex, length, tier, segments))

    innerTicks, anchors = [None] * len(geometry), [None] * len(geometry)
    # The largest complete span owns its intermediate rows and inner pieces.
    # Each outer label is rounded from its own endpoints, never from a sum of
    # independently rounded children.
    for rowIndex, length, tier, segments in sorted(complete, key = lambda row: (-row[1], -row[2], row[0])):
        indices = [index for low, high, index in segments]
        if any(anchors[index] is not None for index in indices):
            continue
        positions = [0.0] + [high for low, high, index in segments]
        positions[-1] = length
        positions = [round(position / step, 9) for position in positions]
        total = positions[-1]
        target = math.floor(total + .5 + 1e-9)
        localIndices = {index: local for local, index in enumerate(indices)}
        edges = [(index, index + 1, 0) for index in range(len(indices))]
        for otherIndex, otherLength, otherTier, otherSegments in complete:
            members = sorted(localIndices[index] for low, high, index in otherSegments if index in localIndices)
            if (len(members) == len(otherSegments) and members
                    and members[-1] - members[0] + 1 == len(members)):
                edges.append((members[0], members[-1] + 1, otherTier))

        # A common rounding phase preserves exact multiples of the display
        # step (including nominal opening widths). Restrict it to phases that
        # produce the independently rounded overall at the final endpoint.
        phaseLow, phaseHigh = max(0.0, target - total), min(1.0, target + 1 - total)
        centerPhase = (phaseLow + phaseHigh) / 2
        events = {}
        for index, position in enumerate(positions[1:-1], 1):
            phase = round(1 - (position % 1), 9)
            if phaseLow + 1e-8 < phase < phaseHigh - 1e-8:
                events.setdefault(phase, []).append(index)
        stops = []
        for phase, members in sorted(events.items()):
            # Rigid transforms can perturb nominally identical cut fractions.
            # Never choose a tiny artificial interval between those ties.
            if stops and phase - stops[-1][1] <= 1e-8:
                stops[-1][1] = phase
                stops[-1][2].extend(members)
            else:
                stops.append([phase, phase, list(members)])
        phase = (phaseLow + (stops[0][0] if stops else phaseHigh)) / 2
        ticks = [math.floor(position + phase) for position in positions]
        ticks[0], ticks[-1] = 0, target
        values = [ticks[end] - ticks[start] for start, end, edgeTier in edges]
        exact = [positions[end] - positions[start] for start, end, edgeTier in edges]
        atStop = [[] for position in positions]
        edgeLookup = {}
        for index, (start, end, edgeTier) in enumerate(edges):
            atStop[start].append(index)
            atStop[end].append(index)
            edgeLookup[start, end, edgeTier] = index
        mirrored, atEdge = [], [[] for edge in edges]
        count = len(indices)
        for index, (start, end, edgeTier) in enumerate(edges):
            opposite = edgeLookup.get((count - end, count - start, edgeTier))
            if (opposite is not None and opposite > index
                    and abs(positions[start] + positions[count - start] - total) * step <= .01
                    and abs(positions[end] + positions[count - end] - total) * step <= .01):
                pairIndex = len(mirrored)
                mirrored.append((index, opposite))
                atEdge[index].append(pairIndex)
                atEdge[opposite].append(pairIndex)
        error = sum((value - actual) ** 2 for value, actual in zip(values, exact))
        asymmetry = sum(abs(values[first] - values[second]) for first, second in mirrored)
        bestScore = (asymmetry, round(error, 8), abs(phase - centerPhase), phase)
        bestPhase = phase
        # Sweep shared endpoint changes rather than trying every phase against
        # every dimension. One cut affects only dimensions ending at that cut.
        for eventIndex, (eventLow, eventHigh, members) in enumerate(stops):
            affected = {edge for index in members for edge in atStop[index]}
            pairs = {pair for edge in affected for pair in atEdge[edge]}
            error -= sum((values[index] - exact[index]) ** 2 for index in affected)
            asymmetry -= sum(abs(values[mirrored[index][0]] - values[mirrored[index][1]]) for index in pairs)
            for index in members:
                ticks[index] += 1
            for index in affected:
                start, end, edgeTier = edges[index]
                values[index] = ticks[end] - ticks[start]
            error += sum((values[index] - exact[index]) ** 2 for index in affected)
            asymmetry += sum(abs(values[mirrored[index][0]] - values[mirrored[index][1]]) for index in pairs)
            nextPhase = stops[eventIndex + 1][0] if eventIndex + 1 < len(stops) else phaseHigh
            phase = (eventHigh + nextPhase) / 2
            score = (asymmetry, round(error, 8), abs(phase - centerPhase), phase)
            if score < bestScore:
                bestScore, bestPhase = score, phase
        ticks = [math.floor(position + bestPhase) for position in positions]
        ticks[0], ticks[-1] = 0, target
        for local, index in enumerate(indices):
            innerTicks[index] = ticks[local + 1] - ticks[local]
            anchors[index] = rowIndex

    for rowIndex, length, tier, segments in complete:
        indices = [index for low, high, index in segments]
        if anchors[indices[0]] is not None and all(anchors[index] == anchors[indices[0]] for index in indices):
            result[rowIndex] = sum(innerTicks[index] for index in indices) * step
    if includeInner:
        return [ticks * step if ticks is not None else None for ticks in innerTicks], result
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
