"""Frozen target collection, movement and resize snapping before this pass."""
from planner_app.viewport.snapping import *
from planner_app.viewport.furnishing_handles import *


def SnapMovement(anchors, delta, targets, scale, vertexRange, alignmentEnabled, gridStep,
                 direction = None, distance = math.hypot):
    """Return travel, applied, priority and guides with stable anchor ties.

    Targets are prepared once per movement, retaining the existing thresholds
    for indexed point and ray lookup. The input collections are read-only.
    A backend may supply its distance primitive to retain its floating-point
    tie behavior; all selection policy remains here.
    """
    targetIndex, rayTargets = None, None
    if len(targets) > 32:
        if direction is None:
            targetIndex = PrepareTargetIndex(targets)
        elif len(anchors) >= 3:
            rayTargets = PrepareRayTargets(targets)
    bestKey, guides, priority = None, [], 3
    result = delta
    for anchor in anchors:
        moved = anchor[0] + delta[0], anchor[1] + delta[1]
        snapped, applied, candidatePriority, candidateGuides = SnapPoint(
            moved, targets, scale, vertexRange, alignmentEnabled, gridStep,
            anchor if direction is not None else None, direction, targetIndex, rayTargets)
        if applied:
            key = candidatePriority, distance(moved[0] - snapped[0], moved[1] - snapped[1])
            if bestKey is None or key < bestKey:
                bestKey = key
                result = snapped[0] - anchor[0], snapped[1] - anchor[1]
                priority = candidatePriority
                guides = candidateGuides if priority == 1 else []
    if direction is not None:
        along = max(0.0, result[0] * direction[0] + result[1] * direction[1])
        result = direction[0] * along, direction[1] * along
    return result, bestKey is not None, priority, guides


def SnapResize(north, center, originalWidth, originalLength, width, length, field, sign,
               centered, minimumSize, targets, scale, vertexRange, alignmentEnabled, gridStep,
               distance = math.hypot):
    """Return width, length, applied, priority and guides without changing inputs.

    Targets are the already filtered direct/alignment points, including enabled
    midpoints. A desktop backend may supply its distance primitive for exact
    anchor ties. Corner resizing retains the original aspect ratio.
    """
    northX, northY = north
    eastX, eastY = northY, -northX
    factor = 2 if centered else 1
    if field == "corner":
        eastSign, northSign = sign
        diagonalX = eastX * (eastSign * originalWidth) + northX * (northSign * originalLength)
        diagonalY = eastY * (eastSign * originalWidth) + northY * (northSign * originalLength)
        anchorX = center[0] if centered else center[0] - diagonalX / 2
        anchorY = center[1] if centered else center[1] - diagonalY / 2
        corner = (anchorX + (eastX * (eastSign * width) + northX * (northSign * length)) / factor,
                  anchorY + (eastY * (eastSign * width) + northY * (northSign * length)) / factor)
        diagonalLength = math.hypot(diagonalX, diagonalY)
        snapped, applied, priority, guides = SnapPoint(corner, targets, scale, vertexRange,
            alignmentEnabled, gridStep, (anchorX, anchorY), (diagonalX / diagonalLength, diagonalY / diagonalLength))
        resizeScale = factor * ((snapped[0] - anchorX) * diagonalX + (snapped[1] - anchorY) * diagonalY) / (diagonalX * diagonalX + diagonalY * diagonalY)
        resizeScale = max(minimumSize / min(originalWidth, originalLength), resizeScale)
        return originalWidth * resizeScale, originalLength * resizeScale, applied, priority, guides

    axisX, axisY = north if field == "length" else (eastX, eastY)
    tangentX, tangentY = (eastX, eastY) if field == "length" else north
    size = length if field == "length" else width
    originalSize = originalLength if field == "length" else originalWidth
    halfSpan = (originalWidth if field == "length" else originalLength) / 2
    anchorX = center[0] if centered else center[0] - axisX * (sign * originalSize / 2)
    anchorY = center[1] if centered else center[1] - axisY * (sign * originalSize / 2)
    edgeX = anchorX + axisX * (sign * size / factor)
    edgeY = anchorY + axisY * (sign * size / factor)
    bestKey, bestGuides, priority = None, [], 3
    for offsetX, offsetY in ((0.0, 0.0), (tangentX * halfSpan, tangentY * halfSpan),
                             (-tangentX * halfSpan, -tangentY * halfSpan)):
        point = edgeX + offsetX, edgeY + offsetY
        snapped, applied, priority, guides = SnapPoint(point, targets, scale, vertexRange,
            alignmentEnabled, gridStep, (anchorX + offsetX, anchorY + offsetY), (axisX * sign, axisY * sign))
        if applied:
            snappedSize = factor * sign * (((snapped[0] - anchorX) - offsetX) * axisX + ((snapped[1] - anchorY) - offsetY) * axisY)
            if snappedSize >= 1:
                key = priority, distance(point[0] - snapped[0], point[1] - snapped[1])
                if bestKey is None or key < bestKey:
                    bestKey, bestSize, bestGuides = key, snappedSize, guides
    # A vertex can meet any point of the edge, not just the three anchors.
    for targetX, targetY, direct in targets:
        if not direct:
            continue
        offsetX, offsetY = targetX - edgeX, targetY - edgeY
        if abs(offsetX * tangentX + offsetY * tangentY) > halfSpan + .01:
            continue
        separation = abs(offsetX * axisX + offsetY * axisY)
        snappedSize = factor * sign * ((targetX - anchorX) * axisX + (targetY - anchorY) * axisY)
        if separation * scale < vertexRange and snappedSize >= 1:
            key = 0, separation
            if bestKey is None or key < bestKey:
                bestKey, bestSize, bestGuides = key, snappedSize, []
    if bestKey is not None:
        size, priority = bestSize, bestKey[0]
    # With no accepted candidate the last point probe's priority is retained,
    # including a grid probe that had no eligible intersection with the ray.
    width, length = (width, size) if field == "length" else (size, length)
    return width, length, bestKey is not None, priority, bestGuides


