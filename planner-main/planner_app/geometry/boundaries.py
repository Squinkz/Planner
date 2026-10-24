"""Incremental numeric boundary classification and ordered contour assembly."""
import math


def GroupContourBounds(bounds):
    """Group intersecting bounds, retaining input order and isolated empty items."""
    parents = list(range(len(bounds)))
    active = []
    for index in sorted(range(len(bounds)), key = lambda index: bounds[index][0]):
        left, top, right, bottom = bounds[index]
        active = [other for other in active if bounds[other][2] >= left]
        for other in active:
            otherLeft, otherTop, otherRight, otherBottom = bounds[other]
            if not (left < right and top < bottom and otherLeft < otherRight and otherTop < otherBottom
                    and left < otherRight and right > otherLeft and top < otherBottom and bottom > otherTop):
                continue
            first, second = index, other
            while parents[first] != first:
                parents[first] = parents[parents[first]]
                first = parents[first]
            while parents[second] != second:
                parents[second] = parents[parents[second]]
                second = parents[second]
            parents[first] = second
        active.append(index)
    components = {}
    for index in range(len(bounds)):
        parent = index
        while parents[parent] != parent:
            parent = parents[parent]
        components.setdefault(parent, []).append(index)
    return list(components.values())


def TraceBoundaryContours(fillContours, extent, joinContours = True, fillRule = 1, state = None, edgeCache = None):
    """Trace prepared numeric contours; return rings/segments and reusable state.

    Each contour is (left, top, right, bottom, edgeTuples), where an edge is
    (x1, y1, x2, y2). Extent is the source path's (width, height). Caches are
    supplied explicitly by their owner; coordinates keep the caller's units.
    """
    edgeCoordinates = [edge for contour in fillContours for edge in contour[4]]
    if edgeCache is None:
        edgeCache = {}
    edgeBounds = [(min(firstX, secondX), min(firstY, secondY), max(firstX, secondX), max(firstY, secondY))
                  for firstX, firstY, secondX, secondY in edgeCoordinates]
    if not edgeCoordinates:
        return [], None
    contourCounts = {}
    for contour in fillContours:
        contourCounts[contour] = contourCounts.get(contour, 0) + 1
    traceMode = (joinContours, fillRule)
    previousEdges = {}
    changedBounds = []
    if state is not None and state[0] == traceMode:
        previousEdges = state[2]
        for contour in contourCounts.keys() | state[1].keys():
            if contourCounts.get(contour, 0) != state[1].get(contour, 0):
                left, top, right, bottom = contour[:4]
                margin = max(.0001, 16 * max(math.ulp(value) for value in contour[:4]))
                changedBounds.append((left - margin, top - margin, right + margin, bottom + margin))
    reusable = {}
    activeBounds = None
    for index, coordinates in enumerate(edgeCoordinates):
        previous = previousEdges.get(coordinates)
        left, top, right, bottom = edgeBounds[index]
        if previous is not None:
            margin = max(.0001, 16 * max(math.ulp(value) for value in coordinates))
            if not any(left - margin < changedRight and right + margin > changedLeft
                       and top - margin < changedBottom and bottom + margin > changedTop
                       for changedLeft, changedTop, changedRight, changedBottom in changedBounds):
                reusable[index] = previous
                continue
        if activeBounds is None:
            activeBounds = (left, top, right, bottom)
        else:
            activeBounds = (min(left, activeBounds[0]), min(top, activeBounds[1]),
                            max(right, activeBounds[2]), max(bottom, activeBounds[3]))
    edgeValues = {}
    cellSize = max(extent[0], extent[1], 1e-5) / math.sqrt(len(edgeCoordinates))

    def Cells(bounds):
        left, top, right, bottom = bounds
        for x in range(math.floor((left - 1e-8) / cellSize), math.floor((right + 1e-8) / cellSize) + 1):
            for y in range(math.floor((top - 1e-8) / cellSize), math.floor((bottom + 1e-8) / cellSize) + 1):
                yield x, y

    edgeBuckets = {}
    fillBuckets = {}
    if activeBounds is not None:
        # Index the complete spans that need retracing, including unchanged
        # intersections along their far ends. Distant cached edges need no
        # spatial cells, while a cold/full rebuild still indexes everything.
        left, top, right, bottom = activeBounds
        margin = max(.0001, 16 * max(math.ulp(value) for value in activeBounds))
        for index, bounds in enumerate(edgeBounds):
            if (bounds[0] <= right + margin and bounds[2] >= left - margin
                    and bounds[1] <= bottom + margin and bounds[3] >= top - margin):
                for cell in Cells(bounds):
                    edgeBuckets.setdefault(cell, []).append(index)
        for index, contour in enumerate(fillContours):
            if (contour[0] <= right + margin and contour[2] >= left - margin
                    and contour[1] <= bottom + margin and contour[3] >= top - margin):
                for cell in Cells(contour[:4]):
                    fillBuckets.setdefault(cell, []).append(index)
    boundaryEdges = []
    for edgeIndex, coordinates in enumerate(edgeCoordinates):
        previous = reusable.get(edgeIndex)
        if previous is not None:
            boundaryEdges.extend(previous)
            edgeValues[coordinates] = previous
            continue
        # Unchanged edges reuse their segments without allocating point pairs.
        first, second = coordinates[:2], coordinates[2:]
        direction = (second[0] - first[0], second[1] - first[1])
        lengthSquared = (direction[0] * direction[0] + direction[1] * direction[1])
        splits = [0.0, 1.0]
        left, top, right, bottom = edgeBounds[edgeIndex]
        # Only edges in intersecting spatial cells can split this segment.
        cells = tuple(Cells(edgeBounds[edgeIndex]))
        candidates = []
        for otherIndex in sorted({index for cell in cells for index in edgeBuckets.get(cell, ())}):
            if otherIndex == edgeIndex:
                continue
            otherLeft, otherTop, otherRight, otherBottom = edgeBounds[otherIndex]
            if (right + 1e-8 < otherLeft or otherRight + 1e-8 < left
                    or bottom + 1e-8 < otherTop or otherBottom + 1e-8 < top):
                continue
            candidates.append(otherIndex)
        probeCells = Cells((left - .00001, top - .00001, right + .00001, bottom + .00001))
        contours = [index for index in sorted({index for cell in probeCells for index in fillBuckets.get(cell, ())})
                    if fillContours[index][0] <= right + .00001 and fillContours[index][2] >= left - .00001
                    and fillContours[index][1] <= bottom + .00001 and fillContours[index][3] >= top - .00001]
        # An unchanged edge only needs retracing if a nearby edge or fill
        # changes. Keep exterior segments outside the edited intersection.
        edgeKey = (coordinates, tuple(edgeCoordinates[index] for index in candidates),
                   tuple(fillContours[index] for index in contours))
        cached = edgeCache.pop(edgeKey, None)
        if cached is not None:
            edgeCache[edgeKey] = cached
            boundaryEdges.extend(cached)
            edgeValues[coordinates] = cached
            continue
        edgeSegments = []
        for otherIndex in candidates:
            otherFirstX, otherFirstY, otherSecondX, otherSecondY = edgeCoordinates[otherIndex]
            otherDirection = (otherSecondX - otherFirstX, otherSecondY - otherFirstY)
            offset = (otherFirstX - first[0], otherFirstY - first[1])
            cross = direction[0] * otherDirection[1] - direction[1] * otherDirection[0]
            if abs(cross) > 1e-10:
                fraction = (offset[0] * otherDirection[1] - offset[1] * otherDirection[0]) / cross
                otherFraction = (offset[0] * direction[1] - offset[1] * direction[0]) / cross
                if -1e-9 <= fraction <= 1 + 1e-9 and -1e-9 <= otherFraction <= 1 + 1e-9:
                    splits.append(max(0.0, min(1.0, fraction)))
            elif abs(offset[0] * direction[1] - offset[1] * direction[0]) < 1e-8:
                # Overlapping collinear edges need the same split points.
                for position in ((otherFirstX, otherFirstY), (otherSecondX, otherSecondY)):
                    fraction = ((position[0] - first[0]) * direction[0] + (position[1] - first[1]) * direction[1]) / lengthSquared
                    if 0 < fraction < 1:
                        splits.append(fraction)
        splits.sort()
        normal = (-direction[1] / math.sqrt(lengthSquared), direction[0] / math.sqrt(lengthSquared))
        for start, end in zip(splits, splits[1:]):
            segmentLength = (end - start) * math.sqrt(lengthSquared)
            if segmentLength < 1e-8:
                continue
            middle = (start + end) / 2
            midpoint = (first[0] + direction[0] * middle, first[1] + direction[1] * middle)
            # Nearly straight joins can leave a boundary sliver narrower
            # than 1e-5 geometry units. A larger probe skips across it and
            # leaves open contours that close with interior diagonals.
            # Keep the probe representable when far from the world origin.
            probeDistance = max(1e-10, 8 * max(math.ulp(midpoint[0]), math.ulp(midpoint[1])))
            probeScale = min(probeDistance, segmentLength * 0.001)
            probeOffset = (normal[0] * probeScale, normal[1] * probeScale)
            # Qt's fuzzy ray intersections can classify a point on the wrong
            # side of a nearly horizontal edge after an alignment snap.
            # Use signed crossings without relative-coordinate comparisons.
            filledSides = []
            for probe in ((midpoint[0] + probeOffset[0], midpoint[1] + probeOffset[1]),
                          (midpoint[0] - probeOffset[0], midpoint[1] - probeOffset[1])):
                probeX, probeY = probe[0], probe[1]
                winding = 0
                cell = (math.floor(probeX / cellSize), math.floor(probeY / cellSize))
                for contourIndex in fillBuckets.get(cell, ()):
                    left, top, right, bottom, contourEdges = fillContours[contourIndex]
                    if not (left <= probeX <= right and top <= probeY <= bottom):
                        continue
                    for firstX, firstY, secondX, secondY in contourEdges:
                        if firstY <= probeY < secondY:
                            cross = ((secondX - firstX) * (probeY - firstY)
                                     - (secondY - firstY) * (probeX - firstX))
                            if cross > 0:
                                winding += 1
                        elif secondY <= probeY < firstY:
                            cross = ((secondX - firstX) * (probeY - firstY)
                                     - (secondY - firstY) * (probeX - firstX))
                            if cross < 0:
                                winding -= 1
                filledSides.append(winding != 0)
            leftFilled, rightFilled = filledSides
            if leftFilled == rightFilled:
                continue
            startPoint = (first[0] + direction[0] * start, first[1] + direction[1] * start)
            endPoint = (first[0] + direction[0] * end, first[1] + direction[1] * end)
            edgeSegments.append((startPoint, endPoint) if leftFilled else (endPoint, startPoint))
        edgeCache[edgeKey] = edgeSegments
        edgeValues[coordinates] = edgeSegments
        boundaryEdges.extend(edgeSegments)
    while len(edgeCache) > max(4096, len(edgeCoordinates) * 4):
        edgeCache.pop(next(iter(edgeCache)))
    state = (traceMode, contourCounts, edgeValues)
    if not joinContours:
        return boundaryEdges, state

    # Join exterior segments into closed contours, including room holes.
    # Match endpoints by distance rather than rounded coordinates. Two
    # numerically identical intersections can straddle a rounding boundary,
    # breaking a contour and making closeSubpath draw a diagonal across it.
    segments = {}
    endpointBuckets = {}
    endpointPoints = []
    exactEndpoints = {}
    endpointTolerance = 1e-6
    for first, second in boundaryEdges:
        endpointKeys = []
        for point in (first, second):
            coordinates = (point[0], point[1])
            exact = exactEndpoints.get(coordinates)
            if exact is not None:
                endpointKeys.append(exact)
                continue
            bucketX = math.floor(point[0] / endpointTolerance)
            bucketY = math.floor(point[1] / endpointTolerance)
            matches = [index for x in range(bucketX - 1, bucketX + 2)
                       for y in range(bucketY - 1, bucketY + 2)
                       for index in endpointBuckets.get((x, y), ())
                       if math.hypot(coordinates[0] - endpointPoints[index][0],
                                     coordinates[1] - endpointPoints[index][1]) <= endpointTolerance]
            if matches:
                endpointKeys.append(min(matches))
            else:
                endpointKeys.append(len(endpointPoints))
                endpointBuckets.setdefault((bucketX, bucketY), []).append(len(endpointPoints))
                endpointPoints.append(coordinates)
            exactEndpoints[coordinates] = endpointKeys[-1]
        firstKey, secondKey = endpointKeys
        if firstKey == secondKey:
            continue
        segments[(firstKey, secondKey)] = (first, second)
    outgoing = {}
    for edgeKey in segments:
        outgoing.setdefault(edgeKey[0], []).append(edgeKey)
    contours = []
    while segments:
        edgeKey = next(iter(segments))
        first, second = segments.pop(edgeKey)
        points = [first, second]
        startKey = edgeKey[0]
        endKey = edgeKey[1]
        while endKey != startKey:
            for nextEdge in outgoing.get(endKey, ()):
                if nextEdge in segments:
                    break
            else:
                break
            first, second = segments.pop(nextEdge)
            points.append(second)
            endKey = nextEdge[1]
        contours.append(points)
    return contours, state
