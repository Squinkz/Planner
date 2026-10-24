"""Frozen opening/snapping reference before the placement pass."""

import math

from bisect import bisect_left, bisect_right

from PySide6 import QtCore, QtGui, QtWidgets

from planner_app.models import *

from planner_app.units import imperialModes
from planner_app.geometry.attachments import OpeningWithinWall

from planner_app.viewport.geometry import CollisionPass
from planner_app.geometry.collisions import JunctionReach

from planner_app.geometry.opening_placement import ProjectOpening, OpeningGap, BlockedOpeningIntervals, OpeningPlacementSpan

class ReferencePlacement:

    def FindFireplacePlacement(self, position, modifiers, source = None, initialSize = None):
        worldPosition = self.ViewportToWorld(position)
        width = initialSize[0] if initialSize is not None else source.width if source is not None else self.miscDefaultSizes["Fireplace"] * 10
        fireplace = self.FindWindowPlacement(position, width,
            source.parentWall if source is not None else None, Fireplace, source, modifiers)
        if fireplace is None and source is not None:
            direction, normal = source.Axes()
            across = QtCore.QPointF.dotProduct(worldPosition - source.parentWall.firstVertex, normal)
            reach = source.depth / 2 + abs(source.depthOffset) + 24 / (self.basePixelsPerMillimeter * self.zoom)
            if abs(across) <= reach:
                searchPosition = self.WorldToViewport(worldPosition - normal * across)
                fireplace = self.FindWindowPlacement(searchPosition, width, source.parentWall, Fireplace, source, modifiers)
        if fireplace is None:
            return None
        if type(fireplace.parentWall) is not Wall:
            return None
        if source is not None:
            fireplace.depth = initialSize[1] if initialSize is not None else source.depth
            fireplace.swingsOutwards = source.swingsOutwards
            fireplace.material = source.material
        direction, normal = fireplace.Axes()
        offset = QtCore.QPointF.dotProduct(worldPosition - fireplace.parentWall.firstVertex, normal)
        limit = (fireplace.depth - fireplace.parentWall.width) / 2
        offset = max(-limit, min(limit, offset))
        fireplace.depthOffset = offset
        center = (fireplace.firstVertex + fireplace.secondVertex) / 2 + normal * offset
        originalFraction = fireplace.centerFraction
        placements = [(3, float("inf"), QtCore.QPointF(), [])]
        snapTargets = self.StairSnapTargets(source)
        # Snap the complete footprint, including both front/back faces, rather
        # than the two opening endpoints on the parent wall's centerline.
        for anchor in self.ObjectCorners(fireplace) + [center]:
            snapped = self.SnapPosition(anchor, modifiers, snapTargets = snapTargets)
            if self.snapApplied:
                correction = snapped - anchor
                placements.append((self.snapPriority, QtCore.QLineF(anchor, snapped).length(),
                                   correction, list(self.alignmentGuides)))
        offsetSnap = None
        if self.alignmentSnapEnabled and self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            target = min((-limit, 0.0, limit), key = lambda target: abs(target - offset))
            if abs(target - offset) * self.basePixelsPerMillimeter * self.zoom <= self.vertexSnapRange:
                offsetSnap = target
        wallLength = QtCore.QLineF(fireplace.parentWall.firstVertex, fireplace.parentWall.secondVertex).length()
        halfSpan = fireplace.length / (2 * wallLength)
        self.alignmentGuides = []
        self.snapApplied = False
        for priority, distance, correction, guides in sorted(placements, key = lambda candidate: candidate[:2]):
            fraction = originalFraction + QtCore.QPointF.dotProduct(correction, direction) / wallLength
            depthOffset = offset + QtCore.QPointF.dotProduct(correction, normal)
            # Center/flush depth snapping must not compete with an independent
            # sideways alignment (a zero depth correction would always win).
            applyOffsetSnap = offsetSnap is not None and abs(depthOffset - offset) < 1e-8
            if applyOffsetSnap:
                depthOffset = offsetSnap
            if not halfSpan - 1e-8 <= fraction <= 1 - halfSpan + 1e-8 or abs(depthOffset) > limit + 1e-8:
                continue
            fireplace.centerFraction = max(halfSpan, min(1 - halfSpan, fraction))
            fireplace.depthOffset = depthOffset
            if not self.OpeningFits(fireplace, source):
                continue
            self.alignmentGuides = guides
            self.snapApplied = priority < 3 or applyOffsetSnap
            self.snapPriority = min(priority, 1) if applyOffsetSnap else priority
            break
        else:
            return None
        if source is None:
            fireplace.swingsOutwards = QtCore.QPointF.dotProduct(worldPosition - fireplace.parentWall.firstVertex, normal) > 0
        return fireplace

    def OpeningFits(self, opening, exclude = None):
        parentLength = QtCore.QLineF(opening.parentWall.firstVertex, opening.parentWall.secondVertex).length()
        if not OpeningWithinWall(parentLength, opening.length, opening.centerFraction):
            return False
        if any(type(wall) in (Wall, Pillar, Column) and wall is not opening.parentWall and
               self.JoinedObjectsOverlap(opening, wall, contactTolerance = 1.0) for wall in self.walls):
            return False
        return not any(other is not exclude and other is not opening and self.OpeningsOverlap(opening, other)
                       for other in self.windows)

    def FindWindowPlacement(self, position, length = None, preferredWall = None, openingType = Window, exclude = None, modifiers = None):
        if length is None:
            length = self.openingDefaultSizes[openingType.__name__] * (20 if openingType in (SlidingDoor, PocketDoor, BarnDoor) else 10)
        if modifiers is None:
            modifiers = QtWidgets.QApplication.keyboardModifiers()
        worldPosition = self.ViewportToWorld(position)
        nearest = None
        nearestGuides = []
        nearestDistance = float("inf")
        solidWalls = [wall for wall in self.walls if type(wall) in (Wall, Pillar, Column)]
        footprintKey = (self.basePixelsPerMillimeter, tuple((id(wall), wall.firstVertex.x(), wall.firstVertex.y(),
                        wall.secondVertex.x(), wall.secondVertex.y(), wall.width, wall.firstMiter, wall.secondMiter)
                        for wall in solidWalls))
        if footprintKey != getattr(self, "openingFootprintKey", None):
            from planner_app.viewport.geometry import FootprintGeometry
            workspace = getattr(self, "openingFootprintWorkspace", None)
            if workspace is None:
                workspace = FootprintGeometry(self.basePixelsPerMillimeter)
                self.openingFootprintWorkspace = workspace
            workspace.basePixelsPerMillimeter = self.basePixelsPerMillimeter
            workspace.ConnectedWallPath(solidWalls, traceContours = False)
            transform = QtGui.QTransform().scale(1 / self.basePixelsPerMillimeter, -1 / self.basePixelsPerMillimeter)
            # Include raw rectangles as well as joined geometry, matching the
            # two collision checks used by OpeningFits.
            self.openingFootprints = [(owner, transform.map(polygon)) for owner, polygon in workspace.wallFillPolygons]
            self.openingFootprints.extend((wall, QtGui.QPolygonF(self.ObjectFootprint(wall)[1])) for wall in solidWalls)
            self.openingFootprintKey = footprintKey
        prepared = getattr(self, "openingPlacementPolygons", None)
        if prepared is None or prepared[0] is not self.openingFootprints:
            prepared = (self.openingFootprints, [(owner, polygon.boundingRect(), tuple((point.x(), point.y()) for point in polygon))
                                               for owner, polygon in self.openingFootprints])
            self.openingPlacementPolygons = prepared
        preparedPolygons = prepared[1]
        walls = ([preferredWall] + [wall for wall in reversed(self.walls) if wall is not preferredWall]
                 if preferredWall is not None else reversed(self.walls))
        for wall in walls:
            if type(wall) is not Wall or not self.IsObjectVisible(wall):
                continue
            projection = ProjectOpening((wall.firstVertex.x(), wall.firstVertex.y()),
                (wall.secondVertex.x(), wall.secondVertex.y()), (worldPosition.x(), worldPosition.y()))
            if projection is None:
                continue
            numericDirection, lengthSquared, fraction, numericProjected = projection
            direction, projected = QtCore.QPointF(*numericDirection), QtCore.QPointF(*numericProjected)
            distance = QtCore.QLineF(position, self.WorldToViewport(projected)).length()
            reach = wall.width * self.basePixelsPerMillimeter * self.zoom / 2 + 24
            if distance <= reach and distance < nearestDistance:
                parentLength = math.sqrt(lengthSquared)
                gapStart, gapEnd = OpeningGap(fraction,
                    ((other.firstFraction, other.secondFraction) for other in self.windows
                     if other is not exclude and other.parentWall is wall))
                if (gapEnd - gapStart) * parentLength < 1.0:
                    continue
                parentCorners = self.ObjectCorners(wall)
                parentBounds = QtGui.QPolygonF(parentCorners).boundingRect()
                blocked = BlockedOpeningIntervals([(point.x(), point.y()) for point in parentCorners],
                    (wall.firstVertex.x(), wall.firstVertex.y()), numericDirection, lengthSquared,
                    (polygon for owner, bounds, polygon in preparedPolygons if owner is not wall and parentBounds.intersects(bounds)))
                gapStart, gapEnd = OpeningGap(fraction, blocked, gapStart, gapEnd)
                if (gapEnd - gapStart) * parentLength < 1.0:
                    continue
                span, minimumCenter, maximumCenter, center = OpeningPlacementSpan(length, parentLength, fraction, gapStart, gapEnd)
                midpoint = wall.firstVertex + direction * center
                anchors = (midpoint, midpoint - direction * (span / 2), midpoint + direction * (span / 2))
                # A raw placement is a fallback, not a zero-distance snap target.
                placements = [(3, float("inf"), openingType(wall, center - span / 2, center + span / 2), [])]
                for anchor in (() if openingType is Fireplace else anchors):
                    snapped = self.SnapPosition(anchor, modifiers, wall.firstVertex, direction / parentLength)
                    if not self.snapApplied:
                        continue
                    snappedCenter = center + QtCore.QPointF.dotProduct(snapped - anchor, direction) / lengthSquared
                    if snappedCenter < minimumCenter - 1e-8 or snappedCenter > maximumCenter + 1e-8:
                        continue
                    snappedCenter = max(minimumCenter, min(maximumCenter, snappedCenter))
                    candidate = openingType(wall, snappedCenter - span / 2, snappedCenter + span / 2)
                    correctionDistance = QtCore.QLineF(self.WorldToViewport(anchor), self.WorldToViewport(snapped)).length()
                    placements.append((self.snapPriority, correctionDistance, candidate, self.alignmentGuides))
                for priority, correctionDistance, candidate, guides in sorted(placements, key = lambda placement: placement[:2]):
                    if self.OpeningFits(candidate, exclude):
                        nearest = candidate
                        nearestGuides = guides
                        nearestDistance = distance
                        break
        self.alignmentGuides = nearestGuides
        return nearest

    def OrientDoor(self, door, position):
        direction = door.secondVertex - door.firstVertex
        length = math.hypot(direction.x(), direction.y())
        if length < 1e-10:
            return
        direction /= length
        offset = self.ViewportToWorld(position) - (door.firstVertex + door.secondVertex) / 2
        along = QtCore.QPointF.dotProduct(offset, direction)
        across = QtCore.QPointF.dotProduct(offset, QtCore.QPointF(-direction.y(), direction.x()))
        # A small axis dead zone avoids flickering when the pointer is on a divider.
        pixelsPerMillimeter = self.basePixelsPerMillimeter * self.zoom
        if isinstance(door, (Door, SlidingDoor, PocketDoor, CasementWindow)) and abs(along) * pixelsPerMillimeter > 2:
            door.hingeAtSecond = along < 0 if isinstance(door, SlidingDoor) else along > 0
        if abs(across) * pixelsPerMillimeter > 2:
            if isinstance(door, SlidingDoor):
                door.panelsFlipped = across < 0
            elif type(door) in (Window, SilledWindow, CasementWindow):
                door.swingsOutwards = across > 0
            elif isinstance(door, (Door, BarnDoor, BifoldDoor)):
                door.swingsOutwards = across < 0

