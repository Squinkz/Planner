"""Frozen junction/tracing implementation before the numeric extraction."""
import math
from PySide6 import QtCore, QtGui


class ReferenceGeometry:
    def BuildWallJunction(self, jointVertex, rays, jointMiters):
        """Construct one endpoint junction; distant wall edits reuse its result."""
        geometryScale = self.basePixelsPerMillimeter
        polygons, materialJoins, materialTransitions = [], [], []
        materialCuts = {id(owner): [] for direction, width, owner in rays}
        joint = QtCore.QPointF(jointVertex.x(), -jointVertex.y()) * geometryScale
        rays.sort(key = lambda ray: math.atan2(ray[0].y(), ray[0].x()))
        for rayIndex, (firstDirection, firstHalfWidth, firstOwner) in enumerate(rays):
            secondDirection, secondHalfWidth, secondOwner = rays[(rayIndex + 1) % len(rays)]
            cross = firstDirection.x() * secondDirection.y() - firstDirection.y() * secondDirection.x()
            if abs(cross) < 1e-6:
                dot = firstDirection.x() * secondDirection.x() + firstDirection.y() * secondDirection.y()
                if dot < 0:
                    # Weld opposing collinear caps with a subpixel overlap.
                    # This also closes floating-point gaps at angled joins.
                    normal = QtCore.QPointF(-firstDirection.y(), firstDirection.x()) * min(firstHalfWidth, secondHalfWidth)
                    overlap = firstDirection * max(0.0001, 0.01 * geometryScale)
                    polygons.append(QtGui.QPolygonF([joint + normal + overlap, joint - normal + overlap,
                                                    joint - normal - overlap, joint + normal - overlap]))
                    materialJoins.append((firstOwner, QtGui.QPolygonF([joint + normal, joint - normal,
                                                                                  joint - normal + overlap, joint + normal + overlap])))
                    materialJoins.append((secondOwner, QtGui.QPolygonF([joint + normal, joint - normal,
                                                                                   joint - normal - overlap, joint + normal - overlap])))
                    if len(rays) > 2 and abs(firstHalfWidth - secondHalfWidth) > 1e-6:
                        # At an unequal-width T, place the width transition at
                        # the branch's face instead of leaving a notch at the center.
                        thinDirection = firstDirection if firstHalfWidth < secondHalfWidth else secondDirection
                        branches = [(direction, halfWidth) for direction, halfWidth, owner in rays
                                    if abs(thinDirection.x() * direction.y() - thinDirection.y() * direction.x()) > 1e-6]
                        branchDirection, branchHalfWidth = max(branches, key = lambda ray: QtCore.QPointF.dotProduct(thinDirection, ray[0]))
                        branchNormal = QtCore.QPointF(-branchDirection.y(), branchDirection.x())
                        if QtCore.QPointF.dotProduct(branchNormal, thinDirection) < 0:
                            branchNormal = -branchNormal
                        sectorNormal = QtCore.QPointF(-firstDirection.y(), firstDirection.x())
                        wideOffset = joint + sectorNormal * max(firstHalfWidth, secondHalfWidth)
                        thinOffset = joint + sectorNormal * min(firstHalfWidth, secondHalfWidth)
                        delta = joint + branchNormal * branchHalfWidth - wideOffset
                        denominator = thinDirection.x() * branchDirection.y() - thinDirection.y() * branchDirection.x()
                        extension = (delta.x() * branchDirection.y() - delta.y() * branchDirection.x()) / denominator
                        extension = max(0.0, extension) * max(jointMiters)
                        if extension > 1e-6:
                            polygons.append(QtGui.QPolygonF([wideOffset, wideOffset + thinDirection * extension,
                                                            thinOffset + thinDirection * extension, thinOffset]))
                            # This width-transition patch belongs entirely to
                            # the wider ray. Neighboring miter cuts would remove
                            # a triangle with no other owner available to fill it.
                            materialTransitions.append((firstOwner if firstHalfWidth > secondHalfWidth else secondOwner, polygons[-1]))
                continue
            firstOffset = joint + QtCore.QPointF(-firstDirection.y(), firstDirection.x()) * firstHalfWidth
            secondOffset = joint - QtCore.QPointF(-secondDirection.y(), secondDirection.x()) * secondHalfWidth
            delta = secondOffset - firstOffset
            distance = (delta.x() * secondDirection.y() - delta.y() * secondDirection.x()) / cross
            intersection = firstOffset + firstDirection * distance
            # Blend the bevel into the complete miter at this shared vertex.
            bevel = (firstOffset + secondOffset) / 2
            localTransition = (QtCore.QPointF.dotProduct(firstDirection, secondDirection) < 0
                    and abs(firstHalfWidth - secondHalfWidth) > 1e-6
                    and QtCore.QLineF(joint, intersection).length() > 4 * max(firstHalfWidth, secondHalfWidth))
            if localTransition:
                # Unequal, nearly straight wall faces intersect far down the
                # wall. Use their local cap transition instead of letting a
                # remote intersection stretch the join and material seam.
                intersection = bevel
            miterPoint = bevel + (intersection - bevel) * max(jointMiters)
            points = [joint, firstOffset, miterPoint, secondOffset]
            polygons.append(QtGui.QPolygonF(points))
            if localTransition:
                # Split the whole transition by the common cap plane;
                # splitting at the bevel first can leave unowned slivers.
                materialJoins.extend(((firstOwner, QtGui.QPolygonF(points)),
                                      (secondOwner, QtGui.QPolygonF(points))))
            else:
                materialJoins.extend(((firstOwner, QtGui.QPolygonF([joint, firstOffset, miterPoint])),
                                      (secondOwner, QtGui.QPolygonF([joint, miterPoint, secondOffset]))))
            # Both adjacent materials meet on the line from the shared
            # centerline vertex to the joined edge intersection.
            boundary = miterPoint - joint
            if localTransition:
                # Keep the wider body intact up to its endpoint cap.
                wideDirection = firstDirection if firstHalfWidth > secondHalfWidth else secondDirection
                boundary = QtCore.QPointF(-wideDirection.y(), wideDirection.x())
            for owner, direction in ((firstOwner, firstDirection), (secondOwner, secondDirection)):
                side = boundary.x() * direction.y() - boundary.y() * direction.x()
                if abs(side) > 1e-10:
                    materialCuts[id(owner)].append((joint, boundary, 1 if side > 0 else -1))
        return polygons, materialJoins, materialTransitions, materialCuts


    def TraceWallBoundary(self, filledPath, joinContours = True, traceKey = None, sourcePolygons = None):
        prepared = ([self.PreparedWallContour(polygon) for polygon in sourcePolygons] if sourcePolygons is not None else
                    [self.PreparedWallContour(polygon, canonical = True) for polygon in filledPath.toSubpathPolygons()])
        prepared = [data for data in prepared if not data[0].isEmpty()]
        if not prepared:
            return QtGui.QPainterPath()
        bounds = [polygon.boundingRect().adjusted(-1e-8, -1e-8, 1e-8, 1e-8) for polygon, contour, edges in prepared]
        parents = list(range(len(prepared)))
        active = []
        # Independent filled regions have independent boundaries. Keep the
        # stationary regions cached when another wall moves or changes shape.
        for index in sorted(range(len(prepared)), key = lambda index: bounds[index].left()):
            active = [other for other in active if bounds[other].right() >= bounds[index].left()]
            for other in active:
                if not bounds[index].intersects(bounds[other]):
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
        for index in range(len(prepared)):
            parent = index
            while parents[parent] != parent:
                parent = parents[parent]
            components.setdefault(parent, []).append(index)
        outline = QtGui.QPainterPath()
        outline.setFillRule(QtCore.Qt.FillRule.WindingFill)
        for indices in components.values():
            key = (joinContours, filledPath.fillRule(),
                   tuple(prepared[index][1] for index in indices))
            component = self.wallBoundaryCache.pop(key, None)
            if component is None:
                path = QtGui.QPainterPath()
                path.setFillRule(filledPath.fillRule())
                for index in indices:
                    path.addPolygon(prepared[index][0])
                    path.closeSubpath()
                component = self.TraceWallComponent(path, joinContours,
                    traceKey = (traceKey, tuple(indices)) if traceKey is not None else None,
                    preparedContours = [prepared[index] for index in indices])
            self.wallBoundaryCache[key] = component
            outline.addPath(component)
        while len(self.wallBoundaryCache) > 128:
            self.wallBoundaryCache.pop(next(iter(self.wallBoundaryCache)))
        return outline


    def TraceWallComponent(self, filledPath, joinContours = True, traceKey = None, preparedContours = None):
        edges = []
        edgeCoordinates = []
        fillContours = []
        if preparedContours is None:
            preparedContours = [self.PreparedWallContour(polygon, canonical = True) for polygon in filledPath.toSubpathPolygons()]
        for polygon, contour, contourEdges in preparedContours:
            edges.extend(contourEdges)
            edgeCoordinates.extend(contour[4])
            fillContours.append(contour)
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
        outlinePath = QtGui.QPainterPath()
        outlinePath.setFillRule(QtCore.Qt.FillRule.WindingFill)
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
            outlinePath.addPolygon(QtGui.QPolygonF(points))
            outlinePath.closeSubpath()
        return outlinePath


