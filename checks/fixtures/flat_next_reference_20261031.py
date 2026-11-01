"""Frozen start-of-pass wall assembly and endpoint snapping adapters."""

"""Joined footprints, hit testing, collision geometry and wall measurements."""
from planner_app.models import AngleGuide, ObjectControlPoints

import math
from time import perf_counter
from functools import wraps
from planner_app.coincident_records import GroupCoincidentRecords, coincidentEncoder
from planner_app.scene_changes import SceneObject
from planner_app.preferences import collisionDefaults
from planner_app.numpy_runtime import LoadNumPy
from planner_app.viewport.polygon_clipping import SubtractConvexPolygon
from planner_app.viewport.spatial_index import BoundsIndex
from planner_app.viewport.geometry_cache import NativeGeometryBudget, NativeGeometryCache
from planner_app.viewport.collision_types import CollisionFlags
from planner_app.geometry.snapping import PrepareTargetIndex, NearbyPointIndices
from planner_app.geometry.collisions import (AllowsCollision, ExcludesFootprintCollision, FootprintsOverlap,
    FootprintContainment, SignificantPathOverlap, JunctionReach, RigidTranslation)
from planner_app.geometry.junctions import BuildWallJunction as BuildNumericWallJunction
from planner_app.geometry.polygons import ClipHalfPlane, PolygonTwiceArea
from planner_app.geometry.boundaries import GroupContourBounds, TraceBoundaryContours
from planner_app.geometry.footprints import (WallBody, RectangleFootprint, ColumnHandleCorners,
    PolygonAxes, FireplaceFootprint)
from planner_app.geometry.measurements import (MergeMeasurementSegments, FindMeasurementOwners,
    PrepareMeasurementPolygons, ExposedMeasurementSpans, MeasurementOpening,
    PlanMeasurementComponents, BuildOpeningDimensions, EffectiveWallSplitSettings)
from planner_app.geometry.measurements import GuideDepthOffset
from planner_app.geometry.reserved_doors import ReservedDoorSupportBounds, ReservedDoorWallContact, ReservedDoorPlacementBounds
from planner_app.geometry.stair_annotations import StairInsetLines
from planner_app.graphics.arrows import ArrowPaths, ConnectedArrowDirections, ConnectedArrowCorners
from planner_app.graphics.path_operations import Paths
from planner_app.graphics import palette
from PySide6 import QtCore, QtGui
from planner_app.models import OpenDoorway, Door, SwingingDoor, DoubleDoor, PocketDoor, BarnDoor, BifoldDoor, SlidingDoor, MeasurementGuide, BoundaryLine, DashedLine, SolidLine, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Label, Furnishing, NorthArrow, Fireplace
from planner_app.graphics.fireplace import FireplacePath
from planner_app.graphics.symbols import WindowWellPath
from planner_app.graphics.column import ColumnPolygon, ColumnPath, ColumnContains
from planner_app.graphics.furnishings import FurnishingContainsPoint
from planner_app.furnishing_parts import FurnishingCollisionFootprints
from planner_app.models import Elevator
from planner_app.models import lineWeightClasses


def CollisionPass(function):
    """Batch geometry; validate retained pair results only when a query needs them."""
    @wraps(function)
    def Batched(self, *args, **kwargs):
        previous = getattr(self, "collisionPassCache", None)
        if previous is None:
            self.collisionPassCache = {}
        try:
            return function(self, *args, **kwargs)
        finally:
            if previous is None and len(getattr(self, "collisionResults", {})) > 16384:
                self.collisionResults = {}
                self.collisionPairKeys = {}
                self.collisionPairEpochs = {}
            self.collisionPassCache = previous
    return Batched



