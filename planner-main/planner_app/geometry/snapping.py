"""Numeric grid intervals, ordered target lookup and constrained point snapping."""
import math
from bisect import bisect_left, bisect_right


def GridIntervals(pixelsPerMillimeter, imperial):
    minimumStep = 90.0 / pixelsPerMillimeter
    if imperial:
        minimumInches = minimumStep / 25.4
        intervals = (1 / 16, 1 / 8, 1 / 4, .5, 1, 2, 4, 6, 12, 24, 48)
        inches = next((step for step in intervals if step >= minimumInches), None)
        if inches is None:
            inches = 48 * 2 ** math.ceil(math.log2(minimumInches / 48))
        majorStep = inches * 25.4
        return majorStep, majorStep / 4
    magnitude = 10.0 ** math.floor(math.log10(minimumStep))
    majorStep = next(multiplier * magnitude for multiplier in (1, 2, 5, 10)
                     if multiplier * magnitude >= minimumStep)
    return majorStep, majorStep / 5.0


def PrepareTargetIndex(targets):
    orderedX = sorted((target[0], index) for index, target in enumerate(targets))
    orderedY = sorted((target[1], index) for index, target in enumerate(targets))
    return ([value for value, index in orderedX], [index for value, index in orderedX],
            [value for value, index in orderedY], [index for value, index in orderedY])


def NearbyTargetIndices(position, margin, targetIndex, alignment = True):
    """Preserve source order, including duplicate targets and equal-distance ties."""
    xValues, xIndices, yValues, yIndices = targetIndex
    positionX, positionY = position
    indices = set(xIndices[bisect_left(xValues, positionX - margin):bisect_right(xValues, positionX + margin)])
    if alignment:
        indices.update(yIndices[bisect_left(yValues, positionY - margin):bisect_right(yValues, positionY + margin)])
    return sorted(indices)


def NearbyPointIndices(position, margin, targetIndex):
    """Ordered square broad phase; the caller retains its native distance test."""
    xValues, xIndices, yValues, yIndices = targetIndex
    positionX, positionY = position
    xStart, xEnd = bisect_left(xValues, positionX - margin), bisect_right(xValues, positionX + margin)
    yStart, yEnd = bisect_left(yValues, positionY - margin), bisect_right(yValues, positionY + margin)
    return sorted(set(xIndices[xStart:xEnd]).intersection(yIndices[yStart:yEnd]))


def PrepareRayTargets(targets):
    """Prepare one numeric snapshot for repeated normalized-ray queries.

    Alignment uses coordinates only. Keep each coordinate's first source index
    so duplicate removal cannot alter strict-distance ties or axis insertion order.
    Nonfinite target data keeps the original full-sweep path.
    """
    firstX, firstY = {}, {}
    directTargets, directIndices = [], []
    for index, (x, y, direct) in enumerate(targets):
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        firstX.setdefault(x, index)
        firstY.setdefault(y, index)
        if direct:
            directTargets.append((x, y))
            directIndices.append(index)
    orderedX, orderedY = sorted(firstX.items()), sorted(firstY.items())
    return ((PrepareTargetIndex(directTargets), directIndices),
            ([coordinate for coordinate, index in orderedX], [index for coordinate, index in orderedX]),
            ([coordinate for coordinate, index in orderedY], [index for coordinate, index in orderedY]))


def FindRaySnaps(position, targets, scale, vertexRange, alignmentEnabled, anchor, direction, prepared):
    positionX, positionY = position
    nearest, nearestDistance = None, vertexRange
    pointIndex, pointSources = prepared[0]
    if vertexRange > 0 and pointSources:
        margin = vertexRange / scale
        margin += 8 * (math.ulp(positionX) + math.ulp(positionY) + math.ulp(margin))
        for pointPosition in NearbyPointIndices(position, margin, pointIndex):
            x, y, direct = targets[pointSources[pointPosition]]
            distance = math.hypot(positionX - x, positionY - y) * scale
            offsetX, offsetY = x - anchor[0], y - anchor[1]
            onRay = abs(offsetX * direction[1] - offsetY * direction[0]) <= .01
            onRay = onRay and offsetX * direction[0] + offsetY * direction[1] >= 0
            if onRay and distance < nearestDistance:
                nearest, nearestDistance = (x, y), distance
    if nearest is not None or not alignmentEnabled:
        return nearest, {}
    ranges = []
    radius = 20.0 / scale
    for axis in (0, 1):
        if abs(direction[axis]) < 1e-10:
            continue
        coordinates, sourceIndices = prepared[axis + 1]
        # The actual intersection is tested below. Widen the coordinate strip
        # for subtraction/division/reconstruction roundoff at large coordinates.
        margin = radius + 8 * (math.ulp(position[axis]) + math.ulp(anchor[axis]) + math.ulp(radius))
        start = bisect_left(coordinates, position[axis] - margin)
        end = bisect_right(coordinates, position[axis] + margin)
        ranges.append((axis, start, end))
    # Dense, mostly unique ranges are cheaper to stream than to sort anew for
    # every anchor. Both paths retain the exact original target/axis order.
    if sum(end - start for axis, start, end in ranges) > len(targets):
        axes = [axis for axis, start, end in ranges]
        candidates = ((index, axis, target[axis]) for index, target in enumerate(targets) for axis in axes)
    else:
        candidates = [(prepared[axis + 1][1][index], axis, prepared[axis + 1][0][index])
                      for axis, start, end in ranges for index in range(start, end)]
        candidates.sort(key = lambda candidate: candidate[:2])
    alignments = {}
    # The axis that first enters this dict wins final equal-distance ties,
    # even when its eventual winning coordinate came from a later target.
    for sourceIndex, axis, coordinate in candidates:
        along = (coordinate - anchor[axis]) / direction[axis]
        if along < 0:
            continue
        intersection = (anchor[0] + direction[0] * along, anchor[1] + direction[1] * along)
        distance = math.hypot(positionX - intersection[0], positionY - intersection[1]) * scale
        if distance < alignments.get(axis, (None, 20.0, None))[1]:
            alignments[axis] = (coordinate, distance, intersection)
    return nearest, alignments


