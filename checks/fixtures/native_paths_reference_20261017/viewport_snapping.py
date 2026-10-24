"""Grid, alignment, endpoint and oriented-footprint snapping."""

import math
from planner_app.geometry.snapping import GridIntervals, PrepareTargetIndex, PrepareRayTargets, SnapPoint
from PySide6 import QtCore
from planner_app.models import Furnishing, MeasurementGuide, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, Window, Fireplace
from planner_app.units import imperialModes
from .geometry import CollisionPass


class SnappingMixin:
    def GridSteps(self, pixelsPerMillimeter = None):
        # Rendering and snapping share the same visible grid interval.
        if pixelsPerMillimeter is None:
            pixelsPerMillimeter = self.basePixelsPerMillimeter * self.zoom
        return GridIntervals(pixelsPerMillimeter, self.unitsMode in imperialModes)

    def SnapVertices(self):
        movingVertices = {(id(wall), vertexIndex) for wall, vertexIndex, originalPosition in self.ActiveAttachments()}
        # A carried footprint moves as one object; endpoint targets can still
        # exclude only the individual vertices being stretched.
        movingIds = {objectId for objectId, vertexIndex in movingVertices}
        for wall in self.walls + self.windows + self.furnishings + self.labels:
            if not self.IsObjectVisible(wall):
                continue
            if self.dragStart is not None and isinstance(wall, Window):
                if (wall.parentWall is self.selectedWall
                        or (id(wall.parentWall), 0) in movingVertices
                        or (id(wall.parentWall), 1) in movingVertices):
                    continue
            if isinstance(wall, (Furnishing, Pillar)):
                if wall is not self.selectedWall and id(wall) not in movingIds:
                    yield from self.ObjectCorners(wall)
                continue
            for vertexIndex, vertex in enumerate((wall.firstVertex, wall.secondVertex)):
                if self.dragStart is not None:
                    if self.connectedEnabled and (id(wall), vertexIndex) in movingVertices:
                        continue
                    if wall is self.selectedWall and (self.selectedVertex is None or vertexIndex == self.selectedVertex):
                        continue
                yield vertex

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
                    obj.secondVertex.x(), obj.secondVertex.y(), obj.width, getattr(obj, "firstMiter", 1),
                    getattr(obj, "secondMiter", 1), (obj.depth, obj.depthOffset) if isinstance(obj, Fireplace) else None) for obj in objects))
        if cacheKey == self.footprintSnapTargetsKey:
            return self.footprintSnapTargets
        targets = [corner for obj in objects for corner in self.ObjectCorners(obj)]
        walls = [obj for obj in objects if type(obj) in (Wall, Pillar, Column)]
        if walls:
            # Joined wall faces add the actual inner and outer miter corners.
            for polygon in self.ConnectedWallPath(walls).toSubpathPolygons():
                targets.extend(self.ViewportToWorld(vertex) for vertex in polygon)
        counters = [obj for obj in objects if isinstance(obj, Counter)]
        if counters:
            path, dimensions, polygons = self.ConnectedCounterPath(counters, includeMeasurements = False)
            for polygon in path.toSubpathPolygons():
                targets.extend(self.ViewportToWorld(vertex) for vertex in polygon)
        self.footprintSnapTargetsKey = cacheKey
        self.footprintSnapTargets = list({(round(vertex.x(), 6), round(vertex.y(), 6)): vertex for vertex in targets}.values())
        return self.footprintSnapTargets

    @CollisionPass
    def SnapStairVertex(self, position, opposite, stair, modifiers):
        constraintOrigin = opposite
        if (self.dragStart is not None and self.selectedVertex is not None
                and self.vertexAxisFromDragged and self.dragVertices is not None
                and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier):
            constraintOrigin = self.dragVertices[self.selectedVertex]
        # The frame orientation stays fixed, but the nearest ray is chosen
        # from the cursor relative to whichever endpoint is now the origin.
        direction = position - constraintOrigin
        length = math.hypot(direction.x(), direction.y())
        if length < 1e-10:
            if modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
                self.axisConstraintOrigin = QtCore.QPointF(constraintOrigin)
            return position
        angleLocked = bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier)
        if angleLocked:
            angle = self.ConstrainedVertexAngle(direction)
            direction = QtCore.QPointF(math.cos(angle), math.sin(angle))
            position = constraintOrigin + direction * length
            self.axisConstraintOrigin = QtCore.QPointF(constraintOrigin)
            self.axisConstraintDirection = direction
        else:
            direction /= length
        if self.snapEnabled == bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            self.alignmentGuides = []
            self.snapApplied = False
            return position
        snapTargets = self.StairSnapTargets(stair)
        movingVertices = {(id(wall), index) for wall, index, originalPosition in self.ActiveAttachments()}
        if isinstance(stair, (Arrow, MeasurementGuide)):
            targets = [vertex for other in self.walls if type(other) is type(stair) and other is not stair and self.IsObjectVisible(other)
                       for index, vertex in enumerate((other.firstVertex, other.secondVertex))
                       if (id(other), index) not in movingVertices]
            if self.vertexSnapEnabled:
                eligible = [vertex for vertex in targets if not angleLocked or
                            (abs((vertex - constraintOrigin).x() * direction.y() - (vertex - constraintOrigin).y() * direction.x()) <= .01
                             and QtCore.QPointF.dotProduct(vertex - constraintOrigin, direction) >= 0)]
                nearest = min(eligible, key = lambda vertex: QtCore.QLineF(position, vertex).length(), default = None)
                if nearest is not None and QtCore.QLineF(position, nearest).length() * self.basePixelsPerMillimeter * self.zoom < self.vertexSnapRange:
                    self.alignmentGuides = []
                    self.snapApplied = True
                    self.snapPriority = 0
                    return QtCore.QPointF(nearest)
            return self.SnapPosition(position, modifiers, constraintOrigin if angleLocked else None,
                                     direction if angleLocked else None, snapTargets = targets + snapTargets,
                                     alignmentTargets = [opposite])
        joinClass = Railing if isinstance(stair, Railing) else Counter if isinstance(stair, Counter) else Stair if isinstance(stair, Stair) else Wall
        # Same-class runs join at either control endpoint. Other object classes
        # continue to supply their actual footprint vertices instead.
        controlTargets = [vertex for other in self.walls if self.IsObjectVisible(other) and type(other) is joinClass and other is not stair
                          for index, vertex in enumerate((other.firstVertex, other.secondVertex))
                          if (id(other), index) not in movingVertices]
        if self.vertexSnapEnabled and self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            nearest = None
            nearestDistance = self.vertexSnapRange
            for vertex in controlTargets:
                offset = vertex - constraintOrigin
                if angleLocked and (abs(offset.x() * direction.y() - offset.y() * direction.x()) > .01
                                    or QtCore.QPointF.dotProduct(offset, direction) < 0):
                    continue
                distance = QtCore.QLineF(self.WorldToViewport(position), self.WorldToViewport(vertex)).length()
                if distance < nearestDistance:
                    nearest, nearestDistance = vertex, distance
            if nearest is not None:
                self.alignmentGuides = []
                self.snapApplied = True
                self.snapPriority = 0
                return QtCore.QPointF(nearest)
        alignmentCandidates = []
        if self.alignmentSnapEnabled:
            aligned = self.SnapPosition(position, modifiers, constraintOrigin if angleLocked else None,
                                        direction if angleLocked else None, snapTargets = controlTargets,
                                        alignmentTargets = [opposite])
            if self.alignmentGuides:
                if not angleLocked:
                    # Grid rounding on the other axis can push an attached stair
                    # into a wall even when the requested alignment fits exactly.
                    alignmentOnly = QtCore.QPointF(position)
                    for axis, coordinate in self.alignmentGuides:
                        if axis == 0:
                            alignmentOnly.setX(coordinate)
                        else:
                            alignmentOnly.setY(coordinate)
                    attachments = self.ActiveAttachments()
                    candidates = []
                    controlGuides = list(self.alignmentGuides)
                    if len(controlGuides) == 1:
                        # Keep the control alignment while snapping the bounding
                        # corners along the remaining axis to nearby wall faces.
                        run = alignmentOnly - opposite
                        runLength = math.hypot(run.x(), run.y())
                        if runLength > 1e-10:
                            run /= runLength
                            edgeOffset = QtCore.QPointF(-run.y(), run.x()) * (stair.width / 2)
                            for offset in (edgeOffset, -edgeOffset):
                                corner = alignmentOnly + offset
                                snapped = self.SnapPosition(corner, modifiers, opposite + offset, run,
                                                            snapTargets = snapTargets)
                                if self.snapApplied and self.alignmentGuides:
                                    target = snapped - offset
                                    candidates.append((QtCore.QLineF(corner, snapped).length(), target,
                                                       controlGuides + list(self.alignmentGuides)))
                    candidates.sort(key = lambda candidate: candidate[0])
                    candidates.extend((0, candidate, controlGuides) for candidate in (aligned, alignmentOnly))
                    testedPositions = set()
                    for distance, candidate, guides in candidates:
                        coordinates = (candidate.x(), candidate.y())
                        if coordinates in testedPositions:
                            continue
                        testedPositions.add(coordinates)
                        preview = type(stair)(opposite, candidate, stair.width)
                        fits = (self.StairFits(preview) if isinstance(preview, Stair) else
                                self.CounterFits(preview) if isinstance(preview, Counter) else self.WallFits(preview))
                        delta = candidate - (stair.firstVertex if self.selectedVertex == 0 else stair.secondVertex)
                        for attached, index, originalPosition in attachments:
                            if not isinstance(attached, Stair) or attached is stair:
                                continue
                            first = attached.firstVertex + delta if index == 0 else attached.firstVertex
                            second = attached.secondVertex + delta if index == 1 else attached.secondVertex
                            if not self.StairFits(Stair(first, second, attached.width)):
                                fits = False
                                break
                        if fits:
                            alignmentCandidates.append((1, QtCore.QLineF(position, candidate).length(), candidate,
                                                        list(dict.fromkeys(guides))))
                            break
                    self.alignmentGuides = controlGuides
                if not alignmentCandidates:
                    alignmentCandidates.append((1, QtCore.QLineF(position, aligned).length(), aligned, list(self.alignmentGuides)))
        runDirection = position - opposite
        runLength = math.hypot(runDirection.x(), runDirection.y())
        runDirection = runDirection / runLength if runLength > 1e-10 else direction
        normal = QtCore.QPointF(-runDirection.y(), runDirection.x()) * (stair.width / 2)
        footprintTargets = snapTargets
        if alignmentCandidates:
            # Same-class control alignment wins over that class's bounding box;
            # nearby wall faces can still compete with it during endpoint drags.
            movingIds = {objectId for objectId, index in movingVertices}
            objects = [obj for obj in self.walls + self.windows if self.IsObjectVisible(obj) and not isinstance(obj, Railing if joinClass is Railing else Counter if joinClass is Counter else Stair)
                       and obj is not stair and id(obj) not in movingIds
                       and not (isinstance(obj, Window) and (obj.parentWall is stair or id(obj.parentWall) in movingIds))]
            footprintTargets = [corner for obj in objects for corner in self.ObjectCorners(obj)]
            walls = [obj for obj in objects if type(obj) in (Wall, Pillar, Column)]
            if walls:
                for polygon in self.ConnectedWallPath(walls).toSubpathPolygons():
                    footprintTargets.extend(self.ViewportToWorld(vertex) for vertex in polygon)
        candidates = []
        for offset in (normal, -normal):
            corner = position + offset
            snapped = self.SnapPosition(corner, modifiers, constraintOrigin + offset if angleLocked else None,
                                        direction if angleLocked else None, snapTargets = footprintTargets)
            if not self.snapApplied or self.snapPriority == 2:
                continue
            if angleLocked:
                target = snapped - offset
            else:
                # Recover the centerline endpoint from the snapped cap corner,
                # preserving width as the endpoint changes the run's orientation.
                delta = snapped - opposite
                radius = math.hypot(delta.x(), delta.y())
                halfWidth = stair.width / 2
                if radius <= halfWidth:
                    continue
                runLength = math.sqrt(radius * radius - halfWidth * halfWidth)
                side = 1 if QtCore.QPointF.dotProduct(offset, normal) > 0 else -1
                angle = math.atan2(delta.y(), delta.x()) - math.atan2(side * halfWidth, runLength)
                target = opposite + QtCore.QPointF(math.cos(angle), math.sin(angle)) * runLength
            candidates.append((self.snapPriority, QtCore.QLineF(position, target).length(),
                               target, list(self.alignmentGuides)))
        candidates.extend(alignmentCandidates)
        # Grid snaps belong to the control vertex, not an offset cap corner.
        # Keep corner-based geometry/alignment candidates ahead of this fallback.
        gridPosition = self.SnapPosition(position, modifiers, constraintOrigin if angleLocked else None,
                                         direction if angleLocked else None, preparedTargets = [])
        if self.snapApplied and self.snapPriority == 2:
            candidates.append((2, QtCore.QLineF(position, gridPosition).length(), gridPosition, []))
        if candidates:
            # Compare snap class before distance across both footprint corners.
            # A closer grid correction must never beat geometry or alignment.
            selfAlignments = [candidate for candidate in alignmentCandidates if type(stair) is Wall
                              and any(abs(coordinate - (opposite.x() if axis == 0 else opposite.y())) <= .01
                                      for axis, coordinate in candidate[3])]
            # A wall aligning to its stationary endpoint should become straight,
            # rather than aligning an offset cap corner to that endpoint's axis.
            priority, distance, target, guides = min(candidates, key = lambda candidate:
                (candidate[0], 0 if candidate in selfAlignments else 1, candidate[1]))
            self.alignmentGuides = guides if priority == 1 else []
            if type(stair) is Wall:
                self.alignmentGuides = [(axis, coordinate) for axis, coordinate in self.alignmentGuides
                                        if abs((target.x() if axis == 0 else target.y()) - coordinate) <= .01]
            self.snapApplied = True
            self.snapPriority = priority
            return target
        self.alignmentGuides = []
        self.snapApplied = False
        self.snapPriority = 3
        return position

    def SnapMidpoints(self):
        movingWalls = {id(wall) for wall, vertexIndex, originalPosition in self.ActiveAttachments()}
        if self.furnishingHandleDrag is not None:
            movingWalls.add(id(self.furnishingHandleDrag["object"]))
            movingWalls.update(id(state[0]) for state in self.furnishingHandleDrag["members"])
        for wall in self.walls + self.windows + self.furnishings + self.labels:
            if not self.IsObjectVisible(wall):
                continue
            if self.groupDrag and any(wall is obj for obj, index in self.groupMovedOpenings):
                continue
            if self.dragStart is not None:
                if wall is self.selectedWall or id(wall) in movingWalls:
                    continue
                if isinstance(wall, Window) and (wall.parentWall is self.selectedWall or id(wall.parentWall) in movingWalls):
                    continue
            yield (wall.firstVertex + wall.secondVertex) / 2

    def SnapPosition(self, worldPosition, modifiers, angleAnchor = None, angleDirection = None, snapTargets = None,
                     alignmentTargets = None, preparedTargets = None, preparedTargetIndex = None, numericTargets = None, rayTargets = None):
        self.alignmentGuides = []
        self.snapApplied = False
        self.snapPriority = 3
        altHeld = bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier)
        if self.snapEnabled == altHeld:
            return worldPosition
        if numericTargets is None:
            if preparedTargets is None:
                targets = self.SnapVertices() if snapTargets is None else snapTargets
                numericTargets = [(vertex.x(), vertex.y(), self.vertexSnapEnabled) for vertex in targets]
                if alignmentTargets is not None:
                    numericTargets.extend((vertex.x(), vertex.y(), False) for vertex in alignmentTargets)
                if self.midpointSnapEnabled:
                    numericTargets.extend((vertex.x(), vertex.y(), True) for vertex in self.SnapMidpoints())
            else:
                # Retain the public prepared Qt-target layout for existing
                # callers; the portable core receives only coordinates/policy.
                numericTargets = [(x, y, directSnap) for x, y, vertex, directSnap in preparedTargets]
        gridStep = self.GridSteps()[1] if self.gridSnapEnabled else None
        point, self.snapApplied, self.snapPriority, self.alignmentGuides = SnapPoint(
            (worldPosition.x(), worldPosition.y()), numericTargets,
            self.basePixelsPerMillimeter * self.zoom, self.vertexSnapRange,
            self.alignmentSnapEnabled, gridStep,
            (angleAnchor.x(), angleAnchor.y()) if angleAnchor is not None else None,
            (angleDirection.x(), angleDirection.y()) if angleAnchor is not None else None,
            preparedTargetIndex, rayTargets)
        return QtCore.QPointF(*point)

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
        numericTargets = []
        if self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            targets = self.SnapVertices() if snapTargets is None else snapTargets
            numericTargets = [(vertex.x(), vertex.y(), self.vertexSnapEnabled) for vertex in targets]
            if self.midpointSnapEnabled:
                numericTargets.extend((vertex.x(), vertex.y(), True) for vertex in self.SnapMidpoints())
        candidates = []
        preparedTargetIndex = None
        rayTargets = None
        if len(numericTargets) > 32:
            if direction is None:
                preparedTargetIndex = PrepareTargetIndex(numericTargets)
            elif len(anchors) >= 3:
                rayTargets = PrepareRayTargets(numericTargets)
        for anchor in anchors:
            moved = anchor + delta
            snapped = self.SnapPosition(moved, modifiers, anchor if direction is not None else None,
                                        direction, snapTargets = snapTargets, preparedTargets = [],
                                        preparedTargetIndex = preparedTargetIndex, numericTargets = numericTargets, rayTargets = rayTargets)
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

    def TranslationAxes(self):
        if not self.localTransforms or self.selectedWall is None:
            return QtCore.QPointF(1, 0), QtCore.QPointF(0, 1)
        vertices = self.dragSourceVertices or self.dragVertices or (self.selectedWall.firstVertex, self.selectedWall.secondVertex)
        direction = vertices[1] - vertices[0]
        length = math.hypot(direction.x(), direction.y())
        if length < 1e-10:
            return QtCore.QPointF(1, 0), QtCore.QPointF(0, 1)
        direction /= length
        normal = QtCore.QPointF(-direction.y(), direction.x())
        return (-normal, direction) if isinstance(self.selectedWall, (Furnishing, Pillar)) else (direction, normal)

    def VertexConstraintAxes(self):
        reference = 0.0
        original = QtCore.QPointF()
        if self.localTransforms and self.selectedWall is not None and self.selectedVertex is not None:
            vertices = self.dragSourceVertices or self.dragVertices
            if vertices is not None:
                original = vertices[self.selectedVertex] - vertices[1 - self.selectedVertex]
                if math.hypot(original.x(), original.y()) > 1e-10:
                    reference = math.atan2(original.y(), original.x())
        key = (self.localTransforms, original.x(), original.y())
        if key != getattr(self, "vertexConstraintAxesKey", None):
            # Twelve infinite lines give all twenty-four rays at 15 degrees.
            self.vertexConstraintAxes = tuple(QtCore.QPointF(math.cos(reference + index * math.pi / 12),
                math.sin(reference + index * math.pi / 12)) for index in range(12))
            self.vertexConstraintAxesKey = key
        return self.vertexConstraintAxes

    def ConstrainedVertexAngle(self, direction):
        axis = self.VertexConstraintAxes()[0]
        reference = math.atan2(axis.y(), axis.x())
        angleStep = math.radians(15)
        return reference + round((math.atan2(direction.y(), direction.x()) - reference) / angleStep) * angleStep

    def SnapWallEndpoint(self, worldPosition, anchor, modifiers, wall = None):
        if wall is not None:
            return self.SnapStairVertex(worldPosition, anchor, wall, modifiers)
        if not modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            return self.SnapPosition(worldPosition, modifiers)
        if (self.dragStart is not None and self.selectedVertex is not None
                and self.vertexAxisFromDragged and self.dragVertices is not None):
            anchor = self.dragVertices[self.selectedVertex]
        offset = worldPosition - anchor
        length = math.hypot(offset.x(), offset.y())
        angle = self.ConstrainedVertexAngle(offset)
        direction = QtCore.QPointF(math.cos(angle), math.sin(angle))
        self.axisConstraintOrigin = QtCore.QPointF(anchor)
        self.axisConstraintDirection = direction
        return self.SnapPosition(anchor + direction * length, modifiers, anchor, direction)