class ReferenceSnapping:

    def GridSteps(self, pixelsPerMillimeter = None):
        # Rendering and snapping share the same visible grid interval.
        if pixelsPerMillimeter is None:
            pixelsPerMillimeter = self.basePixelsPerMillimeter * self.zoom
        minimumStep = 90.0 / pixelsPerMillimeter
        if self.unitsMode in imperialModes:
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

    def SnapPosition(self, worldPosition, modifiers, angleAnchor = None, angleDirection = None, snapTargets = None,
                     alignmentTargets = None, preparedTargets = None, preparedTargetIndex = None):
        self.alignmentGuides = []
        self.snapApplied = False
        self.snapPriority = 3
        altHeld = bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier)
        if self.snapEnabled == altHeld:
            return worldPosition
        nearestVertex = None
        nearestDistance = self.vertexSnapRange
        alignments = {}
        alignmentRange = 20.0
        # Distances need only the view scale: origin, pan and the inverted Y
        # axis cancel out. Group movement shares this target data across anchors.
        scale = self.basePixelsPerMillimeter * self.zoom
        positionX, positionY = worldPosition.x(), worldPosition.y()
        if preparedTargets is None:
            targets = [(vertex, self.vertexSnapEnabled) for vertex in (self.SnapVertices() if snapTargets is None else snapTargets)]
            if alignmentTargets is not None:
                targets.extend((vertex, False) for vertex in alignmentTargets)
            if self.midpointSnapEnabled:
                targets.extend((midpoint, True) for midpoint in self.SnapMidpoints())
            preparedTargets = [(vertex.x(), vertex.y(), vertex, directSnap) for vertex, directSnap in targets]
        nearbyTargets = preparedTargets
        if preparedTargetIndex is not None and angleAnchor is None:
            # A snap can only win within the vertex radius or an alignment strip.
            # Preserve original target order so equal-distance ties stay unchanged.
            xValues, xIndices, yValues, yIndices = preparedTargetIndex
            margin = max(self.vertexSnapRange, alignmentRange) / scale
            nearbyIndices = set(xIndices[bisect_left(xValues, positionX - margin):bisect_right(xValues, positionX + margin)])
            if self.alignmentSnapEnabled:
                nearbyIndices.update(yIndices[bisect_left(yValues, positionY - margin):bisect_right(yValues, positionY + margin)])
            nearbyTargets = [preparedTargets[index] for index in sorted(nearbyIndices)]
        for vertexX, vertexY, vertex, directSnap in nearbyTargets:
            distance = math.hypot(positionX - vertexX, positionY - vertexY) * scale
            onAngleLine = True
            if angleAnchor is not None:
                offset = vertex - angleAnchor
                onAngleLine = abs(offset.x() * angleDirection.y() - offset.y() * angleDirection.x()) <= 0.01
                onAngleLine = onAngleLine and QtCore.QPointF.dotProduct(offset, angleDirection) >= 0
            if directSnap and onAngleLine and distance < nearestDistance:
                nearestVertex = vertex
                nearestDistance = distance
            if self.alignmentSnapEnabled:
                for axis, coordinate, pixelDistance in (
                        (0, vertexX, abs(positionX - vertexX) * scale),
                        (1, vertexY, abs(positionY - vertexY) * scale)):
                    if angleAnchor is not None:
                        component = angleDirection.x() if axis == 0 else angleDirection.y()
                        if abs(component) < 1e-10:
                            continue
                        anchorCoordinate = angleAnchor.x() if axis == 0 else angleAnchor.y()
                        along = (coordinate - anchorCoordinate) / component
                        if along < 0:
                            continue
                        intersection = angleAnchor + angleDirection * along
                        pixelDistance = math.hypot(positionX - intersection.x(), positionY - intersection.y()) * scale
                    if pixelDistance < alignments.get(axis, (None, alignmentRange, None))[1]:
                        alignments[axis] = (coordinate, pixelDistance, intersection if angleAnchor is not None else None)
        if nearestVertex is not None:
            self.snapApplied = True
            self.snapPriority = 0
            return QtCore.QPointF(nearestVertex)
        snappedPosition = QtCore.QPointF(worldPosition)
        if self.gridSnapEnabled:
            self.snapPriority = 2
            majorStep, minorStep = self.GridSteps()
            if angleAnchor is None:
                self.snapApplied = True
                snappedPosition = QtCore.QPointF(round(worldPosition.x() / minorStep) * minorStep,
                                                round(worldPosition.y() / minorStep) * minorStep)
            else:
                # Snap to the nearest grid-line crossing along the constrained ray.
                candidates = []
                for coordinate, anchorCoordinate, component in (
                        (worldPosition.x(), angleAnchor.x(), angleDirection.x()),
                        (worldPosition.y(), angleAnchor.y(), angleDirection.y())):
                    if abs(component) > 1e-10:
                        along = (round(coordinate / minorStep) * minorStep - anchorCoordinate) / component
                        if along >= 0:
                            candidates.append(angleAnchor + angleDirection * along)
                if candidates:
                    self.snapApplied = True
                    snappedPosition = min(candidates, key = lambda candidate: QtCore.QLineF(worldPosition, candidate).length())
        if alignments:
            self.snapApplied = True
            self.snapPriority = 1
            if angleAnchor is not None:
                # Keep angle and wall constraints intact. Multiple guides are valid
                # only if their coordinate lines meet at this point on the constraint.
                snappedPosition = min(alignments.values(), key = lambda target: target[1])[2]
                self.alignmentGuides = [(axis, target[0]) for axis, target in sorted(alignments.items())
                                        if abs((snappedPosition.x() if axis == 0 else snappedPosition.y()) - target[0]) <= 0.01]
            else:
                for axis, (coordinate, distance, intersection) in sorted(alignments.items()):
                    if axis == 0:
                        snappedPosition.setX(coordinate)
                    else:
                        snappedPosition.setY(coordinate)
                    self.alignmentGuides.append((axis, coordinate))
        return snappedPosition

    def SnapObjectMovement(self, anchors, delta, modifiers, snapTargets = None, travelDirection = None):
        if self.controlHeld:
            modifiers |= QtCore.Qt.KeyboardModifier.ControlModifier
        direction = travelDirection
        if direction is not None:
            delta = direction * QtCore.QPointF.dotProduct(delta, direction)
            if QtCore.QPointF.dotProduct(delta, direction) < 0:
                direction = -direction
        elif modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            if self.dragStart is not None:
                self.axisConstraintOrigin = self.ViewportToWorld(self.dragStart)
            if self.localTransforms and self.dragStart is not None and self.selectedWall is not None:
                axes = self.TranslationAxes()
                direction = max(axes, key = lambda axis: abs(QtCore.QPointF.dotProduct(delta, axis)))
                if QtCore.QPointF.dotProduct(delta, direction) < 0:
                    direction = -direction
            elif abs(delta.x()) >= abs(delta.y()):
                direction = QtCore.QPointF(-1 if delta.x() < 0 else 1, 0)
            else:
                direction = QtCore.QPointF(0, -1 if delta.y() < 0 else 1)
            delta = direction * QtCore.QPointF.dotProduct(delta, direction)
        preparedTargets = []
        if self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            targets = self.SnapVertices() if snapTargets is None else snapTargets
            preparedTargets = [(vertex.x(), vertex.y(), vertex, self.vertexSnapEnabled) for vertex in targets]
            if self.midpointSnapEnabled:
                preparedTargets.extend((vertex.x(), vertex.y(), vertex, True) for vertex in self.SnapMidpoints())
        candidates = []
        preparedTargetIndex = None
        if direction is None and len(preparedTargets) > 32:
            orderedX = sorted((target[0], index) for index, target in enumerate(preparedTargets))
            orderedY = sorted((target[1], index) for index, target in enumerate(preparedTargets))
            preparedTargetIndex = ([value for value, index in orderedX], [index for value, index in orderedX],
                                   [value for value, index in orderedY], [index for value, index in orderedY])
        for anchor in anchors:
            moved = anchor + delta
            snapped = self.SnapPosition(moved, modifiers, anchor if direction is not None else None,
                                        direction, snapTargets = snapTargets, preparedTargets = preparedTargets,
                                        preparedTargetIndex = preparedTargetIndex)
            if self.snapApplied:
                candidates.append((self.snapPriority, QtCore.QLineF(moved, snapped).length(),
                                   snapped - anchor, list(self.alignmentGuides)))
        self.alignmentGuides = []
        self.snapApplied = bool(candidates)
        self.snapPriority = 3
        if candidates:
            priority, distance, delta, guides = min(candidates, key = lambda candidate: candidate[:2])
            self.snapPriority = priority
            self.alignmentGuides = guides if priority == 1 else []
        if direction is not None:
            # Enforce the movement line after choosing a snap, independently of
            # the snapping calculation. Snapping can only change travel distance.
            delta = direction * max(0.0, QtCore.QPointF.dotProduct(delta, direction))
        return delta