def SnapPoint(position, targets, scale, vertexRange, alignmentEnabled, gridStep,
              angleAnchor = None, angleDirection = None, targetIndex = None, rayTargets = None):
    """Return (point, applied, priority, guides); targets are (x, y, direct)."""
    positionX, positionY = position
    nearestVertex, nearestDistance = None, vertexRange
    alignments = {}
    alignmentRange = 20.0
    indices = range(len(targets))
    if targetIndex is not None and angleAnchor is None:
        indices = NearbyTargetIndices(position, max(vertexRange, alignmentRange) / scale,
                                      targetIndex, alignmentEnabled)
    useRayIndex = (rayTargets is not None and angleAnchor is not None and scale > 0 and math.isfinite(scale)
                   and all(math.isfinite(value) for value in (*position, *angleAnchor, *angleDirection))
                   and abs(math.hypot(*angleDirection) - 1.0) <= 1e-9)
    if useRayIndex:
        nearestVertex, alignments = FindRaySnaps(position, targets, scale, vertexRange,
                                               alignmentEnabled, angleAnchor, angleDirection, rayTargets)
    else:
        for index in indices:
            vertexX, vertexY, directSnap = targets[index]
            distance = math.hypot(positionX - vertexX, positionY - vertexY) * scale
            onAngleLine = True
            if angleAnchor is not None:
                offsetX, offsetY = vertexX - angleAnchor[0], vertexY - angleAnchor[1]
                onAngleLine = abs(offsetX * angleDirection[1] - offsetY * angleDirection[0]) <= .01
                onAngleLine = onAngleLine and offsetX * angleDirection[0] + offsetY * angleDirection[1] >= 0
            if directSnap and onAngleLine and distance < nearestDistance:
                nearestVertex, nearestDistance = (vertexX, vertexY), distance
            if alignmentEnabled:
                for axis, coordinate, pixelDistance in (
                        (0, vertexX, abs(positionX - vertexX) * scale),
                        (1, vertexY, abs(positionY - vertexY) * scale)):
                    intersection = None
                    if angleAnchor is not None:
                        component = angleDirection[axis]
                        if abs(component) < 1e-10:
                            continue
                        along = (coordinate - angleAnchor[axis]) / component
                        if along < 0:
                            continue
                        intersection = (angleAnchor[0] + angleDirection[0] * along,
                                        angleAnchor[1] + angleDirection[1] * along)
                        pixelDistance = math.hypot(positionX - intersection[0], positionY - intersection[1]) * scale
                    if pixelDistance < alignments.get(axis, (None, alignmentRange, None))[1]:
                        alignments[axis] = (coordinate, pixelDistance, intersection)
    if nearestVertex is not None:
        return nearestVertex, True, 0, []
    snappedPosition, applied, priority = position, False, 3
    if gridStep is not None:
        priority = 2
        if angleAnchor is None:
            applied = True
            snappedPosition = (round(positionX / gridStep) * gridStep, round(positionY / gridStep) * gridStep)
        else:
            candidates = []
            for coordinate, anchorCoordinate, component in (
                    (positionX, angleAnchor[0], angleDirection[0]),
                    (positionY, angleAnchor[1], angleDirection[1])):
                if abs(component) > 1e-10:
                    along = (round(coordinate / gridStep) * gridStep - anchorCoordinate) / component
                    if along >= 0:
                        candidates.append((angleAnchor[0] + angleDirection[0] * along,
                                           angleAnchor[1] + angleDirection[1] * along))
            if candidates:
                applied = True
                snappedPosition = min(candidates, key = lambda candidate:
                    math.hypot(positionX - candidate[0], positionY - candidate[1]))
    guides = []
    if alignments:
        applied, priority = True, 1
        if angleAnchor is not None:
            snappedPosition = min(alignments.values(), key = lambda target: target[1])[2]
            guides = [(axis, target[0]) for axis, target in sorted(alignments.items())
                      if abs(snappedPosition[axis] - target[0]) <= .01]
        else:
            coordinates = list(snappedPosition)
            for axis, (coordinate, distance, intersection) in sorted(alignments.items()):
                coordinates[axis] = coordinate
                guides.append((axis, coordinate))
            snappedPosition = tuple(coordinates)
    return snappedPosition, applied, priority, guides
