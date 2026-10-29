"""Grid, alignment, endpoint and oriented-footprint snapping."""
from planner_app.geometry.endpoint_snapping import NearestRunControlTarget
from planner_app.models import AngleGuide, ObjectControlPoints

import math
from planner_app.geometry.snapping import GridIntervals, SnapPoint
from planner_app.geometry.measurements import GuideDepthOffset
from planner_app.geometry.movement_snapping import (MovementAxes, ConstraintAxes, ConstrainedAngle,
    ConstrainMovement, SnapMovement)
from planner_app.geometry.endpoint_snapping import CapEndpoint, AlignmentPlacementCandidates, SelectEndpointSnap
from planner_app.graphics.path_operations import Paths
from PySide6 import QtCore
from planner_app.models import Furnishing, MeasurementGuide, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, Window, Fireplace
from planner_app.units import imperialModes
from .geometry import CollisionPass


class CornerSnapPoint(QtCore.QPointF):
    """A footprint or joined-boundary target, distinct from a control point."""


def MovementSnapDistance(x, y):
    # Qt and Python hypot can differ by one bit. Keep the native metric so
    # equally close anchors retain the same winning alignment guide.
    return QtCore.QLineF(0.0, 0.0, x, y).length()


class SnappingMixin:
    def GuideDepthEndpoints(self, guide, vertices = None):
        if type(guide) is not MeasurementGuide or guide.depth == 0:
            return ()
        first, second = vertices if vertices is not None else (guide.firstVertex, guide.secondVertex)
        offset = QtCore.QPointF(*GuideDepthOffset((first.x(), first.y()), (second.x(), second.y()), guide.depth))
        return first + offset, second + offset

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
                       for index, vertex in enumerate(ObjectControlPoints(other))
                       if (id(other), index) not in movingVertices]
            if type(stair) is MeasurementGuide:
                movingIds = {objectId for objectId, index in movingVertices}
                targets.extend(vertex for other in self.walls if type(other) is MeasurementGuide and other is not stair
                               and id(other) not in movingIds and self.IsObjectVisible(other)
                               for vertex in self.GuideDepthEndpoints(other))
            if self.vertexSnapEnabled:
                numericTargets = [(vertex.x(), vertex.y()) for vertex in targets] if angleLocked else [None] * len(targets)
                nearest = NearestRunControlTarget((constraintOrigin.x(), constraintOrigin.y()), (direction.x(), direction.y()),
                    numericTargets, angleLocked, lambda index: QtCore.QLineF(position, targets[index]).length())
                if nearest is not None and nearest[1] * self.basePixelsPerMillimeter * self.zoom < self.vertexSnapRange:
                    self.alignmentGuides = []
                    self.snapApplied = True
                    self.snapPriority = 0
                    return QtCore.QPointF(targets[nearest[0]])
            return self.SnapPosition(position, modifiers, constraintOrigin if angleLocked else None,
                                     direction if angleLocked else None, snapTargets = targets + snapTargets,
                                     alignmentTargets = None if isinstance(stair, AngleGuide) else [opposite])
        joinClass = Railing if isinstance(stair, Railing) else Counter if isinstance(stair, Counter) else Stair if isinstance(stair, Stair) else Wall
        # Same-class runs join at either control endpoint. Other object classes
        # continue to supply their actual footprint vertices instead.
        controlTargets = [vertex for other in self.walls if self.IsObjectVisible(other) and type(other) is joinClass and other is not stair
                          for index, vertex in enumerate((other.firstVertex, other.secondVertex))
                          if (id(other), index) not in movingVertices]
        if controlTargets and self.vertexSnapEnabled and self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            screenPosition = self.WorldToViewport(position)
            numericTargets = [(vertex.x(), vertex.y()) for vertex in controlTargets] if angleLocked else [None] * len(controlTargets)
            nearest = NearestRunControlTarget((constraintOrigin.x(), constraintOrigin.y()), (direction.x(), direction.y()),
                numericTargets, angleLocked, lambda index: QtCore.QLineF(screenPosition, self.WorldToViewport(controlTargets[index])).length(),
                limit = self.vertexSnapRange)
            if nearest is not None:
                self.alignmentGuides = []
                self.snapApplied = True
                self.snapPriority = 0
                return QtCore.QPointF(controlTargets[nearest[0]])
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
                                    candidates.append((QtCore.QLineF(corner, snapped).length(), (target.x(), target.y()),
                                                       controlGuides + list(self.alignmentGuides)))
                    for coordinates, guides in AlignmentPlacementCandidates(candidates,
                            (aligned.x(), aligned.y()), (alignmentOnly.x(), alignmentOnly.y()), controlGuides):
                        candidate = QtCore.QPointF(*coordinates)
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
                            alignmentCandidates.append((1, QtCore.QLineF(position, candidate).length(), coordinates,
                                                        list(dict.fromkeys(guides))))
                            break
                    self.alignmentGuides = controlGuides
                if not alignmentCandidates:
                    alignmentCandidates.append((1, QtCore.QLineF(position, aligned).length(), (aligned.x(), aligned.y()), list(self.alignmentGuides)))
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
            footprintTargets = [CornerSnapPoint(corner) for obj in objects for corner in self.ObjectCorners(obj)]
            walls = [obj for obj in objects if type(obj) in (Wall, Pillar, Column)]
            if walls:
                for polygon in Paths.Contours(self.ConnectedWallPath(walls)):
                    footprintTargets.extend(CornerSnapPoint(self.ViewportToWorld(vertex)) for vertex in polygon)
        candidates = []
        for offset in (normal, -normal):
            corner = position + offset
            snapped = self.SnapPosition(corner, modifiers, constraintOrigin + offset if angleLocked else None,
                                        direction if angleLocked else None, snapTargets = footprintTargets)
            if not self.snapApplied or self.snapPriority == 2:
                continue
            target = CapEndpoint((snapped.x(), snapped.y()), (opposite.x(), opposite.y()),
                (offset.x(), offset.y()), (normal.x(), normal.y()), stair.width, angleLocked)
            if target is None:
                continue
            candidates.append((self.snapPriority, QtCore.QLineF(position, QtCore.QPointF(*target)).length(),
                               target, list(self.alignmentGuides)))
        candidates.extend(alignmentCandidates)
        # Grid snaps belong to the control vertex, not an offset cap corner.
        # Keep corner-based geometry/alignment candidates ahead of this fallback.
        gridPosition = self.SnapPosition(position, modifiers, constraintOrigin if angleLocked else None,
                                         direction if angleLocked else None, preparedTargets = [])
        if self.snapApplied and self.snapPriority == 2:
            candidates.append((2, QtCore.QLineF(position, gridPosition).length(), (gridPosition.x(), gridPosition.y()), []))
        target, self.snapApplied, self.snapPriority, self.alignmentGuides = SelectEndpointSnap(
            (position.x(), position.y()), (opposite.x(), opposite.y()), candidates, alignmentCandidates, type(stair) is Wall)
        return QtCore.QPointF(*target)

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

    def NumericSnapTargets(self, targets = None):
        """Supply only enabled target types for direct and alignment snapping."""
        if targets is None:
            targets = self.SnapVertices()
        return [(target.x(), target.y(), True) for target in targets
                if (self.cornerSnapEnabled if isinstance(target, CornerSnapPoint) else self.vertexSnapEnabled)]

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
                numericTargets = self.NumericSnapTargets(snapTargets)
                if alignmentTargets is not None and self.vertexSnapEnabled:
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

    def TranslationAxes(self):
        if not self.localTransforms or self.selectedWall is None or isinstance(self.selectedWall, AngleGuide):
            return QtCore.QPointF(1, 0), QtCore.QPointF(0, 1)
        vertices = self.dragSourceVertices or self.dragVertices or (self.selectedWall.firstVertex, self.selectedWall.secondVertex)
        first, second = vertices[0], vertices[1]
        axes = MovementAxes((first.x(), first.y()), (second.x(), second.y()),
                            isinstance(self.selectedWall, (Furnishing, Pillar)))
        return tuple(QtCore.QPointF(*axis) for axis in axes)

    def VertexConstraintAxes(self):
        original = QtCore.QPointF()
        if self.localTransforms and self.selectedWall is not None and self.selectedVertex is not None:
            vertices = self.dragSourceVertices or self.dragVertices
            if vertices is not None:
                opposite = 2 if isinstance(self.selectedWall, AngleGuide) and self.selectedVertex in (0, 1) else 1 - self.selectedVertex
                original = vertices[self.selectedVertex] - vertices[opposite]
        key = (self.localTransforms, original.x(), original.y())
        if key != getattr(self, "vertexConstraintAxesKey", None):
            # Twelve infinite lines give all twenty-four rays at 15 degrees.
            self.vertexConstraintAxes = tuple(QtCore.QPointF(*axis)
                for axis in ConstraintAxes((original.x(), original.y())))
            self.vertexConstraintAxesKey = key
        return self.vertexConstraintAxes

    def ConstrainedVertexAngle(self, direction):
        axis = self.VertexConstraintAxes()[0]
        return ConstrainedAngle((direction.x(), direction.y()), (axis.x(), axis.y()))

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