class ReferenceGeometry:
    def JoinedObjectBounds(self, obj, excludedWalls = ()):
        """Conservative world bounds including arbitrary-length miter joins."""
        batch = getattr(self, "collisionPassCache", None)
        key = (id(obj), frozenset(excludedWalls))
        if batch is not None and key in batch.get("joinedBounds", {}):
            return batch["joinedBounds"][key]
        bounds = self.ObjectFootprint(obj)[0]
        if type(obj) in (Wall, Stair, Counter, Railing):
            category = type(obj)
            members = [wall for wall in self.walls if type(wall) is category and id(wall) not in excludedWalls and wall is not obj]
            for vertex, opposite, miter in ((obj.firstVertex, obj.secondVertex, obj.firstMiter),
                                              (obj.secondVertex, obj.firstVertex, obj.secondMiter)):
                delta = opposite - vertex
                length = math.hypot(delta.x(), delta.y())
                if length < 1e-10:
                    continue
                rays = [(delta / length, obj.width / 2, miter)]
                for other in members:
                    for endpoint, far, otherMiter in ((other.firstVertex, other.secondVertex, other.firstMiter),
                                                       (other.secondVertex, other.firstVertex, other.secondMiter)):
                        if QtCore.QLineF(vertex, endpoint).length() > .02000001:
                            continue
                        direction = far - endpoint
                        distance = math.hypot(direction.x(), direction.y())
                        if distance > 1e-10:
                            rays.append((direction / distance, other.width / 2, otherMiter))
                if len(rays) == 1:
                    continue
                radius = JunctionReach([(direction.x(), direction.y(), width, miter)
                                        for direction, width, miter in rays], self.basePixelsPerMillimeter)
                bounds = bounds.united(QtCore.QRectF(vertex.x() - radius, vertex.y() - radius, 2 * radius, 2 * radius))
        if batch is not None:
            batch.setdefault("joinedBounds", {})[key] = bounds
        return bounds