class ReferenceSnapping:
    def SnapVertices(self):
        movingVertices = {(id(wall), vertexIndex) for wall, vertexIndex, originalPosition in self.ActiveAttachments()}
        # A carried footprint moves as one object; endpoint targets can still
        # exclude only the individual vertices being stretched.
        movingIds = {objectId for objectId, vertexIndex in movingVertices}
        for wall in self.walls + self.windows + self.furnishings + self.labels:
            if not self.IsObjectVisible(wall) or isinstance(wall, AngleGuide) and (wall is self.selectedWall and self.dragStart is not None or id(wall) in movingIds):
                continue
            if self.dragStart is not None and isinstance(wall, Window):
                if (wall.parentWall is self.selectedWall
                        or (id(wall.parentWall), 0) in movingVertices
                        or (id(wall.parentWall), 1) in movingVertices):
                    continue
            if isinstance(wall, (Furnishing, Pillar)):
                if wall is not self.selectedWall and id(wall) not in movingIds:
                    yield from (CornerSnapPoint(corner) for corner in self.ObjectCorners(wall))
                continue
            for vertexIndex, vertex in enumerate(ObjectControlPoints(wall)):
                if self.dragStart is not None:
                    if self.connectedEnabled and (id(wall), vertexIndex) in movingVertices:
                        continue
                    if wall is self.selectedWall and (self.selectedVertex is None or vertexIndex == self.selectedVertex):
                        continue
                yield vertex
            if type(wall) is MeasurementGuide and (self.dragStart is None or wall is not self.selectedWall and id(wall) not in movingIds):
                yield from self.GuideDepthEndpoints(wall)

    def StairSnapTargets(self, source = None):
        movingWalls = {id(wall) for wall, vertexIndex, originalPosition in self.ActiveAttachments()}
        if self.groupDrag:
            movingWalls.update(id(obj) for obj, index in self.groupMovedOpenings)
        if self.furnishingHandleDrag is not None:
            movingWalls.add(id(self.furnishingHandleDrag["object"]))
            movingWalls.update(id(state[0]) for state in self.furnishingHandleDrag["members"])
        objects = [obj for obj in self.walls + self.windows + self.furnishings + self.labels
                   if self.IsObjectVisible(obj) and obj is not source and id(obj) not in movingWalls
                   and not (isinstance(obj, Window) and (obj.parentWall is source or id(obj.parentWall) in movingWalls))]
        cacheKey = (self.basePixelsPerMillimeter, tuple((id(obj), obj.firstVertex.x(), obj.firstVertex.y(),
                    obj.secondVertex.x(), obj.secondVertex.y(), obj.width, getattr(obj, "firstMiter", 0),
                    getattr(obj, "secondMiter", 0), (obj.middleVertex.x(), obj.middleVertex.y()) if isinstance(obj, AngleGuide) else None, (obj.depth, obj.depthOffset) if isinstance(obj, Fireplace) else None) for obj in objects))
        if cacheKey == self.footprintSnapTargetsKey:
            return self.footprintSnapTargets
        targets = [corner for obj in objects for corner in self.ObjectCorners(obj)]
        walls = [obj for obj in objects if type(obj) in (Wall, Pillar, Column)]
        if walls:
            # Joined wall faces add the actual inner and outer miter corners.
            for polygon in Paths.Contours(self.ConnectedWallPath(walls)):
                targets.extend(self.ViewportToWorld(vertex) for vertex in polygon)
        counters = [obj for obj in objects if isinstance(obj, Counter)]
        if counters:
            path, dimensions, polygons = self.ConnectedCounterPath(counters, includeMeasurements = False)
            for polygon in Paths.Contours(path):
                targets.extend(self.ViewportToWorld(vertex) for vertex in polygon)
        self.footprintSnapTargetsKey = cacheKey
        self.footprintSnapTargets = list({(round(vertex.x(), 6), round(vertex.y(), 6)): CornerSnapPoint(vertex) for vertex in targets}.values())
        return self.footprintSnapTargets

    def SnapMidpoints(self):
        movingWalls = {id(wall) for wall, vertexIndex, originalPosition in self.ActiveAttachments()}
        if self.furnishingHandleDrag is not None:
            movingWalls.add(id(self.furnishingHandleDrag["object"]))
            movingWalls.update(id(state[0]) for state in self.furnishingHandleDrag["members"])
        for wall in self.walls + self.windows + self.furnishings + self.labels:
            if not self.IsObjectVisible(wall) or isinstance(wall, AngleGuide):
                continue
            if self.groupDrag and any(wall is obj for obj, index in self.groupMovedOpenings):
                continue
            if self.dragStart is not None:
                if wall is self.selectedWall or id(wall) in movingWalls:
                    continue
                if isinstance(wall, Window) and (wall.parentWall is self.selectedWall or id(wall.parentWall) in movingWalls):
                    continue
            yield (wall.firstVertex + wall.secondVertex) / 2

    def SnapObjectMovement(self, anchors, delta, modifiers, snapTargets = None, travelDirection = None):
        constrained = self.controlHeld or bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier)
        axes = None
        if travelDirection is None and constrained:
            if self.dragStart is not None:
                self.axisConstraintOrigin = self.ViewportToWorld(self.dragStart)
            if self.localTransforms and self.dragStart is not None and self.selectedWall is not None:
                axes = tuple((axis.x(), axis.y()) for axis in self.TranslationAxes())
        delta, direction = ConstrainMovement((delta.x(), delta.y()),
            (travelDirection.x(), travelDirection.y()) if travelDirection is not None else None, constrained, axes)
        if self.snapEnabled == bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            # No target collection or anchor copies on the disabled path.
            delta, self.snapApplied, self.snapPriority, self.alignmentGuides = SnapMovement(
                (), delta, (), 1, 0, False, None, direction)
            return QtCore.QPointF(*delta)
        numericTargets = self.NumericSnapTargets(snapTargets)
        if self.midpointSnapEnabled:
            numericTargets.extend((vertex.x(), vertex.y(), True) for vertex in self.SnapMidpoints())
        gridStep = self.GridSteps()[1] if self.gridSnapEnabled and anchors else None
        delta, self.snapApplied, self.snapPriority, self.alignmentGuides = SnapMovement(
            [(anchor.x(), anchor.y()) for anchor in anchors], delta, numericTargets,
            self.basePixelsPerMillimeter * self.zoom, self.vertexSnapRange,
            self.alignmentSnapEnabled, gridStep, direction, MovementSnapDistance)
        return QtCore.QPointF(*delta)



class ReferenceHandles:
    def SnapFurnishingResize(self, state, width, length, modifiers):
        self.snapApplied = False
        self.snapPriority = 3
        self.alignmentGuides = []
        if self.snapEnabled == bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            return width, length
        targets = self.NumericSnapTargets(self.StairSnapTargets(state.get("fireplace") or state["object"]))
        if self.midpointSnapEnabled:
            targets.extend((vertex.x(), vertex.y(), True) for vertex in self.SnapMidpoints())
        north, center = state["north"], state["center"]
        width, length, self.snapApplied, self.snapPriority, self.alignmentGuides = SnapResize(
            (north.x(), north.y()), (center.x(), center.y()), state["width"], state["length"],
            width, length, *state["handle"][1:3], state.get("centeredResize", False),
            .001 if isinstance(state["object"], Label) else 1, targets,
            self.basePixelsPerMillimeter * self.zoom, self.vertexSnapRange, self.alignmentSnapEnabled,
            self.GridSteps()[1] if self.gridSnapEnabled else None, MovementSnapDistance)
        return width, length


from planner_app.viewport.widget import DrawingViewport

class ReferenceViewport(ReferenceSnapping, ReferenceHandles, DrawingViewport):
    pass