class ReferenceGeometry:
    def ConnectedWallPath(self, walls, traceContours = True):
        if any(isinstance(wall, Column) for wall in walls):
            return self.ConnectedColumnWallPath(walls, traceContours)
        prepared = self.__dict__.get("columnGeometryPreparation")
        if prepared is not None:
            context = self.ColumnPreparationContext()
            # Picking/collision queries also ask this viewport for regular-only
            # subsets. Keep valid column work across those scratch queries.
            if context is None or prepared["context"] != context:
                self.__dict__.pop("columnGeometryPreparation", None)
                self.__dict__.pop("columnExteriorPrefix", None)
        self.columnOutlinePaths = []
        self.columnMaterialPaths = {}
        # Build once in a stable coordinate system; pan/zoom only transform the path.
        changes = getattr(self, "renderChanges", None)
        preparedKey = ((changes.geometry, changes.appearance, changes.topology, changes.visibility,
                        self.basePixelsPerMillimeter, id(walls), traceContours) if changes is not None else None)
        if walls is getattr(self, "preparedWallMembers", None) and getattr(self, "preparedWallValueKey", None) is not None and self.preparedWallValueKey[0] == preparedKey:
            geometryKey = self.preparedWallValueKey[1]
        else:
            geometryKey = (self.basePixelsPerMillimeter, traceContours, tuple((id(wall), wall.firstVertex.x(), wall.firstVertex.y(),
                             wall.secondVertex.x(), wall.secondVertex.y(), wall.width,
                             wall.firstMiter, wall.secondMiter) for wall in walls))
            if walls is getattr(self, "preparedWallMembers", None):
                self.preparedWallValueKey = (preparedKey, geometryKey)
        origin = self.WorldToViewport(QtCore.QPointF())
        viewTransform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
        if geometryKey == self.wallGeometryKey:
            return viewTransform.map(self.wallGeometryPath)
        previousKey = self.wallGeometryKey
        if previousKey is not None and previousKey[:2] == geometryKey[:2]:
            translation = self.WallTranslation(previousKey[2], geometryKey[2])
            if translation is not None:
                transform = QtGui.QTransform().translate(translation.x() * self.basePixelsPerMillimeter,
                                                         -translation.y() * self.basePixelsPerMillimeter)
                self.wallGeometryPath = transform.map(self.wallGeometryPath)
                self.wallFillPolygons = [(owner, transform.map(polygon)) for owner, polygon in self.wallFillPolygons]
                self.wallFootprintCuts = {owner: [((point[0] + translation.x() * self.basePixelsPerMillimeter,
                    point[1] - translation.y() * self.basePixelsPerMillimeter), normal) for point, normal in planes]
                    for owner, planes in self.wallFootprintCuts.items()}
                self.wallGeometryComponents = [((key[0], key[1], tuple((id(wall), wall.firstVertex.x(), wall.firstVertex.y(),
                    wall.secondVertex.x(), wall.secondVertex.y(), wall.width, wall.firstMiter, wall.secondMiter) for wall in members)),
                    members, transform.map(path)) for key, members, path in self.wallGeometryComponents]
                self.wallGeometryKey = geometryKey
                if self.materialGeometryKey is not None and self.materialGeometryKey[0] == previousKey:
                    self.materialPaths = {material: transform.map(path) for material, path in self.materialPaths.items()}
                    self.wallMaterialPaths = {owner: transform.map(path) for owner, path in self.wallMaterialPaths.items()}
                    self.materialGeometryKey = (geometryKey, self.materialGeometryKey[1])
                return viewTransform.map(self.wallGeometryPath)
        def MergeBounds(entries, count):
            if count <= 1:
                return [list(range(count))] if count else []
            parents = list(range(count))
            spatial = None
            # Index component envelopes when many owned pieces make the
            # rectangle sweep expensive. Simple isolated walls keep that sweep.
            if (count >= 32 and len(entries) > count * 2
                    and all(math.isfinite(value) for index, bounds in entries for value in bounds.getCoords())):
                memberBounds = [[] for index in range(count)]
                componentBounds = [None] * count
                for index, bounds in entries:
                    memberBounds[index].append(bounds)
                    previous = componentBounds[index]
                    componentBounds[index] = bounds if previous is None else previous.united(bounds)
                sizes = sorted(max(bounds.width(), bounds.height()) for bounds in componentBounds if bounds is not None)
                spatial = BoundsIndex(sizes[len(sizes) // 2] if sizes else 1)
            active = []
            scanEntries = (enumerate(componentBounds) if spatial is not None else
                           sorted(entries, key = lambda entry: entry[1].left()))
            for index, bounds in scanEntries:
                if bounds is None:
                    continue
                if spatial is None:
                    active = [(other, otherBounds) for other, otherBounds in active if otherBounds.right() >= bounds.left()]
                    candidates = active
                else:
                    candidates = ((other, componentBounds[other]) for other in spatial.Query(bounds))
                for other, otherBounds in candidates:
                    if index == other or not bounds.intersects(otherBounds):
                        continue
                    if spatial is not None and not any(first.intersects(second)
                            for first in memberBounds[index] for second in memberBounds[other]):
                        continue
                    first, second = index, other
                    while parents[first] != first:
                        parents[first] = parents[parents[first]]
                        first = parents[first]
                    while parents[second] != second:
                        parents[second] = parents[parents[second]]
                        second = parents[second]
                    parents[first] = second
                if spatial is None:
                    active.append((index, bounds))
                else:
                    # The envelope rejects distant components; exact owned
                    # pieces decide contact, including gaps inside an envelope.
                    spatial.Insert(bounds, index)
            groups = {}
            for index in range(count):
                parent = index
                while parents[parent] != parent:
                    parent = parents[parent]
                groups.setdefault(parent, []).append(index)
            return list(groups.values())

        # Miter geometry only depends on walls sharing control endpoints.
        # Crossing a stationary construction must not rebuild its junctions.
        parents = list(range(len(walls)))
        endpointBuckets = {}
        for index, wall in enumerate(walls):
            for vertex in (wall.firstVertex, wall.secondVertex):
                bucketX, bucketY = math.floor(vertex.x() / .01), math.floor(vertex.y() / .01)
                for x in range(bucketX - 1, bucketX + 2):
                    for y in range(bucketY - 1, bucketY + 2):
                        for other, otherVertex in endpointBuckets.get((x, y), ()):
                            if QtCore.QLineF(vertex, otherVertex).length() > .01:
                                continue
                            first, second = index, other
                            while parents[first] != first:
                                first = parents[first]
                            while parents[second] != second:
                                second = parents[second]
                            parents[first] = second
                endpointBuckets.setdefault((bucketX, bucketY), []).append((index, vertex))
        groups = {}
        for index in range(len(walls)):
            parent = index
            while parents[parent] != parent:
                parent = parents[parent]
            groups.setdefault(parent, []).append(index)
        components = list(groups.values())
        results = []
        footprintCuts = {}
        for indices in components:
            key = (geometryKey[0], traceContours, tuple(geometryKey[2][index] for index in indices))
            cached = self.wallComponentCache.get(key)
            if cached is None:
                self.BuildWallComponent([walls[index] for index in indices], traceContours)
                cached = (self.wallGeometryPath, self.wallFillPolygons, self.wallFootprintCuts)
                self.wallComponentCache[key] = cached
            results.append(cached)
            footprintCuts.update(cached[2])
        self.wallFootprintCuts = footprintCuts
        # Remove internal crossing edges from the cached exterior contours,
        # rather than retracing every rectangle and miter triangle underneath.
        endJoinedRuns = bool(walls) and all(type(wall) in (Counter, Stair) for wall in walls)
        pillarWeldTolerance = .01 * self.basePixelsPerMillimeter
        if endJoinedRuns:
            overlapping = [[index] for index in range(len(components))]
        else:
            componentBounds = []
            for index, result in enumerate(results):
                for owner, polygon in result[1]:
                    margin = pillarWeldTolerance if isinstance(owner, Pillar) else 1e-8
                    componentBounds.append((index, polygon.boundingRect().adjusted(-margin, -margin, margin, margin)))
            overlapping = MergeBounds(componentBounds, len(components))
        mergedResults = []
        mergedComponents = []
        for group in overlapping:
            path = QtGui.QPainterPath()
            path.setFillRule(QtCore.Qt.FillRule.WindingFill)
            polygons = []
            for index in group:
                path.addPath(results[index][0])
                polygons.extend(results[index][1])
            if traceContours and len(group) > 1:
                traceKey = ("overlap", tuple(id(walls[index]) for component in group for index in components[component]))
                weldTolerance = (pillarWeldTolerance if any(isinstance(walls[index], Pillar)
                    for component in group for index in components[component]) else 0.0)
                weldOptions = {"weldTolerance": weldTolerance} if weldTolerance else {}
                path = self.TraceWallBoundary(path, traceKey = traceKey, **weldOptions)
            mergedResults.append((path, polygons))
            mergedComponents.append(sorted(index for component in group for index in components[component]))
        components, results = mergedComponents, mergedResults
        combined = QtGui.QPainterPath()
        combined.setFillRule(QtCore.Qt.FillRule.WindingFill)
        self.wallFillPolygons = []
        for path, polygons in results:
            combined.addPath(path)
            self.wallFillPolygons.extend(polygons)
        pillarPolygons = [polygon for owner, polygon in self.wallFillPolygons
                          if isinstance(owner, Pillar)]
        if pillarPolygons:
            # Pillars own their full rectangle, independent of scene/material
            # order, including when a neighboring wall is highlighted.
            priorityPolygons = []
            pillarData = [(polygon, self.PreparedWallPolygon(polygon)) for polygon in pillarPolygons]
            ownershipCache = self.wallOwnershipCache
            for owner, polygon in self.wallFillPolygons:
                if isinstance(owner, Pillar):
                    priorityPolygons.append((owner, polygon))
                    continue
                coordinates, bounds, normalized = self.PreparedWallPolygon(polygon)
                cutters = [(cutter, data[0]) for cutter, data in pillarData if bounds.intersects(data[1])]
                if not cutters:
                    priorityPolygons.append((owner, polygon))
                    continue
                key = ("pillars", coordinates, tuple(cutterKey for cutter, cutterKey in cutters))
                fragments = ownershipCache.get(key)
                if fragments is None:
                    pieces = [list(polygon)]
                    for cutter, cutterKey in cutters:
                        pieces = [piece for fragment in pieces for piece in SubtractConvexPolygon(fragment, cutter)]
                    fragments = tuple(QtGui.QPolygonF(fragment) for fragment in pieces if len(fragment) >= 3)
                    ownershipCache[key] = fragments
                priorityPolygons.extend((owner, fragment) for fragment in fragments)
            while len(ownershipCache) > max(1024, len(walls) * 16):
                ownershipCache.pop(next(iter(ownershipCache)))
            self.wallFillPolygons = priorityPolygons
        self.wallGeometryPath = combined
        self.wallGeometryKey = geometryKey
        self.wallGeometryComponents = [((geometryKey[0], traceContours, tuple(geometryKey[2][index] for index in indices)),
                                       [walls[index] for index in indices], result[0])
                                      for indices, result in zip(components, results)]
        while len(self.wallComponentCache) > max(128, len(components) * 2):
            self.wallComponentCache.pop(next(iter(self.wallComponentCache)))
        return viewTransform.map(combined)


"""Grid, alignment, endpoint and oriented-footprint snapping."""
from planner_app.geometry.endpoint_snapping import NearestRunControlTarget
from planner_app.models import AngleGuide, ObjectControlPoints

import math
from planner_app.geometry.snapping import GridIntervals, SnapPoint, PrepareTargetIndex, PrepareRayTargets
from planner_app.geometry.measurements import GuideDepthOffset
from planner_app.geometry.movement_snapping import (MovementAxes, ConstraintAxes, ConstrainedAngle,
    ConstrainMovement, SnapMovement)
from planner_app.geometry.endpoint_snapping import CapEndpoint, AlignmentPlacementCandidates, SelectEndpointSnap
from planner_app.graphics.path_operations import Paths
from PySide6 import QtCore
from planner_app.models import Furnishing, MeasurementGuide, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, Window, Fireplace
from planner_app.units import imperialModes
from planner_app.viewport.geometry import CollisionPass


class CornerSnapPoint(QtCore.QPointF):
    """A footprint or joined-boundary target, distinct from a control point."""


def MovementSnapDistance(x, y):
    # Qt and Python hypot can differ by one bit. Keep the native metric so
    # equally close anchors retain the same winning alignment guide.
    return QtCore.QLineF(0.0, 0.0, x, y).length()



class ReferenceSnapping:
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


"""Placement previews, opening fitting, collision validation and sidebar drops."""
from planner_app.models import AngleGuide

from planner_app.models import Elevator

import math
from contextlib import contextmanager
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import OpenDoorway, Door, SwingingDoor, DoubleDoor, Furnishing, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, SlidingDoor, MeasurementGuide, BoundaryLine, DashedLine, SolidLine, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, RoomLabel, Window, NorthArrow, Fireplace
from planner_app.viewport.geometry import CollisionPass
from planner_app.geometry.opening_placement import (ProjectOpening, OpeningGap,
    BlockedOpeningIntervals, OpeningPlacementSpan, CenteredOpeningSpan, OpeningVertexFraction)
from planner_app.geometry.opening_collisions import OpeningCollisionIndex
from planner_app.geometry.reserved_doors import ReservedDoorWithinHost, ReservedDoorWallContact, ReservedDoorPlacementBounds, ReservedDoorEditCenter
from planner_app.geometry.opening_candidates import OpeningFacingChanges, FireplaceDepthSnap, FireplacePlacementCandidates
from planner_app.viewport.placement_types import OpeningFacingPolicy
from planner_app.viewport.spatial_index import BoundsIndex
from planner_app.geometry.attachments import FitOpeningCenters, OpeningWithinWall, OpeningIntervalsOverlap
from planner_app.placement_sizing import NominalPlacementSize, FurnishingPlacementSize



class ReferencePlacement:
    def PlacementBlockers(self, obj, kind):
        """Ordered broad phase confined to one immutable validation scope."""
        scope = (getattr(self, "collisionPassCache", None) or {}).get("placementValidation")
        if scope is None:
            return None
        members = scope["categories"][kind]
        if not members:
            return ()
        if scope["index"] is None:
            index = BoundsIndex(2000)
            fallback = []
            for member in scope["objects"]:
                if isinstance(member, (Arrow, MeasurementGuide, Label, NorthArrow)):
                    continue
                bounds = self.JoinedObjectBounds(member)
                if type(member) is Furnishing:
                    scope["furnishingBounds"][id(member)] = bounds
                if all(math.isfinite(value) for value in bounds.getCoords()):
                    index.Insert(bounds.normalized().adjusted(-.01, -.01, .01, .01), member)
                else:
                    fallback.append(member)
            scope["index"], scope["fallback"] = index, fallback
            scope["orders"] = {name: {id(member): position for position, member in enumerate(values)}
                               for name, values in scope["categories"].items()}
        identity = id(obj), kind
        if identity not in scope["nearby"]:
            bounds = self.JoinedObjectBounds(obj)
            if not all(math.isfinite(value) for value in bounds.getCoords()):
                nearby = [member for member in members if member is not obj]
            else:
                order = scope["orders"][kind]
                movingBounds = scope.get("movingBounds", {})
                nearby = [member for member in scope["index"].Query(bounds.normalized().adjusted(-.01, -.01, .01, .01))
                          + scope["fallback"] if id(member) in order and member is not obj and id(member) not in movingBounds]
                if movingBounds:
                    queryBounds = bounds.normalized().adjusted(-.01, -.01, .01, .01)
                    nearby.extend(scope["members"][identity] for identity, currentBounds in movingBounds.items()
                                  if identity in order and identity != id(obj)
                                  and queryBounds.intersects(currentBounds.normalized().adjusted(-.01, -.01, .01, .01)))
                nearby.sort(key = lambda member: order[id(member)])
            scope["nearby"][identity] = tuple(nearby)
        return scope["nearby"][identity]

