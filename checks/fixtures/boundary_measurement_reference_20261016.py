"""Frozen pre-optimization oracles for boundary/measurement parity and timings.

Captured before the boundary/measurement follow-up on 2026-10-16.
Keep this independent of the optimized methods; do not update it to mirror them.
"""
import math
from PySide6 import QtCore, QtGui
from planner_app.viewport.spatial_index import BoundsIndex
from planner_app.models import Wall, Pillar, Column, Window, Door, SilledWindow, CasementWindow, BifoldDoor, PocketDoor, SlidingDoor, BarnDoor, OpenDoorway, Fireplace


def OriginalTraceWallComponent(self, filledPath, joinContours = True, traceKey = None):
    edges = []
    edgeCoordinates = []
    fillContours = []
    for polygon in filledPath.toSubpathPolygons():
        contourEdges = []
        for index in range(len(polygon) - 1):
            first = polygon[index]
            second = polygon[index + 1]
            if QtCore.QLineF(first, second).length() > 1e-9:
                edges.append((first, second))
                contourEdges.append((first.x(), first.y(), second.x(), second.y()))
                edgeCoordinates.append(contourEdges[-1])
        bounds = polygon.boundingRect()
        fillContours.append((bounds.left(), bounds.top(), bounds.right(), bounds.bottom(), tuple(contourEdges)))
    edgeBounds = [(min(firstX, secondX), min(firstY, secondY), max(firstX, secondX), max(firstY, secondY))
                  for firstX, firstY, secondX, secondY in edgeCoordinates]
    if not edges:
        return QtGui.QPainterPath()
    # Reuse exterior segments of unchanged edges without rebuilding their
    # complete neighbor keys. Only changed fill bounds can affect their
    # intersections or inside/outside classification.
    contourCounts = {}
    for contour in fillContours:
        contourCounts[contour] = contourCounts.get(contour, 0) + 1
    contexts = getattr(self, "wallTraceContexts", None)
    if contexts is None:
        self.wallTraceContexts = contexts = {}
        self.wallTraceContextPoints = 0
    stored = contexts.pop(traceKey, None) if traceKey is not None else None
    if stored is not None:
        self.wallTraceContextPoints -= stored[1]
    if traceKey is None:
        state = self.wallTraceState
    else:
        state = stored[0] if stored is not None else None
    traceMode = (joinContours, filledPath.fillRule())
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
    bounds = filledPath.boundingRect()
    cellSize = max(bounds.width(), bounds.height(), 1e-5) / math.sqrt(len(edges))

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
    for edgeIndex, (first, second) in enumerate(edges):
        coordinates = edgeCoordinates[edgeIndex]
        previous = reusable.get(edgeIndex)
        if previous is not None:
            boundaryEdges.extend(previous)
            edgeValues[coordinates] = previous
            continue
        direction = second - first
        lengthSquared = QtCore.QPointF.dotProduct(direction, direction)
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
        edgeKey = ((first.x(), first.y(), second.x(), second.y()),
                   tuple((edges[index][0].x(), edges[index][0].y(), edges[index][1].x(), edges[index][1].y())
                         for index in candidates), tuple(fillContours[index] for index in contours))
        cached = self.wallBoundaryEdgeCache.pop(edgeKey, None)
        if cached is not None:
            self.wallBoundaryEdgeCache[edgeKey] = cached
            boundaryEdges.extend(cached)
            edgeValues[coordinates] = cached
            continue
        edgeSegments = []
        for otherIndex in candidates:
            otherFirst, otherSecond = edges[otherIndex]
            otherDirection = otherSecond - otherFirst
            offset = otherFirst - first
            cross = direction.x() * otherDirection.y() - direction.y() * otherDirection.x()
            if abs(cross) > 1e-10:
                fraction = (offset.x() * otherDirection.y() - offset.y() * otherDirection.x()) / cross
                otherFraction = (offset.x() * direction.y() - offset.y() * direction.x()) / cross
                if -1e-9 <= fraction <= 1 + 1e-9 and -1e-9 <= otherFraction <= 1 + 1e-9:
                    splits.append(max(0.0, min(1.0, fraction)))
            elif abs(offset.x() * direction.y() - offset.y() * direction.x()) < 1e-8:
                # Overlapping collinear edges need the same split points.
                for position in (otherFirst, otherSecond):
                    fraction = QtCore.QPointF.dotProduct(position - first, direction) / lengthSquared
                    if 0 < fraction < 1:
                        splits.append(fraction)
        splits.sort()
        normal = QtCore.QPointF(-direction.y(), direction.x()) / math.sqrt(lengthSquared)
        for start, end in zip(splits, splits[1:]):
            segmentLength = (end - start) * math.sqrt(lengthSquared)
            if segmentLength < 1e-8:
                continue
            midpoint = first + direction * ((start + end) / 2)
            # Nearly straight joins can leave a boundary sliver narrower
            # than 1e-5 geometry units. A larger probe skips across it and
            # leaves open contours that close with interior diagonals.
            # Keep the probe representable when far from the world origin.
            probeDistance = max(1e-10, 8 * max(math.ulp(midpoint.x()), math.ulp(midpoint.y())))
            probeOffset = normal * min(probeDistance, segmentLength * 0.001)
            # Qt's fuzzy ray intersections can classify a point on the wrong
            # side of a nearly horizontal edge after an alignment snap.
            # Use signed crossings without relative-coordinate comparisons.
            filledSides = []
            for probe in (midpoint + probeOffset, midpoint - probeOffset):
                probeX, probeY = probe.x(), probe.y()
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
            startPoint = first + direction * start
            endPoint = first + direction * end
            edgeSegments.append((startPoint, endPoint) if leftFilled else (endPoint, startPoint))
        self.wallBoundaryEdgeCache[edgeKey] = edgeSegments
        edgeValues[coordinates] = edgeSegments
        boundaryEdges.extend(edgeSegments)
    while len(self.wallBoundaryEdgeCache) > max(4096, len(edges) * 4):
        self.wallBoundaryEdgeCache.pop(next(iter(self.wallBoundaryEdgeCache)))
    state = (traceMode, contourCounts, edgeValues)
    if traceKey is None:
        self.wallTraceState = state
    else:
        # Connected components and their later crossing union need separate
        # histories. Bound both the count and retained coordinate volume.
        points = sum(len(contour[4]) * 2 for contour in contourCounts) + len(edgeValues) * 2
        points += sum(len(segments) * 2 for segments in edgeValues.values())
        if points <= 32768:
            contexts[traceKey] = (state, points)
            self.wallTraceContextPoints += points
            while len(contexts) > 8 or self.wallTraceContextPoints > 32768:
                evicted, size = contexts.pop(next(iter(contexts)))
                self.wallTraceContextPoints -= size

    if not joinContours:
        outlinePath = QtGui.QPainterPath()
        for first, second in boundaryEdges:
            outlinePath.moveTo(first)
            outlinePath.lineTo(second)
        return outlinePath

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
            coordinates = (point.x(), point.y())
            exact = exactEndpoints.get(coordinates)
            if exact is not None:
                endpointKeys.append(exact)
                continue
            bucketX = math.floor(point.x() / endpointTolerance)
            bucketY = math.floor(point.y() / endpointTolerance)
            matches = [index for x in range(bucketX - 1, bucketX + 2)
                       for y in range(bucketY - 1, bucketY + 2)
                       for index in endpointBuckets.get((x, y), ())
                       if math.hypot(point.x() - endpointPoints[index].x(),
                                     point.y() - endpointPoints[index].y()) <= endpointTolerance]
            if matches:
                endpointKeys.append(min(matches))
            else:
                endpointKeys.append(len(endpointPoints))
                endpointBuckets.setdefault((bucketX, bucketY), []).append(len(endpointPoints))
                endpointPoints.append(point)
            exactEndpoints[coordinates] = endpointKeys[-1]
        firstKey, secondKey = endpointKeys
        if firstKey == secondKey:
            continue
        segments[(firstKey, secondKey)] = (first, second)
    outgoing = {}
    for edgeKey in segments:
        outgoing.setdefault(edgeKey[0], []).append(edgeKey)
    outlinePath = QtGui.QPainterPath()
    outlinePath.setFillRule(QtCore.Qt.FillRule.WindingFill)
    while segments:
        edgeKey = next(iter(segments))
        first, second = segments.pop(edgeKey)
        points = [first, second]
        startKey = edgeKey[0]
        endKey = edgeKey[1]
        while endKey != startKey:
            nextEdge = next((key for key in outgoing.get(endKey, []) if key in segments), None)
            if nextEdge is None:
                break
            first, second = segments.pop(nextEdge)
            points.append(second)
            endKey = nextEdge[1]
        outlinePath.addPolygon(QtGui.QPolygonF(points))
        outlinePath.closeSubpath()
    return outlinePath


def OriginalBuildWallDimensions(self, walls, boundaryPath, openings = None, cachedBoundary = False,
                        measureCaps = False, blockers = (), cutters = ()):
    selectedIds = {id(obj) for obj, index in self.SelectionEntries()} if hasattr(self, "SelectionEntries") else set()
    selectionKey = frozenset(id(wall) for wall in walls if id(wall) in selectedIds)
    doors = list(self.windows if openings is None else openings)
    wallKey = tuple((id(wall), wall.firstVertex.x(), wall.firstVertex.y(), wall.secondVertex.x(),
                     wall.secondVertex.y(), wall.width, wall.firstMiter, wall.secondMiter) for wall in walls)
    doorKey = tuple((type(door), id(door.parentWall), door.firstFraction, door.secondFraction,
                     (door.hingeAtSecond, door.swingsOutwards) if isinstance(door, BarnDoor) else
                     door.swingsOutwards if type(door) in (Window, Door, SilledWindow, CasementWindow, BifoldDoor) else
                     door.hingeAtSecond if isinstance(door, PocketDoor) else door.panelsFlipped if isinstance(door, SlidingDoor) else
                     (door.depth, door.depthOffset) if isinstance(door, Fireplace) else None) for door in doors)
    origin = self.WorldToViewport(QtCore.QPointF())
    scale = 1 / (self.basePixelsPerMillimeter * self.zoom)
    worldTransform = QtGui.QTransform(scale, 0, 0, -scale, -origin.x() * scale, origin.y() * scale)
    # Accept explicit boundary paths too, while ignoring pan/zoom roundoff.
    if cachedBoundary:
        if self.dimensionBoundaryKey != self.wallGeometryKey:
            self.dimensionBoundaryValues = tuple((round(element.x / self.basePixelsPerMillimeter, 5),
                                                   round(-element.y / self.basePixelsPerMillimeter, 5), element.type)
                                                  for element in (self.wallGeometryPath.elementAt(index)
                                                                  for index in range(self.wallGeometryPath.elementCount())))
            self.dimensionBoundaryKey = self.wallGeometryKey
        boundaryKey = self.dimensionBoundaryValues
    else:
        boundaryKey = []
        for index in range(boundaryPath.elementCount()):
            element = boundaryPath.elementAt(index)
            boundaryKey.append((round((element.x - origin.x()) * scale, 5),
                                round((origin.y() - element.y) * scale, 5), element.type))
    blockerKey = tuple(tuple((point.x(), point.y()) for point in polygon) for polygon in blockers)
    cutterKey = tuple(tuple((point.x(), point.y()) for point in polygon) for polygon in cutters)
    cacheKey = (wallKey, doorKey, tuple(door.measurementFlipped for door in doors),
                tuple(boundaryKey), tuple(sorted(self.measurementSettings.items())),
                measureCaps, blockerKey, cutterKey, selectionKey)
    if cacheKey == self.dimensionCacheKey:
        return self.dimensionCache
    previousKey = self.dimensionCacheKey
    if cachedBoundary and previousKey is not None and not blockers and not cutters and previousKey[1:3] == cacheKey[1:3] and previousKey[4:] == cacheKey[4:]:
        translation = self.WallTranslation(previousKey[0], wallKey)
        if translation is not None and len(previousKey[3]) == len(boundaryKey) and all(
                old[2] == new[2] and abs(new[0] - old[0] - translation.x()) < 1e-4
                and abs(new[1] - old[1] - translation.y()) < 1e-4
                for old, new in zip(previousKey[3], boundaryKey)):
            self.dimensionCache = [(first + translation, second + translation, owners)
                                   for first, second, owners in self.dimensionCache]
            self.dimensionCacheKey = cacheKey
            return self.dimensionCache
    # A boundary has many segments; normalize each candidate wall once,
    # rather than repeating its geometry for every segment during a drag.
    wallAxes = []
    for wall in walls:
        firstX, firstY = wall.firstVertex.x(), wall.firstVertex.y()
        axisX = wall.secondVertex.x() - firstX
        axisY = wall.secondVertex.y() - firstY
        wallLength = math.hypot(axisX, axisY)
        if wallLength >= 0.0001:
            wallAxes.append((wall, firstX, firstY, axisX / wallLength, axisY / wallLength, wallLength, wall.width / 2))
    sizes = sorted(max(wallLength, halfWidth * 2) for wall, firstX, firstY, axisX, axisY, wallLength, halfWidth in wallAxes)
    axisIndex = BoundsIndex(sizes[len(sizes) // 2] if sizes else 1)
    for entry in wallAxes:
        wall, firstX, firstY, axisX, axisY, wallLength, halfWidth = entry
        secondX, secondY = firstX + axisX * wallLength, firstY + axisY * wallLength
        extent = abs(halfWidth)
        bounds = QtCore.QRectF(min(firstX, secondX) - abs(axisY) * extent,
                              min(firstY, secondY) - abs(axisX) * extent,
                              abs(secondX - firstX) + 2 * abs(axisY) * extent,
                              abs(secondY - firstY) + 2 * abs(axisX) * extent)
        axisIndex.Insert(bounds.adjusted(-.01, -.01, .01, .01), entry)
    ownerCache = getattr(self, "dimensionOwnerCache", None)
    if ownerCache is None:
        self.dimensionOwnerCache = ownerCache = {}
    dimensions = []
    for polygon in worldTransform.map(boundaryPath).toSubpathPolygons():
        segments = []
        for index in range(len(polygon) - 1):
            first = polygon[index]
            second = polygon[index + 1]
            direction = second - first
            length = math.hypot(direction.x(), direction.y())
            if length < 0.0001:
                continue
            direction /= length
            if segments and QtCore.QLineF(segments[-1][2], direction).length() < 1e-6:
                segments[-1] = (segments[-1][0], second, direction)
            else:
                segments.append((first, second, direction))
        if len(segments) > 1 and QtCore.QLineF(segments[-1][2], segments[0][2]).length() < 1e-6:
            segments[0] = (segments[-1][0], segments[0][1], segments[0][2])
            segments.pop()
        for first, second, direction in segments:
            owners = []
            midpoint = (first + second) / 2
            firstX, firstY = first.x(), first.y()
            secondX, secondY = second.x(), second.y()
            midpointX, midpointY = midpoint.x(), midpoint.y()
            directionX, directionY = direction.x(), direction.y()
            # The exact owner predicate allows a small angular tolerance.
            # Include its maximum drift along long spans in the broad phase.
            margin = max(.02 + QtCore.QLineF(first, second).length() * 1e-6,
                         16 * max(math.ulp(value) for value in (firstX, firstY, secondX, secondY)))
            spanBounds = QtCore.QRectF(first, second).normalized().adjusted(-margin, -margin, margin, margin)
            candidates = axisIndex.Query(spanBounds)
            ownerKey = (measureCaps, firstX, firstY, secondX, secondY,
                        tuple((id(wall), type(wall), wallX, wallY, axisX, axisY, wallLength, halfWidth)
                              for wall, wallX, wallY, axisX, axisY, wallLength, halfWidth in candidates))
            cached = ownerCache.pop(ownerKey, None)
            if cached is not None:
                owners = list(cached)
            else:
                for wall, wallX, wallY, axisX, axisY, wallLength, halfWidth in candidates:
                    cross = directionX * axisY - directionY * axisX
                    if abs(cross) >= 1e-6:
                        if (measureCaps or isinstance(wall, Pillar)) and abs(directionX * axisX + directionY * axisY) < 1e-6:
                            along = (midpointX - wallX) * axisX + (midpointY - wallY) * axisY
                            across = abs((midpointX - wallX) * axisY - (midpointY - wallY) * axisX)
                            if min(abs(along), abs(along - wallLength)) < .01 and across <= halfWidth + .01:
                                owners.append(wall)
                        continue
                    across = abs((midpointX - wallX) * axisY - (midpointY - wallY) * axisX)
                    if abs(across - halfWidth) < 0.01:
                        firstAlong = (firstX - wallX) * axisX + (firstY - wallY) * axisY
                        secondAlong = (secondX - wallX) * axisX + (secondY - wallY) * axisY
                        if max(firstAlong, secondAlong) > 0 and min(firstAlong, secondAlong) < wallLength:
                            owners.append(wall)
            ownerCache[ownerKey] = tuple(owners)
            # Walls measure long sides; counters also measure exposed end caps.
            if owners:
                if any(id(owner) in selectedIds for owner in owners):
                    dimensions.append((first, second, owners))
                    continue
                # Door jambs split the relevant side. Project onto
                # the exposed span so room corners and wall intersections still clip it.
                spanLength = QtCore.QLineF(first, second).length()
                interruptions = []
                contactSpans = []
                for cutter in cutters:
                    start, end = 0.0, spanLength
                    for index, point in enumerate(cutter):
                        edge = cutter[(index + 1) % len(cutter)] - point
                        edgeLength = math.hypot(edge.x(), edge.y())
                        if edgeLength < 1e-8:
                            continue
                        axis = QtCore.QPointF(-edge.y(), edge.x()) / edgeLength
                        projections = [QtCore.QPointF.dotProduct(vertex, axis) for vertex in cutter]
                        low, high = min(projections) - .01, max(projections) + .01
                        origin = QtCore.QPointF.dotProduct(first, axis)
                        slope = QtCore.QPointF.dotProduct(direction, axis)
                        if abs(slope) < 1e-8:
                            if origin < low or origin > high:
                                end = -1.0
                                break
                        else:
                            bounds = sorted(((low - origin) / slope, (high - origin) / slope))
                            start, end = max(start, bounds[0]), min(end, bounds[1])
                        if end <= start:
                            break
                    if end - start > .02:
                        contactSpans.append((start, end))
                # Adjacent footprint pieces are a single contact span.
                # Their internal seams must not introduce midpoint cuts.
                for start, end in sorted(contactSpans):
                    if interruptions and start <= interruptions[-1][1] + .02:
                        interruptions[-1] = (interruptions[-1][0], max(end, interruptions[-1][1]))
                    else:
                        interruptions.append((start, end))
                for door in doors:
                    isDoor = isinstance(door, (Door, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway))
                    mode = self.measurementSettings["doors" if isDoor else "windows"]
                    if mode == 2 and not isinstance(door, Fireplace):
                        continue
                    if not any(door.parentWall is owner for owner in owners):
                        continue
                    parentDirection = door.parentWall.secondVertex - door.parentWall.firstVertex
                    swingNormal = QtCore.QPointF(-parentDirection.y(), parentDirection.x())
                    if mode == 1 and not isinstance(door, Fireplace) and (not isDoor or isinstance(door, (Door, SlidingDoor, BarnDoor))):
                        flippedSide = door.swingsOutwards if not isinstance(door, SlidingDoor) else door.panelsFlipped
                        if flippedSide:
                            swingNormal = -swingNormal
                        if isinstance(door, BarnDoor):
                            swingNormal = -swingNormal
                        if door.measurementFlipped:
                            swingNormal = -swingNormal
                        # In world coordinates this is opposite the window's crossbar/sill side.
                        if QtCore.QPointF.dotProduct(midpoint - door.parentWall.firstVertex, swingNormal) <= 0:
                            continue
                    openingFirst = door.firstVertex
                    openingSecond = door.secondVertex
                    if isinstance(door, PocketDoor):
                        pocketMidpoint = (openingFirst + openingSecond) / 2
                        if door.hingeAtSecond:
                            openingFirst = pocketMidpoint
                        else:
                            openingSecond = pocketMidpoint
                    firstAlong = QtCore.QPointF.dotProduct(openingFirst - first, direction)
                    secondAlong = QtCore.QPointF.dotProduct(openingSecond - first, direction)
                    start = max(0.0, min(firstAlong, secondAlong))
                    end = min(spanLength, max(firstAlong, secondAlong))
                    if end - start > 0.0001:
                        interruptions.append((start, end))
                cursor = 0.0
                for start, end in sorted(interruptions):
                    if start - cursor > 0.0001:
                        dimensions.append((first + direction * cursor, first + direction * start, owners))
                    openingStart = max(cursor, start)
                    if end - openingStart > 0.0001:
                        dimensionFirst = first + direction * openingStart
                        dimensionSecond = first + direction * end
                        for fireplace in doors:
                            if not isinstance(fireplace, Fireplace) or not any(fireplace.parentWall is owner for owner in owners):
                                continue
                            limits = sorted((QtCore.QPointF.dotProduct(fireplace.firstVertex - first, direction),
                                             QtCore.QPointF.dotProduct(fireplace.secondVertex - first, direction)))
                            if openingStart < limits[0] - .01 or end > limits[1] + .01:
                                continue
                            tangent, normal = fireplace.Axes()
                            wallCenter = (fireplace.firstVertex + fireplace.secondVertex) / 2
                            wallSide = QtCore.QPointF.dotProduct((dimensionFirst + dimensionSecond) / 2 - wallCenter, normal)
                            edge = fireplace.depthOffset + (fireplace.depth / 2 if wallSide > 0 else -fireplace.depth / 2)
                            shift = normal * (edge - wallSide)
                            dimensionFirst += shift
                            dimensionSecond += shift
                            break
                        openingOwners = [opening for opening in doors if any(opening.parentWall is owner for owner in owners)
                                         and min(QtCore.QPointF.dotProduct(opening.firstVertex - first, direction),
                                                 QtCore.QPointF.dotProduct(opening.secondVertex - first, direction)) <= openingStart + .01
                                         and max(QtCore.QPointF.dotProduct(opening.firstVertex - first, direction),
                                                 QtCore.QPointF.dotProduct(opening.secondVertex - first, direction)) >= end - .01]
                        dimensions.append((dimensionFirst, dimensionSecond, openingOwners or owners))
                    cursor = max(cursor, end)
                if spanLength - cursor > 0.0001:
                    dimensions.append((first + direction * cursor, second, owners))
    self.dimensionCacheKey = cacheKey
    if blockers:
        exposedDimensions = []
        for first, second, owners in dimensions:
            if any(id(owner) in selectedIds for owner in owners):
                exposedDimensions.append((first, second, owners))
                continue
            delta = second - first
            length = math.hypot(delta.x(), delta.y())
            direction = delta / length
            coveredSpans = []
            for polygon in blockers:
                if len(polygon) < 3:
                    continue
                start, end = 0.0, length
                # Clip against the oriented footprint, including flush contact.
                for index in range(len(polygon)):
                    edge = polygon[(index + 1) % len(polygon)] - polygon[index]
                    edgeLength = math.hypot(edge.x(), edge.y())
                    if edgeLength < 1e-8:
                        continue
                    axis = QtCore.QPointF(-edge.y(), edge.x()) / edgeLength
                    projections = [QtCore.QPointF.dotProduct(point, axis) for point in polygon]
                    low, high = min(projections) - .01, max(projections) + .01
                    origin = QtCore.QPointF.dotProduct(first, axis)
                    slope = QtCore.QPointF.dotProduct(direction, axis)
                    if abs(slope) < 1e-8:
                        if origin < low or origin > high:
                            end = -1.0
                            break
                    else:
                        bounds = sorted(((low - origin) / slope, (high - origin) / slope))
                        start, end = max(start, bounds[0]), min(end, bounds[1])
                    if end <= start:
                        break
                if end - start > .0001:
                    coveredSpans.append((start, end))
            cursor = 0.0
            for start, end in sorted(coveredSpans):
                if start - cursor > .01:
                    exposedDimensions.append((first + direction * cursor, first + direction * start, owners))
                cursor = max(cursor, end)
            if length - cursor > .01:
                exposedDimensions.append((first + direction * cursor, second, owners))
        dimensions = exposedDimensions
    while len(ownerCache) > max(1024, len(walls) * 8):
        ownerCache.pop(next(iter(ownerCache)))
    self.dimensionCache = dimensions
    return dimensions
