"""Joined footprints, hit testing, collision geometry and wall measurements."""
from planner_app.models import AngleGuide, ObjectControlPoints

import math
from time import perf_counter
from functools import wraps
from planner_app.coincident_records import GroupCoincidentRecords
from planner_app.preferences import collisionDefaults
from .polygon_clipping import SubtractConvexPolygon
from .spatial_index import BoundsIndex
from .collision_types import CollisionFlags
from planner_app.geometry.snapping import PrepareTargetIndex, NearbyPointIndices
from planner_app.geometry.collisions import (AllowsCollision, ExcludesFootprintCollision, FootprintsOverlap,
    FootprintContainment, SignificantPathOverlap, JunctionReach, RigidTranslation)
from planner_app.geometry.junctions import BuildWallJunction as BuildNumericWallJunction
from planner_app.geometry.polygons import ClipHalfPlane
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


class GeometryMixin:
    def ReservedDoorSupport(self, parent, walls = None):
        if walls is not None:
            return ReservedDoorSupportBounds((parent.firstVertex.x(), parent.firstVertex.y()),
                (parent.secondVertex.x(), parent.secondVertex.y()),
                (((wall.firstVertex.x(), wall.firstVertex.y()), (wall.secondVertex.x(), wall.secondVertex.y()))
                 for wall in walls if type(wall) is Wall))
        changes = getattr(self, "renderChanges", None)
        key = ((changes.wallGeometry, changes.topology) if changes is not None else
               tuple((id(wall), wall.firstVertex.x(), wall.firstVertex.y(), wall.secondVertex.x(), wall.secondVertex.y())
                     for wall in self.walls if type(wall) is Wall))
        if key != getattr(self, "reservedDoorSupportKey", None):
            self.reservedDoorSupportKey, self.reservedDoorSupportCache = key, {}
        parentKey = id(parent), parent.firstVertex.x(), parent.firstVertex.y(), parent.secondVertex.x(), parent.secondVertex.y()
        if parentKey not in self.reservedDoorSupportCache:
            # Store only two scalar bounds per queried parent, never complete
            # membership sets for every wall in a subdivided run.
            if len(self.reservedDoorSupportCache) >= 2048:
                self.reservedDoorSupportCache.pop(next(iter(self.reservedDoorSupportCache)))
            self.reservedDoorSupportCache[parentKey] = self.ReservedDoorSupport(parent, self.walls)
        return self.reservedDoorSupportCache[parentKey]

    def OpeningWallObstructs(self, opening, wall, walls = None, joined = True):
        if wall is opening.parentWall:
            return False
        overlap = self.JoinedObjectsOverlap if joined else self.ObjectsOverlap
        if isinstance(opening, PocketDoor) and type(wall) is Wall:
            parent = opening.parentWall
            contact = ReservedDoorWallContact((parent.firstVertex.x(), parent.firstVertex.y()),
                (parent.secondVertex.x(), parent.secondVertex.y()), parent.width,
                (wall.firstVertex.x(), wall.firstVertex.y()), (wall.secondVertex.x(), wall.secondVertex.y()),
                self.ReservedDoorSupport(parent, walls))
            if contact == "collinear":
                return False
            if contact == "branch":
                first, second = ((opening.centerFraction, opening.secondFraction) if opening.hingeAtSecond else
                                 (opening.firstFraction, opening.centerFraction))
                aperture = OpenDoorway(parent, first, second)
                aperture.geometryIssues = getattr(opening, "geometryIssues", ())
                return overlap(aperture, wall, contactTolerance = 1.0)
        return overlap(opening, wall, contactTolerance = 1.0)

    def OpeningTravelBounds(self, opening):
        if not isinstance(opening, PocketDoor):
            return 0, 1
        parent = opening.parentWall
        return ReservedDoorPlacementBounds(QtCore.QLineF(parent.firstVertex, parent.secondVertex).length(),
            opening.length, opening.hingeAtSecond, self.ReservedDoorSupport(parent))

    def OpeningLengthLimit(self, opening):
        parent = opening.parentWall
        end = 1.0
        if isinstance(opening, PocketDoor) and not opening.hingeAtSecond:
            end = min(self.ReservedDoorSupport(parent)[1], 2 - opening.firstFraction)
        return (end - opening.firstFraction) * QtCore.QLineF(parent.firstVertex, parent.secondVertex).length()

    def CollisionEnabled(self, first, second):
        return AllowsCollision(CollisionFlags(type(first)), CollisionFlags(type(second)),
                               getattr(self, "collisionSettings", collisionDefaults))

    def JoinedObjectsOverlap(self, first, second, contactTolerance = 1.0, excludedWalls = ()):
        if not self.CollisionEnabled(first, second):
            return False
        if ExcludesFootprintCollision(CollisionFlags(type(first)), CollisionFlags(type(second))):
            return False
        batch = getattr(self, "collisionPassCache", None)
        if batch is not None:
            # Candidate objects are temporary. Retain them for this pass so
            # Python cannot reuse their ids for another snap candidate.
            batch.setdefault("references", {}).update(((id(first), first), (id(second), second)))
        if batch is not None and "results" not in batch:
            diagnostics = getattr(self, "renderDiagnostics", None)
            diagnostics = diagnostics if diagnostics is not None and diagnostics.enabled else None
            started = perf_counter() if diagnostics is not None else None
            # Cached painting, hit testing and footprint-only work need no
            # collider scan. Prepare the defensive value key at the first pair
            # query, preserving direct edits and rigid-translation reuse.
            objects = self.walls + self.windows + self.furnishings
            geometryKey = tuple((id(obj), obj.firstVertex.x(), obj.firstVertex.y(),
                                 obj.secondVertex.x(), obj.secondVertex.y(), obj.width,
                                 getattr(obj, "firstMiter", None), getattr(obj, "secondMiter", None),
                                 (obj.depth, obj.depthOffset) if isinstance(obj, Fireplace) else None,
                                 (id(obj.definition), obj.flipHorizontal, obj.flipVertical)
                                 if isinstance(obj, Furnishing) and obj.definition.get("components") else None) for obj in objects)
            oldKey = getattr(self, "collisionResultKey", None)
            unchanged = oldKey is not None and self.WallTranslation(oldKey, geometryKey) is not None
            if not hasattr(self, "collisionPairKeys"):
                self.collisionPairKeys = {}
                self.collisionPairEpochs = {}
                self.collisionEpoch = 0
                self.collisionResults = {}
            if not unchanged:
                self.collisionEpoch += 1
            sceneIds = {id(obj) for obj in objects}
            if oldKey is not None and {entry[0] for entry in oldKey} != sceneIds:
                self.collisionResults = {key: value for key, value in self.collisionResults.items()
                                         if key[0] in sceneIds and key[1] in sceneIds and not key[3]}
                self.collisionPairKeys = {key: value for key, value in self.collisionPairKeys.items()
                                          if key in self.collisionResults}
                self.collisionPairEpochs = {key: value for key, value in self.collisionPairEpochs.items()
                                            if key in self.collisionResults}
            self.collisionResultKey = geometryKey
            batch.update(results = self.collisionResults, sceneIds = sceneIds, epoch = self.collisionEpoch)
            if diagnostics is not None:
                diagnostics.RecordPhase("collider-key", started)
        excludedKey = frozenset(excludedWalls)
        # Rigid scene movement preserves every pair. Other edits validate only
        # queried pairs against their actual bounds or joined path signatures.
        resultCache = (batch["results"] if batch is not None and id(first) in batch["sceneIds"]
                       and id(second) in batch["sceneIds"] else {})
        resultKey = (min(id(first), id(second)), max(id(first), id(second)), contactTolerance, excludedKey)
        pairKeys = self.collisionPairKeys if batch is not None and resultCache is batch["results"] else {}
        pairEpochs = self.collisionPairEpochs if batch is not None and resultCache is batch["results"] else {}
        epoch = batch["epoch"] if batch is not None else None
        if resultKey in resultCache and pairEpochs.get(resultKey) == epoch:
            return resultCache[resultKey]
        if self.ObjectsOverlap(first, second, contactTolerance = contactTolerance):
            resultCache[resultKey] = True
            pairEpochs[resultKey] = epoch
            pairKeys.pop(resultKey, None)
            return True
        bounds = [self.JoinedObjectBounds(obj, excludedKey) for obj in (first, second)]
        if not bounds[0].intersects(bounds[1]):
            resultCache[resultKey] = False
            pairEpochs[resultKey] = epoch
            pairKeys.pop(resultKey, None)
            return False
        paths = []
        cache = getattr(self, "collisionFootprintCache", {})
        for obj in (first, second):
            pathKey = (id(obj), excludedKey)
            if batch is not None and pathKey in batch.get("paths", {}):
                paths.append(batch["paths"][pathKey])
                continue
            if type(obj) in (Wall, Pillar, Column, Stair, Counter, Railing):
                category = Wall if type(obj) in (Wall, Pillar, Column) else type(obj)
                memberKey = (category, excludedKey)
                prepared = batch.get("members", {}).get(memberKey) if batch is not None else None
                if prepared is None:
                    members = tuple(wall for wall in self.walls if
                                    (type(wall) in (Wall, Pillar, Column) if category is Wall else type(wall) is category)
                                    and id(wall) not in excludedKey)
                    key = tuple((id(wall), wall.firstVertex.x(), wall.firstVertex.y(), wall.secondVertex.x(),
                                 wall.secondVertex.y(), wall.width, wall.firstMiter, wall.secondMiter) for wall in members)
                    prepared = (members, {id(wall) for wall in members}, key)
                    if batch is not None:
                        batch.setdefault("members", {})[memberKey] = prepared
                members, memberIds, key = prepared
                if id(obj) not in memberIds:
                    members += (obj,)
                    key += ((id(obj), obj.firstVertex.x(), obj.firstVertex.y(), obj.secondVertex.x(),
                             obj.secondVertex.y(), obj.width, obj.firstMiter, obj.secondMiter),)
                stored = cache.get(type(obj))
                if stored is None or stored[0] != key:
                    workspaces = getattr(self, "collisionWorkspaces", {})
                    # Contour tracing changes the exterior path, not ownership.
                    # Painting may already have prepared these exact fills.
                    # Different membership, hidden/excluded walls and direct
                    # model edits must still use independent collision geometry.
                    geometryKey = getattr(self, "wallGeometryKey", None)
                    if geometryKey == (self.basePixelsPerMillimeter, True, key) and not any(isinstance(wall, Column) for wall in members):
                        workspace = self
                    else:
                        workspace = workspaces.setdefault(type(obj), FootprintGeometry(self.basePixelsPerMillimeter))
                        workspace.ConnectedWallPath(members, traceContours = False)
                    self.collisionWorkspaces = workspaces
                    transform = QtGui.QTransform().scale(1 / self.basePixelsPerMillimeter, -1 / self.basePixelsPerMillimeter)
                    ownerPaths = {}
                    for owner, polygon in workspace.wallFillPolygons:
                        path = ownerPaths.setdefault(id(owner), QtGui.QPainterPath())
                        path.setFillRule(QtCore.Qt.FillRule.WindingFill)
                        path.addPolygon(transform.map(polygon))
                        path.closeSubpath()
                    for wallId, nativePath in workspace.columnMaterialPaths.items():
                        ownerPaths[wallId] = transform.map(nativePath)
                    cache[type(obj)] = (key, ownerPaths)
                paths.append(cache[type(obj)][1].get(id(obj), QtGui.QPainterPath()))
            else:
                path = QtGui.QPainterPath()
                if isinstance(obj, Furnishing) and obj.definition.get("components"):
                    path.setFillRule(QtCore.Qt.FillRule.WindingFill)
                    for bounds, corners, axes in FurnishingCollisionFootprints(obj):
                        path.addPolygon(QtGui.QPolygonF([QtCore.QPointF(*point) for point in corners]))
                        path.closeSubpath()
                else:
                    path.addPolygon(QtGui.QPolygonF(self.ObjectCorners(obj)))
                    path.closeSubpath()
                paths.append(path)
            if batch is not None:
                batch.setdefault("paths", {})[pathKey] = paths[-1]
        self.collisionFootprintCache = cache
        pathKeys = []
        for obj, path in zip((first, second), paths):
            pathKey = (id(obj), excludedKey)
            signature = batch.get("pathKeys", {}).get(pathKey) if batch is not None else None
            if signature is None:
                signature = tuple((element.x, element.y, element.type)
                                  for index in range(path.elementCount()) for element in (path.elementAt(index),))
                if batch is not None:
                    batch.setdefault("pathKeys", {})[pathKey] = signature
            pathKeys.append((id(obj), signature))
        pairKey = tuple(sorted(pathKeys))
        if pairKeys.get(resultKey) == pairKey and resultKey in resultCache:
            pairEpochs[resultKey] = epoch
            return resultCache[resultKey]
        pairKeys[resultKey] = pairKey
        pairEpochs[resultKey] = epoch
        if not paths[0].boundingRect().intersects(paths[1].boundingRect()):
            resultCache[resultKey] = False
            return False
        overlap = Paths.Intersection(paths[0], paths[1])
        if overlap.isEmpty():
            resultCache[resultKey] = False
            return False
        result = SignificantPathOverlap(([(point.x(), point.y()) for point in polygon]
                                         for polygon in Paths.FillPolygons(overlap)), contactTolerance)
        resultCache[resultKey] = result
        return result

    def JoinedObjectBounds(self, obj, excludedWalls = ()):
        """Conservative world bounds including arbitrary-length miter joins."""
        batch = getattr(self, "collisionPassCache", None)
        key = (id(obj), frozenset(excludedWalls))
        if batch is not None and key in batch.get("joinedBounds", {}):
            return batch["joinedBounds"][key]
        bounds = self.ObjectFootprint(obj)[0]
        if type(obj) in (Wall, Stair, Counter, Railing):
            category = type(obj)
            prepared = None
            if batch is not None:
                endpointKey = (category, frozenset(excludedWalls))
                prepared = batch.get("junctionEndpoints", {}).get(endpointKey)
                if prepared is None:
                    # Index a read-only validation pass once, preserving scene
                    # and endpoint order for the native junction calculation.
                    endpoints = [(wall, endpoint, far, miter) for wall in self.walls
                                 if type(wall) is category and id(wall) not in excludedWalls
                                 for endpoint, far, miter in ((wall.firstVertex, wall.secondVertex, wall.firstMiter),
                                                             (wall.secondVertex, wall.firstVertex, wall.secondMiter))]
                    endpointIndex = PrepareTargetIndex([(endpoint.x(), endpoint.y()) for wall, endpoint, far, miter in endpoints])
                    prepared = endpoints, endpointIndex
                    batch.setdefault("junctionEndpoints", {})[endpointKey] = prepared
            else:
                members = [wall for wall in self.walls if type(wall) is category and id(wall) not in excludedWalls and wall is not obj]
            for vertex, opposite, miter in ((obj.firstVertex, obj.secondVertex, obj.firstMiter),
                                              (obj.secondVertex, obj.firstVertex, obj.secondMiter)):
                delta = opposite - vertex
                length = math.hypot(delta.x(), delta.y())
                if length < 1e-10:
                    continue
                rays = [(delta / length, obj.width / 2, miter)]
                if prepared is not None:
                    endpoints, endpointIndex = prepared
                    nearby = (endpoints[index] for index in NearbyPointIndices(
                        (vertex.x(), vertex.y()), .02000001, endpointIndex))
                else:
                    nearby = ((other, endpoint, far, otherMiter) for other in members
                              for endpoint, far, otherMiter in ((other.firstVertex, other.secondVertex, other.firstMiter),
                                                                (other.secondVertex, other.firstVertex, other.secondMiter)))
                for other, endpoint, far, otherMiter in nearby:
                    if other is obj or QtCore.QLineF(vertex, endpoint).length() > .02000001:
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

    def WallTranslation(self, previous, current):
        delta = RigidTranslation(previous, current)
        return QtCore.QPointF(*delta) if delta is not None else None

    def ContainedWalls(self, walls = None):
        walls = [wall for wall in (self.walls if walls is None else walls) if not isinstance(wall, (Stair, Arrow, MeasurementGuide, Railing))]
        footprints = [self.ObjectFootprint(wall) for wall in walls]
        cacheKey = tuple((id(wall), wall.footprintCache[0]) for wall in walls)
        if cacheKey == self.containedWallKey:
            return self.containedWallCache
        contained = []
        tolerance = .01
        expandedBounds = [bounds.adjusted(-tolerance, -tolerance, tolerance, tolerance) for bounds, corners, axes in footprints]
        for index, wall in enumerate(walls):
            bounds, corners, axes = footprints[index]
            if not corners:
                continue
            for otherIndex, other in enumerate(walls):
                if index == otherIndex:
                    continue
                otherBounds, otherCorners, otherAxes = footprints[otherIndex]
                if not otherCorners or not expandedBounds[otherIndex].contains(bounds):
                    continue
                numericCorners, numericAxes = self.NumericCollisionFootprint(wall, footprints[index])
                otherNumericCorners, otherNumericAxes = self.NumericCollisionFootprint(other, footprints[otherIndex])
                containedOnAxes, equalBounds = FootprintContainment(numericCorners, otherNumericCorners,
                                                                   otherNumericAxes, tolerance)
                # Coincident duplicates flag the later wall, leaving one normal wall.
                if containedOnAxes and (not equalBounds or index > otherIndex):
                    contained.append(wall)
                    break
        self.containedWallKey = cacheKey
        self.containedWallCache = contained
        return contained

    def DuplicateFurnishings(self, includeHidden = False):
        """Flag front copies without changing placement validity or scene data."""
        ordered = sorted((obj for obj in self.furnishings if type(obj) is Furnishing and (includeHidden or self.IsObjectVisible(obj))),
                         key = lambda obj: not obj.behindCounters)
        seen, duplicates = set(), []
        for obj in ordered:
            key = (getattr(obj, "definitionKey", obj.definition["key"]), obj.firstVertex.x(), obj.firstVertex.y(),
                   obj.secondVertex.x(), obj.secondVertex.y(), obj.width, obj.flipHorizontal, obj.flipVertical)
            if key in seen:
                duplicates.append(obj)
            seen.add(key)
        return duplicates

    def DuplicateArchitecturalObjects(self, includeHidden = False):
        """Find front copies across all architectural types, including openings."""
        duplicates = []
        for group in self.CoincidentObjectGroups(includeHidden):
            obj = group[0]
            if isinstance(obj, Window) or type(obj) in (Wall, Pillar, Column, Counter, Stair, Railing, Elevator):
                duplicates.extend(group[1:])
        return duplicates

    def CoincidentObjectGroups(self, includeHidden = False):
        """Keep paint order and visual identity consistent for duplicate repairs."""
        from planner_app.project_codec import EncodeObjectRecord
        objects = self.walls + self.windows + sorted(self.furnishings, key = lambda obj: not obj.behindCounters) + self.labels
        indices = {id(obj): index for index, obj in enumerate(objects)}
        groups = {}
        def Records():
            for obj in objects:
                if not includeHidden and not self.IsObjectVisible(obj):
                    continue
                if type(obj) is Furnishing:
                    record = ("Furnishing", getattr(obj, "definitionKey", obj.definition["key"]), obj.firstVertex.x(), obj.firstVertex.y(),
                              obj.secondVertex.x(), obj.secondVertex.y(), obj.width, obj.flipHorizontal, obj.flipVertical)
                    # Preserve the furnishing fast path: no encoded dictionary,
                    # yielded pair or extra serialization is needed.
                    groups.setdefault(record, []).append(obj)
                else:
                    record = EncodeObjectRecord(obj, indices)
                    yield obj, record
        return GroupCoincidentRecords(Records(), groups = groups, consumeRecords = True)

    def WallPolygon(self, wall):
        if isinstance(wall, Column):
            return QtGui.QPolygonF([self.WorldToViewport(point) for point in ColumnPolygon(wall)])
        firstPoint = self.WorldToViewport(wall.firstVertex)
        secondPoint = self.WorldToViewport(wall.secondVertex)
        direction = secondPoint - firstPoint
        length = math.hypot(direction.x(), direction.y())
        if length == 0:
            return QtGui.QPolygonF()
        halfWidth = wall.width * self.basePixelsPerMillimeter * self.zoom / 2
        normal = QtCore.QPointF(-direction.y(), direction.x()) * (halfWidth / length)
        return QtGui.QPolygonF([firstPoint + normal, secondPoint + normal,
                               secondPoint - normal, firstPoint - normal])

    def HitTest(self, position):
        reference = getattr(self, "referenceImage", None)
        if reference is not None and reference.active:
            return None, None
        worldPosition = self.ViewportToWorld(position)
        origin = self.WorldToViewport(QtCore.QPointF())
        scale = self.basePixelsPerMillimeter * self.zoom
        worldTransform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(scale, -scale)
        # A collapsed opening still needs a usable hit area on either wall face,
        # even while its parent wall is selected and would otherwise win the hit.
        selectedIds = {id(obj) for obj, index in self.SelectionEntries()}
        for opening in reversed(self.windows):
            if id(opening) not in selectedIds and self.IsObjectVisible(opening) and opening.length * scale < 10:
                first, second = self.WorldToViewport(opening.firstVertex), self.WorldToViewport(opening.secondVertex)
                path = QtGui.QPainterPath()
                polygon = self.WallPolygon(opening)
                path.addPolygon(polygon)
                path.closeSubpath()
                if path.isEmpty():
                    direction = self.WorldToViewport(opening.parentWall.secondVertex) - self.WorldToViewport(opening.parentWall.firstVertex)
                    length = math.hypot(direction.x(), direction.y())
                    normal = QtCore.QPointF(-direction.y(), direction.x()) / max(length, 1e-8) * (opening.width * scale / 2)
                    path.moveTo(first - normal)
                    path.lineTo(first + normal)
                stroke = Paths.PrepareStroke(width = 10)
                if Paths.Contains(path, position) or Paths.Contains(stroke(path), position):
                    return opening, None
        for obj in reversed(self.furnishings):
            if isinstance(obj, NorthArrow) and self.IsObjectVisible(obj) and self.WallPolygon(obj).containsPoint(position, QtCore.Qt.FillRule.OddEvenFill):
                return obj, None
        for opening in reversed(self.windows):
            if opening.windowWell and self.IsObjectVisible(opening):
                well = WindowWellPath(opening.firstVertex, opening.secondVertex, opening.width,
                                      opening.wellDepth, swingsOutwards = not opening.swingsOutwards)
                if Paths.Contains(Paths.PrepareStroke(width = 10 / scale)(well), worldPosition):
                    return opening, None
        hitMargin = max(5, self.vertexSnapRange) / (self.basePixelsPerMillimeter * self.zoom)
        # Endpoint handles have a fixed screen-space hit area at every zoom.
        contained = list(reversed(self.ContainedWalls()))
        containedIds = {id(wall) for wall in contained}
        orderedWalls = contained + list(reversed(self.windows)) + [wall for wall in reversed(self.walls) if id(wall) not in containedIds]
        orderedWalls = [obj for obj in orderedWalls if self.IsObjectVisible(obj)]
        hitPillar = next((obj for obj in orderedWalls if isinstance(obj, Pillar)
                          and (ColumnPath(obj).boundingRect() if isinstance(obj, Column) else
                               self.ObjectFootprint(obj)[0]).contains(worldPosition)
                          and (ColumnContains(obj, worldPosition) if isinstance(obj, Column) else
                               self.WallPolygon(obj).containsPoint(position, QtCore.Qt.FillRule.OddEvenFill))), None)
        if any(isinstance(obj, Railing) for obj in orderedWalls):
            orderedWalls.sort(key = lambda obj: 0 if isinstance(obj, Window) or type(obj) in (Wall, Pillar, Column) else 1 if isinstance(obj, Railing) else 2)
        orderedWalls = [obj for obj in orderedWalls if isinstance(obj, (Arrow, BoundaryLine))] + [obj for obj in orderedWalls if not isinstance(obj, (Arrow, BoundaryLine))]
        arrows = [obj for obj in orderedWalls if isinstance(obj, Arrow)]
        arrowDirections = ConnectedArrowDirections(list(reversed(arrows)))
        arrowCorners = ConnectedArrowCorners(arrows, arrowDirections)
        # Control points precede line bodies, including annotations drawn inside
        # walls. Otherwise an active endpoint can hover visibly but clicking its
        # position selects the line crossing it instead.
        vertexMargin = hitMargin + max(.0001, 16 * math.ulp(worldPosition.x()), 16 * math.ulp(worldPosition.y()))
        vertexWalls = sorted(orderedWalls, key = lambda obj: 0 if obj is self.selectedWall else 1 if id(obj) in selectedIds else 2)
        for wall in vertexWalls:
            if isinstance(wall, (Pillar, Fireplace)) or isinstance(wall, Counter) and id(wall) not in selectedIds:
                continue
            if type(wall) is Wall and hitPillar is not None and id(wall) not in selectedIds:
                # Unselected wall endpoints hidden beneath a pillar remain hidden.
                continue
            for vertexIndex, vertex in enumerate(ObjectControlPoints(wall)):
                if abs(vertex.x() - worldPosition.x()) > vertexMargin or abs(vertex.y() - worldPosition.y()) > vertexMargin:
                    continue
                delta = position - self.WorldToViewport(vertex)
                if math.hypot(delta.x(), delta.y()) <= self.vertexSnapRange:
                    return wall, vertexIndex
        for guide in orderedWalls:
            if not isinstance(guide, BoundaryLine):
                continue
            path = QtGui.QPainterPath(self.WorldToViewport(guide.firstVertex))
            path.lineTo(self.WorldToViewport(guide.secondVertex))
            hitWidth = max(10, self.lineWidths[lineWeightClasses[guide.weightClass][1]]) if isinstance(guide, DashedLine) else 10
            if Paths.Contains(Paths.PrepareStroke(width = hitWidth)(path), position):
                return guide, None
        # A visible selection stays draggable through objects painted above it.
        selectedObjects = [obj for obj, index in reversed(self.SelectionEntries()) if self.IsObjectVisible(obj)]
        for obj in selectedObjects:
            # A wall selection must not cover its fireplace's visible body.
            if type(obj) is Wall and any(isinstance(child, Fireplace) and child.parentWall is obj
                                        and self.IsObjectVisible(child) and Paths.Contains(FireplacePath(child), worldPosition)
                                        for child in self.windows):
                continue
            if isinstance(obj, Column):
                if ColumnContains(obj, worldPosition):
                    return obj, None
                origin = self.WorldToViewport(QtCore.QPointF())
                path = QtGui.QTransform().translate(origin.x(), origin.y()).scale(
                    self.basePixelsPerMillimeter * self.zoom, -self.basePixelsPerMillimeter * self.zoom).map(ColumnPath(obj))
                stroke = Paths.PrepareStroke(width = 10)
                if Paths.Contains(stroke(path), position):
                    return obj, None
                continue
            if not isinstance(obj, (Furnishing, Label, Pillar, Fireplace)):
                for vertexIndex, vertex in enumerate(ObjectControlPoints(obj)):
                    if QtCore.QLineF(position, self.WorldToViewport(vertex)).length() <= self.vertexSnapRange:
                        return obj, vertexIndex
            if isinstance(obj, Arrow):
                first, second, showTip = arrowDirections[id(obj)]
                tail, head = ArrowPaths(self.WorldToViewport(first), self.WorldToViewport(second), obj.width,
                                        obj.solidTip, obj.tipSize, self.basePixelsPerMillimeter * self.zoom, showTip,
                                        [[self.WorldToViewport(point) for point in polygon] for polygon in arrowCorners[id(obj)]])
                path = QtGui.QPainterPath(tail)
                path.setFillRule(QtCore.Qt.FillRule.WindingFill)
                path.addPath(head)
            elif isinstance(obj, Fireplace):
                # Once selected, its full handle box remains draggable like furnishings.
                path = QtGui.QPainterPath()
                path.addPolygon(self.WallPolygon(obj.HandleBox()))
                path.closeSubpath()
            elif isinstance(obj, AngleGuide):
                path, labelRect, label, arcMiddle = self.AngleLayout(obj, selected = True)
                if labelRect.contains(position):
                    return obj, 3
            elif isinstance(obj, MeasurementGuide):
                labelPosition, angle, labelRect, labelPath = self.MeasurementLabelLayout(obj)
                if Paths.Contains(labelPath, position):
                    return obj, None if isinstance(obj, BoundaryLine) else 3
                first, last = self.WorldToViewport(obj.firstVertex), self.WorldToViewport(obj.secondVertex)
                path = QtGui.QPainterPath(first)
                path.lineTo(last)
                if type(obj) is MeasurementGuide and obj.depth != 0:
                    offset = QtCore.QPointF(*GuideDepthOffset((obj.firstVertex.x(), obj.firstVertex.y()),
                                                           (obj.secondVertex.x(), obj.secondVertex.y()), obj.depth))
                    for endpoint, screen in ((obj.firstVertex, first), (obj.secondVertex, last)):
                        path.moveTo(screen)
                        path.lineTo(self.WorldToViewport(endpoint + offset))
                if not isinstance(obj, BoundaryLine) and not obj.textOffset.isNull():
                    path.moveTo((first + last) / 2)
                    path.lineTo(labelPosition)
            else:
                bounds = self.ObjectFootprint(obj)[0].adjusted(-hitMargin, -hitMargin, hitMargin, hitMargin)
                if not bounds.contains(worldPosition):
                    continue
                path = QtGui.QPainterPath()
                path.addPolygon(self.WallPolygon(obj))
                path.closeSubpath()
            if Paths.Contains(path, position):
                return obj, None
            stroke = Paths.PrepareStroke(width = 10)
            if Paths.Contains(stroke(path), position):
                return obj, None
        for label in reversed(self.labels):
            if (self.IsObjectVisible(label) and self.ObjectFootprint(label)[0].contains(worldPosition)
                    and self.WallPolygon(label).containsPoint(position, QtCore.Qt.FillRule.OddEvenFill)):
                return label, None
        # Keep complete collections for connected geometry and draw-order rules,
        # but only construct screen polygons/strokes near the pointer. Arrow
        # heads and miter joins can extend beyond their rectangular footprints.
        candidates = []
        for obj in orderedWalls:
            margin = hitMargin + (max(obj.tipSize * 2, obj.width * 4) if isinstance(obj, Arrow) else 0)
            bounds = (ColumnPath(obj).boundingRect() if isinstance(obj, Column) else self.ObjectFootprint(obj)[0])
            bounds = bounds.adjusted(-margin, -margin, margin, margin)
            if isinstance(obj, Arrow):
                # A thin shaft can inherit a wide neighbor's miter triangle.
                for polygon in arrowCorners[id(obj)]:
                    bounds = bounds.united(QtGui.QPolygonF(polygon).boundingRect().adjusted(-hitMargin, -hitMargin, hitMargin, hitMargin))
            if bounds.contains(worldPosition):
                candidates.append(obj)
        for wall in candidates:
            if isinstance(wall, Fireplace):
                path = worldTransform.map(FireplacePath(wall))
                stroke = Paths.PrepareStroke(width = 10)
                if Paths.Contains(path, position) or Paths.Contains(stroke(path), position):
                    return wall, None
                continue
            if isinstance(wall, Column):
                if ColumnContains(wall, worldPosition):
                    return wall, None
                continue
            if isinstance(wall, Counter):
                continue
            if type(wall) is Wall and hitPillar is not None:
                continue
            if isinstance(wall, AngleGuide):
                path, labelRect, label, arcMiddle = self.AngleLayout(wall, selected = wall is getattr(self, "hoveredAngleGuide", None))
                if labelRect.contains(position):
                    return wall, 3
                if Paths.Contains(Paths.PrepareStroke(width = 10)(path), position):
                    return wall, None
                continue
            if isinstance(wall, MeasurementGuide):
                labelPosition, angle, labelRect, labelPath = self.MeasurementLabelLayout(wall)
                if not isinstance(wall, BoundaryLine) and Paths.Contains(labelPath, position):
                    return wall, 3
                first = self.WorldToViewport(wall.firstVertex)
                second = self.WorldToViewport(wall.secondVertex)
                path = QtGui.QPainterPath(first)
                path.lineTo(second)
                if type(wall) is MeasurementGuide and wall.depth != 0:
                    offset = QtCore.QPointF(*GuideDepthOffset((wall.firstVertex.x(), wall.firstVertex.y()),
                                                           (wall.secondVertex.x(), wall.secondVertex.y()), wall.depth))
                    for endpoint, screen in ((wall.firstVertex, first), (wall.secondVertex, second)):
                        path.moveTo(screen)
                        path.lineTo(self.WorldToViewport(endpoint + offset))
                if not isinstance(wall, BoundaryLine) and not wall.textOffset.isNull():
                    path.moveTo((first + second) / 2)
                    path.lineTo(labelPosition)
                hitWidth = max(10, self.lineWidths[lineWeightClasses[wall.weightClass][1]]) if isinstance(wall, DashedLine) else 10
                if Paths.Contains(Paths.PrepareStroke(width = hitWidth)(path), position):
                    return wall, None
                continue
            if isinstance(wall, Arrow):
                first, second, showTip = arrowDirections[id(wall)]
                tail, head = ArrowPaths(self.WorldToViewport(first), self.WorldToViewport(second), wall.width,
                                        wall.solidTip, wall.tipSize, self.basePixelsPerMillimeter * self.zoom, showTip,
                                        [[self.WorldToViewport(point) for point in polygon] for polygon in arrowCorners[id(wall)]])
                stroke = Paths.PrepareStroke(width = 10)
                path = QtGui.QPainterPath(tail)
                path.setFillRule(QtCore.Qt.FillRule.WindingFill)
                path.addPath(head)
                if Paths.Contains(path, position) or Paths.Contains(stroke(path), position):
                    return wall, None
                continue
            if self.WallPolygon(wall).containsPoint(position, QtCore.Qt.FillRule.OddEvenFill):
                return wall, None
            firstPoint = self.WorldToViewport(wall.firstVertex)
            direction = self.WorldToViewport(wall.secondVertex) - firstPoint
            lengthSquared = direction.x() ** 2 + direction.y() ** 2
            if lengthSquared:
                delta = position - firstPoint
                fraction = max(0, min(1, (delta.x() * direction.x() + delta.y() * direction.y()) / lengthSquared))
                distance = position - (firstPoint + direction * fraction)
                if math.hypot(distance.x(), distance.y()) <= 5:
                    return wall, None
        walls = [wall for wall in self.walls if type(wall) in (Wall, Pillar, Column) and self.IsObjectVisible(wall)]
        stairs = [wall for wall in self.walls if isinstance(wall, Stair) and self.IsObjectVisible(wall)]
        if stairs and Paths.Contains(self.ConnectedStairPath(stairs), position):
            nearest = min(stairs, key = lambda stair: min(QtCore.QLineF(position, self.WorldToViewport(vertex)).length()
                                                         for vertex in (stair.firstVertex, stair.secondVertex)))
            return nearest, None
        joinedHitWalls = [wall for wall in walls if not isinstance(wall, Column)]
        if joinedHitWalls and Paths.Contains(self.ConnectedWallPath(joinedHitWalls), position):
            # The extended corner belongs to its nearest adjoining wall.
            nearestWall = min(joinedHitWalls, key = lambda wall: min(
                QtCore.QLineF(position, self.WorldToViewport(wall.firstVertex)).length(),
                QtCore.QLineF(position, self.WorldToViewport(wall.secondVertex)).length()))
            return nearestWall, None
        railings = [obj for obj in self.walls if isinstance(obj, Railing) and self.IsObjectVisible(obj)]
        if railings:
            path, dimensions = self.ConnectedRailingPath(railings, includeMeasurements = False)
            if Paths.Contains(path, position):
                return min(railings, key = lambda obj: min(QtCore.QLineF(position, self.WorldToViewport(vertex)).length()
                            for vertex in (obj.firstVertex, obj.secondVertex))), None
        # Furnishings are below walls and stairs, but above counters.
        for obj in reversed(self.furnishings):
            if not self.IsObjectVisible(obj):
                continue
            if not self.ObjectFootprint(obj)[0].adjusted(-hitMargin, -hitMargin, hitMargin, hitMargin).contains(worldPosition):
                continue
            if type(obj) is Furnishing:
                if FurnishingContainsPoint(obj, self.furnishingRenderers[obj.definition["key"]], worldPosition, 5 / scale):
                    return obj, None
                continue
            footprint = QtGui.QPainterPath()
            footprint.addPolygon(self.WallPolygon(obj))
            footprint.closeSubpath()
            border = Paths.PrepareStroke(width = 10)
            if Paths.Contains(footprint, position) or Paths.Contains(border(footprint), position):
                return obj, None
        counters = [wall for wall in orderedWalls if isinstance(wall, Counter)]
        for counter in counters:
            if not self.ObjectFootprint(counter)[0].adjusted(-hitMargin, -hitMargin, hitMargin, hitMargin).contains(worldPosition):
                continue
            for vertexIndex, vertex in enumerate((counter.firstVertex, counter.secondVertex)):
                if QtCore.QLineF(position, self.WorldToViewport(vertex)).length() <= self.vertexSnapRange:
                    return counter, vertexIndex
            if self.WallPolygon(counter).containsPoint(position, QtCore.Qt.FillRule.OddEvenFill):
                return counter, None
        if counters:
            path, dimensions, polygons = self.ConnectedCounterPath(counters, includeMeasurements = False)
            if Paths.Contains(path, position):
                nearest = min(counters, key = lambda counter: min(
                    QtCore.QLineF(position, self.WorldToViewport(vertex)).length()
                    for vertex in (counter.firstVertex, counter.secondVertex)))
                return nearest, None
        selectedObjects = list({id(obj): obj for obj, index in self.SelectionEntries()}.values())
        if len(selectedObjects) > 1:
            corners = [corner for obj in selectedObjects for corner in self.ObjectCorners(obj)]
            if corners:
                bounds = QtCore.QRectF(QtCore.QPointF(min(corner.x() for corner in corners), min(corner.y() for corner in corners)),
                                      QtCore.QPointF(max(corner.x() for corner in corners), max(corner.y() for corner in corners)))
                if bounds.contains(self.ViewportToWorld(position)):
                    return self.selectedWall, None
        return None, None

    def ConnectedColumnWallPath(self, walls, traceContours):
        geometryKey = (self.basePixelsPerMillimeter, traceContours, tuple((id(wall), wall.firstVertex.x(),
            wall.firstVertex.y(), wall.secondVertex.x(), wall.secondVertex.y(), wall.width,
            wall.firstMiter, wall.secondMiter) for wall in walls))
        origin = self.WorldToViewport(QtCore.QPointF())
        viewTransform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
        if geometryKey == self.wallGeometryKey:
            return viewTransform.map(self.wallGeometryPath)
        if "columnWallWorkspace" not in self.__dict__:
            self.columnWallWorkspace = FootprintGeometry(self.basePixelsPerMillimeter, self)
        workspace = self.columnWallWorkspace
        workspace.basePixelsPerMillimeter = self.basePixelsPerMillimeter
        regularWalls = [wall for wall in walls if not isinstance(wall, Column)]
        workspace.ConnectedWallPath(regularWalls, traceContours)
        regularPath = workspace.wallGeometryPath
        transform = QtGui.QTransform().scale(self.basePixelsPerMillimeter, -self.basePixelsPerMillimeter)
        columns = [(wall, transform.map(ColumnPath(wall)).toReversed()) for wall in walls if isinstance(wall, Column)]
        columnFill = QtGui.QPainterPath()
        columnFill.setFillRule(QtCore.Qt.FillRule.WindingFill)
        for wall, path in columns:
            columnFill.addPath(path)
        # Curves stay native for paint and ownership. Qt's boolean union is
        # used only for the exterior footprint consumed by measurements.
        combined = QtGui.QPainterPath(regularPath)
        self.columnOutlinePaths = [(regularPath, columnFill)]
        for index, (wall, path) in enumerate(columns):
            if combined.boundingRect().intersects(path.boundingRect()):
                combined = Paths.Union(combined, path)
            else:
                combined.addPath(path)
            occluders = QtGui.QPainterPath(regularPath)
            for otherIndex, (other, otherPath) in enumerate(columns):
                if index != otherIndex and path.boundingRect().intersects(otherPath.boundingRect()):
                    occluders.addPath(otherPath)
            self.columnOutlinePaths.append((path, occluders))
        self.columnMaterialPaths = {id(wall): path for wall, path in columns}
        self.wallGeometryPath = combined
        self.wallFillPolygons = list(workspace.wallFillPolygons)
        # Collision ownership and measurement cutters still consume polygons;
        # generate them only here, using the cached world-tolerance footprint.
        self.wallFillPolygons.extend((wall, transform.map(ColumnPolygon(wall))) for wall, path in columns)
        self.wallGeometryComponents = []
        self.wallGeometryKey = geometryKey
        return viewTransform.map(combined)

    def ConnectedWallPath(self, walls, traceContours = True):
        if any(isinstance(wall, Column) for wall in walls):
            return self.ConnectedColumnWallPath(walls, traceContours)
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
            parents = list(range(count))
            active = []
            for index, bounds in sorted(entries, key = lambda entry: entry[1].left()):
                active = [(other, otherBounds) for other, otherBounds in active if otherBounds.right() >= bounds.left()]
                for other, otherBounds in active:
                    if index == other or not bounds.intersects(otherBounds):
                        continue
                    first, second = index, other
                    while parents[first] != first:
                        parents[first] = parents[parents[first]]
                        first = parents[first]
                    while parents[second] != second:
                        parents[second] = parents[parents[second]]
                        second = parents[second]
                    parents[first] = second
                active.append((index, bounds))
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
        for indices in components:
            key = (geometryKey[0], traceContours, tuple(geometryKey[2][index] for index in indices))
            cached = self.wallComponentCache.pop(key, None)
            if cached is None:
                self.BuildWallComponent([walls[index] for index in indices], traceContours)
                cached = (self.wallGeometryPath, self.wallFillPolygons)
            self.wallComponentCache[key] = cached
            results.append(cached)
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
                fragments = ownershipCache.pop(key, None)
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

    def BuildWallComponent(self, walls, traceContours):
        geometryKey = (self.basePixelsPerMillimeter, traceContours, tuple((id(wall), wall.firstVertex.x(), wall.firstVertex.y(),
                        wall.secondVertex.x(), wall.secondVertex.y(), wall.width, wall.firstMiter, wall.secondMiter) for wall in walls))
        origin = self.WorldToViewport(QtCore.QPointF())
        viewTransform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
        geometryScale = self.basePixelsPerMillimeter
        polygons = []
        polygonWalls = []
        materialCuts = {id(wall): [] for wall in walls}
        materialJoins = []
        materialTransitions = []
        # Polygon keys describe local inputs, independent of the component.
        # An endpoint edit should not clip every stationary owner's geometry.
        sectorCache = getattr(self, "wallSectorCache", None)
        if sectorCache is None:
            self.wallSectorCache = sectorCache = {}
            self.wallOwnershipCache = {}
            self.wallJunctionCache = {}
            self.wallBodyCache = {}
        for wall in walls:
            bodyKey = (geometryScale, type(wall), wall.firstVertex.x(), wall.firstVertex.y(),
                       wall.secondVertex.x(), wall.secondVertex.y(), wall.width)
            body = self.wallBodyCache.pop(bodyKey, None)
            if body is not None:
                self.wallBodyCache[bodyKey] = body
                polygons.append(body)
                polygonWalls.append(wall)
                continue
            if isinstance(wall, Column):
                transform = QtGui.QTransform().scale(geometryScale, -geometryScale)
                polygons.append(transform.map(ColumnPolygon(wall)))
                self.wallBodyCache[bodyKey] = polygons[-1]
                polygonWalls.append(wall)
                continue
            body = WallBody((wall.firstVertex.x() * geometryScale, -wall.firstVertex.y() * geometryScale),
                            (wall.secondVertex.x() * geometryScale, -wall.secondVertex.y() * geometryScale),
                            wall.width * geometryScale)
            if not body:
                continue
            polygons.append(QtGui.QPolygonF([QtCore.QPointF(*point) for point in body]))
            self.wallBodyCache[bodyKey] = polygons[-1]
            polygonWalls.append(wall)

        while len(self.wallBodyCache) > max(1024, len(walls) * 4):
            self.wallBodyCache.pop(next(iter(self.wallBodyCache)))

        # Group rays around each shared endpoint, then join only angular
        # neighbors. Pairwise joins between non-neighbors create outward spikes
        # when a third wall sits between the two outside walls.
        junctions = []
        junctionBuckets = {}
        for wall in walls:
            if isinstance(wall, Pillar):
                continue
            for vertex, otherVertex, miter in ((wall.firstVertex, wall.secondVertex, wall.firstMiter),
                                               (wall.secondVertex, wall.firstVertex, wall.secondMiter)):
                direction = QtCore.QPointF(otherVertex.x() - vertex.x(), vertex.y() - otherVertex.y())
                length = math.hypot(direction.x(), direction.y())
                if length == 0:
                    continue
                direction /= length
                halfWidth = wall.width * geometryScale / 2
                rays = None
                bucketX, bucketY = math.floor(vertex.x() / .01), math.floor(vertex.y() / .01)
                candidates = [index for x in range(bucketX - 1, bucketX + 2)
                              for y in range(bucketY - 1, bucketY + 2)
                              for index in junctionBuckets.get((x, y), ())]
                # Keep the original first-match order at tolerance boundaries.
                for jointIndex in sorted(candidates):
                    jointVertex, jointRays, jointMiters = junctions[jointIndex]
                    if QtCore.QLineF(vertex, jointVertex).length() <= 0.01:
                        rays = jointRays
                        jointMiters.append(miter)
                        break
                if rays is None:
                    rays = []
                    junctionBuckets.setdefault((bucketX, bucketY), []).append(len(junctions))
                    junctions.append((vertex, rays, [miter]))
                # Overlapping walls in the same direction contribute the widest
                # edge, avoiding duplicate rays hiding the exterior boundary.
                for rayIndex, (existingDirection, existingWidth, existingOwner) in enumerate(rays):
                    if QtCore.QLineF(direction, existingDirection).length() < 1e-6:
                        rays[rayIndex] = (existingDirection, max(halfWidth, existingWidth),
                                          wall if halfWidth > existingWidth else existingOwner)
                        break
                else:
                    rays.append((direction, halfWidth, wall))

        junctionCache = self.wallJunctionCache
        footprintCuts = {}
        for jointVertex, rays, jointMiters in junctions:
            if len(rays) < 2:
                continue
            key = (geometryScale, jointVertex.x(), jointVertex.y(), tuple(jointMiters),
                   tuple((direction.x(), direction.y(), width, id(owner)) for direction, width, owner in rays))
            cached = junctionCache.pop(key, None)
            if cached is None:
                cached = self.BuildWallJunction(jointVertex, rays, jointMiters)
            junctionCache[key] = cached
            joins, ownedJoins, transitions, cuts, footprintPlanes = cached
            polygons.extend(joins)
            materialJoins.extend(ownedJoins)
            materialTransitions.extend(transitions)
            for ownerId, entries in cuts.items():
                materialCuts[ownerId].extend(entries)
            for ownerId, entries in footprintPlanes.items():
                if entries:
                    footprintCuts.setdefault(ownerId, []).extend(entries)
        while len(junctionCache) > max(512, len(walls) * 4):
            junctionCache.pop(next(iter(junctionCache)))
        if footprintCuts:
            # Trim finite owner sources before both outline assembly and material
            # coverage. Otherwise an unequal-width body or the coverage fallback
            # can fill the corner back in after clipping the junction patch.
            sources = list(zip(polygonWalls, polygons[:len(polygonWalls)])) + materialJoins + materialTransitions
            clippedSources = []
            for sourceIndex, (owner, polygon) in enumerate(sources):
                planes = footprintCuts.get(id(owner), ())
                if planes:
                    coordinates = self.PreparedWallPolygon(polygon)[0]
                    key = ("footprint", coordinates, tuple(planes))
                    clipped = sectorCache.pop(key, None)
                    if clipped is None:
                        points = coordinates
                        for origin, normal in planes:
                            points = ClipHalfPlane(points, origin, normal)
                        clipped = QtGui.QPolygonF([QtCore.QPointF(*point) for point in points])
                    sectorCache[key] = clipped
                    polygon = clipped
                if sourceIndex >= len(polygonWalls):
                    # A seam can collapse an inner join triangle to a line.
                    # Such pieces have no fill and must not enter tracing or
                    # ownership indexing as extra overlapping contour sources.
                    coordinates = self.PreparedWallPolygon(polygon)[0]
                    area = sum(x * coordinates[(index + 1) % len(coordinates)][1]
                               - coordinates[(index + 1) % len(coordinates)][0] * y
                               for index, (x, y) in enumerate(coordinates))
                    if abs(area) <= 1e-9:
                        continue
                clippedSources.append((owner, polygon))
            polygons = [polygon for owner, polygon in clippedSources]
            materialJoins = clippedSources[len(polygonWalls):]
            materialTransitions = []
        # Preserve the original winding fill. Qt's path simplification can drop
        # entire wall bodies when several angled junctions form closed rooms.
        combinedPath = QtGui.QPainterPath()
        combinedPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
        tracePolygons = []
        for polygon in polygons:
            if len(polygon) < 3:
                continue
            polygon = self.PreparedWallPolygon(polygon)[2]
            combinedPath.addPolygon(polygon)
            combinedPath.closeSubpath()
            tracePolygons.append(polygon)
        if len(polygons) == 1 and not materialCuts[id(polygonWalls[0])]:
            # A lone rectangle or column ellipse already has its full exterior
            # and material ownership. Tracing it and subtracting its own fill
            # repeats expensive edge work on every translation.
            self.wallGeometryPath = combinedPath
            self.wallFillPolygons = [(polygonWalls[0], polygon)]
            self.wallGeometryKey = geometryKey
            return viewTransform.map(combinedPath)
        weldOptions = ({"weldTolerance": .01 * geometryScale} if any(isinstance(wall, Pillar) for wall in walls) else {})
        self.wallGeometryPath = (self.TraceWallBoundary(combinedPath, traceKey = ("walls", tuple(id(wall) for wall in walls)),
                                                      sourcePolygons = tracePolygons, **weldOptions)
                                 if traceContours else combinedPath)
        self.wallFillPolygons = []
        for owner, polygon in list(zip(polygonWalls, polygons[:len(polygonWalls)])) + materialJoins:
            # Clip rectangles and junction triangles to the owner's miter sector.
            # Doing this in cached world geometry avoids paint-order boundaries.
            polygonKey = self.PreparedWallPolygon(polygon)[0]
            cuts = materialCuts[id(owner)]
            sectorKey = (polygonKey, tuple((joint.x(), joint.y(), boundary.x(), boundary.y(), side)
                                          for joint, boundary, side in cuts))
            cached = sectorCache.pop(sectorKey, None)
            if cached is not None:
                sectorCache[sectorKey] = cached
                if len(cached) >= 3:
                    self.wallFillPolygons.append((owner, cached))
                continue
            points = list(polygon)
            for joint, boundary, side in materialCuts[id(owner)]:
                clipped = []
                for index, first in enumerate(points):
                    second = points[(index + 1) % len(points)]
                    firstOffset = first - joint
                    secondOffset = second - joint
                    firstDistance = (boundary.x() * firstOffset.y() - boundary.y() * firstOffset.x()) * side
                    secondDistance = (boundary.x() * secondOffset.y() - boundary.y() * secondOffset.x()) * side
                    if firstDistance >= -1e-8:
                        clipped.append(first)
                    if (firstDistance < -1e-8) != (secondDistance < -1e-8):
                        fraction = firstDistance / (firstDistance - secondDistance)
                        clipped.append(first + (second - first) * fraction)
                points = clipped
                if not points:
                    break
            clippedPolygon = QtGui.QPolygonF(points)
            sectorCache[sectorKey] = clippedPolygon
            if len(points) >= 3:
                self.wallFillPolygons.append((owner, clippedPolygon))
        self.wallFillPolygons.extend(materialTransitions)
        # Complete ownership from finite source polygons. Qt boolean operations
        # lose thin regions at acute angles, so subtract convex owner fragments
        # directly and assign every uncovered piece to its source wall.
        owned = []
        for owner, polygon in self.wallFillPolygons:
            polygonKey, bounds, normalized = self.PreparedWallPolygon(polygon)
            owned.append((polygon, bounds, polygonKey))
        sizes = sorted(max(bounds.width(), bounds.height()) for polygon, bounds, key in owned)
        ownedIndex = BoundsIndex(sizes[len(sizes) // 2] if sizes else 1)
        for polygon, bounds, key in owned:
            ownedIndex.Insert(bounds, (polygon, key))
        ownershipCache = self.wallOwnershipCache
        for owner, polygon in list(zip(polygonWalls, polygons[:len(polygonWalls)])) + materialJoins + materialTransitions:
            polygonKey, bounds, normalized = self.PreparedWallPolygon(polygon)
            cutters = ownedIndex.Query(bounds)
            ownershipKey = (polygonKey, tuple(key for cutter, key in cutters))
            fragments = ownershipCache.pop(ownershipKey, None)
            if fragments is None:
                fragments = [list(polygon)]
                for cutter, cutterKey in cutters:
                    fragments = [piece for fragment in fragments for piece in SubtractConvexPolygon(fragment, cutter)]
                    if not fragments:
                        break
                fragments = tuple(QtGui.QPolygonF(fragment) for fragment in fragments if len(fragment) >= 3)
            ownershipCache[ownershipKey] = fragments
            additions = [(owner, fragment) for fragment in fragments]
            self.wallFillPolygons.extend(additions)
            for owner, fragment in additions:
                fragmentKey, fragmentBounds, normalized = self.PreparedWallPolygon(fragment)
                ownedIndex.Insert(fragmentBounds, (fragment, fragmentKey))
        for cache in (self.wallBodyCache, sectorCache, ownershipCache):
            while len(cache) > max(1024, len(walls) * 16):
                cache.pop(next(iter(cache)))
        self.wallFillPolygons = [(owner, self.PreparedWallPolygon(polygon)[2]) for owner, polygon in self.wallFillPolygons]
        if all(type(wall) in (Counter, Stair) for wall in walls):
            self.PreserveRunSideSeams()
        self.wallGeometryKey = geometryKey
        return viewTransform.map(self.wallGeometryPath)

    def PreserveRunSideSeams(self):
        """Keep side contact visible even in an end-connected U-shaped chain."""
        scale = self.basePixelsPerMillimeter
        tolerance = .01 * scale
        widths = sorted({owner.width * scale for owner, polygon in self.wallFillPolygons})
        index = BoundsIndex(widths[len(widths) // 2] if widths else 1)
        seams = set()
        for owner, polygon in self.wallFillPolygons:
            delta = owner.secondVertex - owner.firstVertex
            length = math.hypot(delta.x(), delta.y())
            if length < .0001:
                continue
            axis = QtCore.QPointF(delta.x(), -delta.y()) / length
            origin = QtCore.QPointF(owner.firstVertex.x(), -owner.firstVertex.y()) * scale
            vertices = list(polygon)
            for first, second in zip(vertices, vertices[1:] + vertices[:1]):
                edge = second - first
                edgeLength = math.hypot(edge.x(), edge.y())
                midpoint = (first + second) / 2
                across = abs((midpoint.x() - origin.x()) * axis.y() - (midpoint.y() - origin.y()) * axis.x())
                if edgeLength < tolerance or abs(edge.x() * axis.y() - edge.y() * axis.x()) > tolerance or abs(across - owner.width * scale / 2) > tolerance:
                    continue
                direction = edge / edgeLength
                bounds = QtCore.QRectF(first, second).normalized().adjusted(-tolerance, -tolerance, tolerance, tolerance)
                for other, start, end in index.Query(bounds):
                    if other is owner:
                        continue
                    if abs((start.x() - first.x()) * direction.y() - (start.y() - first.y()) * direction.x()) > tolerance:
                        continue
                    if abs((end.x() - first.x()) * direction.y() - (end.y() - first.y()) * direction.x()) > tolerance:
                        continue
                    limits = sorted((QtCore.QPointF.dotProduct(start - first, direction), QtCore.QPointF.dotProduct(end - first, direction)))
                    low, high = max(0, limits[0]), min(edgeLength, limits[1])
                    if high - low <= tolerance:
                        continue
                    a, b = first + direction * low, first + direction * high
                    normal = QtCore.QPointF(-direction.y(), direction.x()) * tolerance
                    center = (a + b) / 2
                    if not (self.wallGeometryPath.contains(center + normal) and self.wallGeometryPath.contains(center - normal)):
                        continue
                    key = tuple(sorted(((round(a.x(), 8), round(a.y(), 8)), (round(b.x(), 8), round(b.y(), 8)))))
                    if key not in seams:
                        seams.add(key)
                        self.wallGeometryPath.moveTo(a)
                        self.wallGeometryPath.lineTo(b)
                index.Insert(bounds, (owner, first, second))

    def PreparedWallPolygon(self, polygon):
        """Memoize metadata for immutable polygons owned by the geometry caches."""
        cache = getattr(self, "wallPolygonCache", None)
        if cache is None:
            self.wallPolygonCache = cache = {}
        if not cache:
            self.wallPolygonPointCount = 0
        stored = cache.pop(id(polygon), None)
        if stored is not None and stored[0] is polygon:
            cache[id(polygon)] = stored
            return stored[1]
        if stored is not None:
            self.wallPolygonPointCount -= len(stored[1][0])
        coordinates = tuple((point.x(), point.y()) for point in polygon)
        area = sum(firstX * coordinates[(index + 1) % len(coordinates)][1]
                   - coordinates[(index + 1) % len(coordinates)][0] * firstY
                   for index, (firstX, firstY) in enumerate(coordinates))
        normalized = QtGui.QPolygonF(list(reversed(polygon))) if area < 0 else polygon
        data = (coordinates, polygon.boundingRect(), normalized)
        if len(coordinates) <= 65536:
            cache[id(polygon)] = (polygon, data)
            self.wallPolygonPointCount += len(coordinates)
            while len(cache) > 4096 or self.wallPolygonPointCount > 65536:
                source, evicted = cache.pop(next(iter(cache)))
                self.wallPolygonPointCount -= len(evicted[0])
        return data

    def BuildWallJunction(self, jointVertex, rays, jointMiters):
        """Adapt wall identities and Qt points to numeric junction construction."""
        scale = self.basePixelsPerMillimeter
        joint = (jointVertex.x() * scale, -jointVertex.y() * scale)
        owners = {id(owner): owner for direction, width, owner in rays}
        numericRays = [((direction.x(), direction.y()), width, id(owner)) for direction, width, owner in rays]
        polygons, joins, transitions, cuts, footprintPlanes = BuildNumericWallJunction(joint, numericRays, jointMiters, max(.0001, .01 * scale))
        # The original method sorts its caller's rays in place.
        rays.sort(key = lambda ray: math.atan2(ray[0].y(), ray[0].x()))
        polygons = [QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in polygon]) for polygon in polygons]
        joins = [(owners[owner], QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in polygon])) for owner, polygon in joins]
        transitions = [(owners[owner], QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in polygon])) for owner, polygon in transitions]
        cuts = {owner: [(QtCore.QPointF(*joint), QtCore.QPointF(*boundary), side) for joint, boundary, side in entries]
                for owner, entries in cuts.items()}
        return polygons, joins, transitions, cuts, footprintPlanes

    def ConnectedRailingPath(self, railings, includeMeasurements = True):
        if not hasattr(self, "railingWorkspace"):
            self.railingWorkspace = FootprintGeometry(self.basePixelsPerMillimeter, self)
        workspace = self.railingWorkspace
        workspace.zoom = self.zoom
        footprint = workspace.ConnectedWallPath(railings)
        key = tuple((id(obj), obj.firstVertex.x(), obj.firstVertex.y(), obj.secondVertex.x(), obj.secondVertex.y(),
                     obj.width, obj.firstMiter, obj.secondMiter, obj.postCount) for obj in railings)
        if key != getattr(self, "railingSymbolKey", None):
            symbol = QtGui.QPainterPath()
            symbol.setFillRule(QtCore.Qt.FillRule.WindingFill)
            transform = QtGui.QTransform().scale(self.basePixelsPerMillimeter, -self.basePixelsPerMillimeter)
            # A shared endpoint owns one post, even if multiple runs meet there.
            posts = []
            for railing in railings:
                run = railing.secondVertex - railing.firstVertex
                length = math.hypot(run.x(), run.y())
                if length < 1e-10:
                    continue
                direction = run / length
                normal = QtCore.QPointF(-direction.y(), direction.x())
                offset = normal * (railing.width * .75 / 2)
                bar = QtGui.QPainterPath()
                bar.addPolygon(transform.map(QtGui.QPolygonF([railing.firstVertex - offset, railing.secondVertex - offset,
                    railing.secondVertex + offset, railing.firstVertex + offset])))
                bar.closeSubpath()
                symbol = Paths.Union(symbol, bar)
                for index in range(railing.postCount):
                    center = railing.firstVertex + run * (index / (railing.postCount - 1))
                    existing = next((post for post in posts if QtCore.QLineF(center, post[0]).length() <= .01), None)
                    if existing is None:
                        posts.append([center, direction, normal, railing.width])
                    elif railing.width > existing[3]:
                        existing[1:] = [direction, normal, railing.width]
            postOutlines = QtGui.QPainterPath()
            for center, direction, normal, width in posts:
                a, b = direction * (width / 2), normal * (width / 2)
                post = QtGui.QPainterPath()
                post.addPolygon(transform.map(QtGui.QPolygonF([center - a - b, center + a - b, center + a + b, center - a + b])))
                post.closeSubpath()
                postOutlines.addPath(post)
                symbol = Paths.Union(symbol, post)
            self.railingSymbolKey, self.railingSymbolPath = key, symbol
            self.railingPostOutlinePath = postOutlines
        origin = self.WorldToViewport(QtCore.QPointF())
        transform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
        dimensions = workspace.WallDimensions(railings, footprint, [], cachedBoundary = True) if includeMeasurements else []
        return transform.map(self.railingSymbolPath), dimensions

    def ConnectedStairPath(self, stairs):
        if not hasattr(self, "stairWorkspace"):
            self.stairWorkspace = FootprintGeometry(self.basePixelsPerMillimeter, self)
        workspace = self.stairWorkspace
        workspace.zoom = self.zoom
        previousKey = workspace.wallGeometryKey
        path = workspace.ConnectedWallPath(stairs)
        if previousKey != workspace.wallGeometryKey:
            outline = workspace.wallGeometryPath
            self.stairOutlinePath = QtGui.QPainterPath()
            lines = []
            seen = set()
            first = None
            for index in range(outline.elementCount()):
                element = outline.elementAt(index)
                point = QtCore.QPointF(element.x, element.y)
                if element.isLineTo() and first is not None:
                    key = tuple(sorted(((round(first.x(), 8), round(first.y(), 8)), (round(point.x(), 8), round(point.y(), 8)))))
                    if key not in seen:
                        seen.add(key)
                        lines.append(QtCore.QLineF(first, point))
                        self.stairOutlinePath.moveTo(first)
                        self.stairOutlinePath.lineTo(point)
                first = point
            self.stairOutlineLines = lines
            self.stairInsetLines = StairInsetLines(workspace.wallGeometryComponents, workspace.wallFillPolygons, self.basePixelsPerMillimeter)
            self.stairLandingCache = {}
        self.stairGeometryKey, self.stairGeometryPath = workspace.wallGeometryKey, workspace.wallGeometryPath
        self.stairGeometryComponents = workspace.wallGeometryComponents
        return path

    def StairDimensions(self, stairs):
        if not hasattr(self, "stairMeasurementWorkspace"):
            self.stairMeasurementWorkspace = FootprintGeometry(self.basePixelsPerMillimeter, self)
        workspace = self.stairMeasurementWorkspace
        workspace.zoom = self.zoom
        # The stair fill contains overlapping rectangles and landing triangles.
        # Measurements need the exterior contour, as counters do, rather than
        # measuring those internal subpaths. Keep the rendering cache separate.
        path = workspace.ConnectedWallPath(stairs)
        blockers = [self.ObjectCorners(obj) for obj in self.walls
                    if not isinstance(obj, (Stair, Arrow, MeasurementGuide)) and self.IsObjectVisible(obj)]
        return workspace.WallDimensions(stairs, path, [], cachedBoundary = True,
                                        measureCaps = True, blockers = blockers)

    def ConnectedCounterPath(self, counters, includeMeasurements = True):
        if not hasattr(self, "counterWorkspace"):
            self.counterWorkspace = FootprintGeometry(self.basePixelsPerMillimeter, self)
        workspace = self.counterWorkspace
        workspace.preparedWallMembers = counters if counters is getattr(self, "preparedCounterMembers", None) else None
        workspace.zoom = self.zoom
        path = workspace.ConnectedWallPath(counters)
        blockers = [self.ObjectCorners(obj) for obj in self.walls
                    if not isinstance(obj, (Counter, Arrow, MeasurementGuide)) and self.IsObjectVisible(obj)] if includeMeasurements else []
        dimensions = workspace.WallDimensions(counters, path, [], cachedBoundary = True,
                                              measureCaps = True, blockers = blockers) if includeMeasurements else []
        self.counterGeometryCache = {"wallGeometryKey": workspace.wallGeometryKey,
                                     "wallGeometryPath": workspace.wallGeometryPath, "dimensionCache": workspace.dimensionCache}
        return path, dimensions, workspace.wallFillPolygons

    def StairLandingTrims(self, stair, stairs):
        if id(stair) not in self.stairLandingCache:
            self.stairLandingCache[id(stair)] = stair.LandingTrims(stairs)
        return self.stairLandingCache[id(stair)]

    def PreparedWallContour(self, polygon, canonical = False):
        """Retain Qt's closed contour and edge metadata for immutable inputs."""
        source = polygon
        if not canonical:
            cache = self.wallContourCache
            stored = cache.pop(id(source), None)
            if stored is not None:
                self.wallContourCachePoints -= stored[2]
                if stored[0] is source:
                    cache[id(source)] = stored
                    self.wallContourCachePoints += stored[2]
                    return stored[1]
            path = QtGui.QPainterPath()
            path.addPolygon(polygon)
            path.closeSubpath()
            contours = Paths.Contours(path)
            polygon = contours[0] if contours else QtGui.QPolygonF()
        edges, coordinates = [], []
        for index in range(len(polygon) - 1):
            first, second = polygon[index], polygon[index + 1]
            if QtCore.QLineF(first, second).length() > 1e-9:
                edges.append((first, second))
                coordinates.append((first.x(), first.y(), second.x(), second.y()))
        bounds = polygon.boundingRect()
        data = (polygon, (bounds.left(), bounds.top(), bounds.right(), bounds.bottom(), tuple(coordinates)), tuple(edges))
        if not canonical:
            points = len(source) + len(polygon) + len(edges) * 4
            if points <= 32768:
                cache[id(source)] = (source, data, points)
                self.wallContourCachePoints += points
                while len(cache) > 2048 or self.wallContourCachePoints > 32768:
                    source, unusedData, evictedPoints = cache.pop(next(iter(cache)))
                    self.wallContourCachePoints -= evictedPoints
        return data

    def TraceWallBoundary(self, filledPath, joinContours = True, traceKey = None, sourcePolygons = None, weldTolerance = 0.0):
        prepared = ([self.PreparedWallContour(polygon) for polygon in sourcePolygons] if sourcePolygons is not None else
                    [self.PreparedWallContour(polygon, canonical = True) for polygon in Paths.Contours(filledPath)])
        prepared = [data for data in prepared if not data[0].isEmpty()]
        if not prepared:
            return QtGui.QPainterPath()
        margin = max(1e-8, weldTolerance / 2)
        bounds = [polygon.boundingRect().adjusted(-margin, -margin, margin, margin) for polygon, contour, edges in prepared]
        components = GroupContourBounds([(rect.left(), rect.top(), rect.right(), rect.bottom()) for rect in bounds])
        outline = QtGui.QPainterPath()
        outline.setFillRule(QtCore.Qt.FillRule.WindingFill)
        for indices in components:
            key = (joinContours, filledPath.fillRule(), weldTolerance,
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
                    preparedContours = [prepared[index] for index in indices],
                    **({"weldTolerance": weldTolerance} if weldTolerance else {}))
            self.wallBoundaryCache[key] = component
            outline.addPath(component)
        while len(self.wallBoundaryCache) > 128:
            self.wallBoundaryCache.pop(next(iter(self.wallBoundaryCache)))
        return outline

    def TraceWallComponent(self, filledPath, joinContours = True, traceKey = None, preparedContours = None, weldTolerance = 0.0):
        """Adapt canonical contours and retain bounded, numeric trace histories."""
        if preparedContours is None:
            preparedContours = [self.PreparedWallContour(polygon, canonical = True) for polygon in Paths.Contours(filledPath)]
        fillContours = [contour for polygon, contour, edges in preparedContours]
        if not any(contour[4] for contour in fillContours):
            return QtGui.QPainterPath()
        contexts = getattr(self, "wallTraceContexts", None)
        if contexts is None:
            self.wallTraceContexts = contexts = {}
            self.wallTraceContextPoints = 0
        stored = contexts.pop(traceKey, None) if traceKey is not None else None
        if stored is not None:
            self.wallTraceContextPoints -= stored[1]
        state = self.wallTraceState if traceKey is None else stored[0] if stored is not None else None
        bounds = filledPath.boundingRect()
        contours, state = TraceBoundaryContours(fillContours, (bounds.width(), bounds.height()), joinContours,
                                               filledPath.fillRule().value, state, self.wallBoundaryEdgeCache, weldTolerance = weldTolerance)
        if traceKey is None:
            self.wallTraceState = state
        else:
            contourCounts, edgeValues = state[1:]
            points = sum(len(contour[4]) * 2 for contour in contourCounts) + len(edgeValues) * 2
            points += sum(len(segments) * 2 for segments in edgeValues.values())
            if points <= 32768:
                contexts[traceKey] = (state, points)
                self.wallTraceContextPoints += points
                while len(contexts) > 8 or self.wallTraceContextPoints > 32768:
                    evicted, size = contexts.pop(next(iter(contexts)))
                    self.wallTraceContextPoints -= size
        outline = QtGui.QPainterPath()
        if joinContours:
            outline.setFillRule(QtCore.Qt.FillRule.WindingFill)
            for points in contours:
                outline.addPolygon(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points]))
                outline.closeSubpath()
        else:
            for first, second in contours:
                outline.moveTo(QtCore.QPointF(*first))
                outline.lineTo(QtCore.QPointF(*second))
        return outline

    def WallDimensions(self, walls, boundaryPath, openings = None, cachedBoundary = False,
                       measureCaps = False, blockers = (), measurementSettings = None):
        settings = EffectiveWallSplitSettings(self.measurementSettings if measurementSettings is None else measurementSettings, getattr(self, "wallMeasurementMode", "All"))
        cutters = []
        if walls and type(walls[0]) in (Wall, Pillar, Column, Railing):
            if not hasattr(self, "measurementCutterWorkspaces"):
                self.measurementCutterWorkspaces = {}
            toWorld = QtGui.QTransform().scale(1 / self.basePixelsPerMillimeter, -1 / self.basePixelsPerMillimeter)
            for objectClass, key in ((Stair, "stairs"), (Counter, "counters")):
                if settings[key] != 0:
                    continue
                members = [obj for obj in self.walls if isinstance(obj, objectClass) and self.IsObjectVisible(obj)]
                if not members:
                    continue
                workspace = self.measurementCutterWorkspaces.get(key)
                if workspace is None:
                    workspace = FootprintGeometry(self.basePixelsPerMillimeter, self)
                    self.measurementCutterWorkspaces[key] = workspace
                workspace.ConnectedWallPath(members, traceContours = False)
                # Use the joined, owned footprint pieces: endpoint rectangles
                # alone stop at control vertices and omit the corner/landing.
                for owner, polygon in workspace.wallFillPolygons:
                    area = sum(point.x() * polygon[(index + 1) % len(polygon)].y() -
                               polygon[(index + 1) % len(polygon)].x() * point.y()
                               for index, point in enumerate(polygon))
                    # Shared material/join seams may be zero-area polygons.
                    # They are not footprints and must not cut a distant edge.
                    if abs(area) > 1e-8:
                        cutters.append(toWorld.map(polygon))
        components = self.wallGeometryComponents
        if not cachedBoundary or len(components) < 2:
            return self.BuildWallDimensions(walls, boundaryPath, openings, cachedBoundary, measureCaps, blockers, cutters, measurementSettings)
        doors = list(self.windows if openings is None else openings)
        blockerKey = tuple(tuple((point.x(), point.y()) for point in polygon) for polygon in blockers)
        cutterKey = tuple(tuple((point.x(), point.y()) for point in polygon) for polygon in cutters)
        origin = self.WorldToViewport(QtCore.QPointF())
        transform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
        dimensions = []
        # World dimensions never depend on the selection overlay.
        plans = PlanMeasurementComponents(((id(wall) for wall in members) for geometryKey, members, path in components),
                                          (id(door.parentWall) for door in doors), ())
        settingsKey = tuple(sorted(settings.items()))
        for (geometryKey, members, path), (doorIndices, unusedSelectedKeys) in zip(components, plans):
            componentDoors = [doors[index] for index in doorIndices]
            doorKey = tuple((id(door), type(door), door.firstFraction, door.secondFraction,
                             getattr(door, "hingeAtSecond", None), getattr(door, "swingsOutwards", None),
                             getattr(door, "panelsFlipped", None), door.measurementFlipped,
                             (door.depth, door.depthOffset) if isinstance(door, Fireplace) else None) for door in componentDoors)
            key = (geometryKey, doorKey, settingsKey, measureCaps, blockerKey, cutterKey)
            cached = self.wallDimensionComponentCache.pop(key, None)
            if cached is None:
                cached = self.BuildWallDimensions(members, transform.map(path), componentDoors,
                                                   measureCaps = measureCaps, blockers = blockers, cutters = cutters,
                                                   measurementSettings = measurementSettings)
            self.wallDimensionComponentCache[key] = cached
            dimensions.extend(cached)
        while len(self.wallDimensionComponentCache) > max(128, len(components) * 2):
            self.wallDimensionComponentCache.pop(next(iter(self.wallDimensionComponentCache)))
        self.dimensionCacheKey = None
        self.dimensionCache = dimensions
        return dimensions

    def BuildWallDimensions(self, walls, boundaryPath, openings = None, cachedBoundary = False,
                            measureCaps = False, blockers = (), cutters = (), measurementSettings = None):
        settings = EffectiveWallSplitSettings(self.measurementSettings if measurementSettings is None else measurementSettings, getattr(self, "wallMeasurementMode", "All"))
        doors = list(self.windows if openings is None else openings)
        wallKey = tuple((id(wall), wall.firstVertex.x(), wall.firstVertex.y(), wall.secondVertex.x(),
                         wall.secondVertex.y(), wall.width, wall.firstMiter, wall.secondMiter) for wall in walls)
        doorKey = tuple((id(door), type(door), id(door.parentWall), door.firstFraction, door.secondFraction,
                         (door.hingeAtSecond, door.swingsOutwards) if isinstance(door, BarnDoor) else
                         door.swingsOutwards if type(door) in (Window, Door, DoubleDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, BifoldDoor) else
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
                    tuple(boundaryKey), tuple(sorted(settings.items())),
                    measureCaps, blockerKey, cutterKey)
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
        axisValues = {}
        for entry in wallAxes:
            wall, firstX, firstY, axisX, axisY, wallLength, halfWidth = entry
            secondX, secondY = firstX + axisX * wallLength, firstY + axisY * wallLength
            extent = abs(halfWidth)
            bounds = QtCore.QRectF(min(firstX, secondX) - abs(axisY) * extent,
                                  min(firstY, secondY) - abs(axisX) * extent,
                                  abs(secondX - firstX) + 2 * abs(axisY) * extent,
                                  abs(secondY - firstY) + 2 * abs(axisX) * extent)
            bounds = bounds.adjusted(-.01, -.01, .01, .01)
            axisIndex.Insert(bounds, entry)
            axisValues[id(wall)] = ((type(wall),) + entry[1:], bounds)
        ownerStateKey = (measureCaps, tuple(id(entry[0]) for entry in wallAxes))
        state = self.dimensionOwnerState
        previousSpans = {}
        changedAxes = []
        if state is not None and state[0] == ownerStateKey:
            # Only changed wall axes can alter the ordered candidate set of an
            # unchanged span. Use the same expanded bounds as the exact query.
            previousSpans = state[2]
            for identity, (value, bounds) in axisValues.items():
                oldValue, oldBounds = state[1][identity]
                if value != oldValue:
                    changedAxes.extend((oldBounds, bounds))
        ownerSpans = {}
        ownerCache = getattr(self, "dimensionOwnerCache", None)
        if ownerCache is None:
            self.dimensionOwnerCache = ownerCache = {}
        spanCache = getattr(self, "dimensionSpanCache", None)
        if spanCache is None:
            self.dimensionSpanCache = spanCache = {}
            self.dimensionSpanCachePoints = 0
        if not spanCache:
            self.dimensionSpanCachePoints = 0
        doorsByWall = {}
        openingVertices = {}
        openingKeys = {}
        for index, door in enumerate(doors):
            doorsByWall.setdefault(id(door.parentWall), []).append(index)
            first, second = door.firstVertex, door.secondVertex
            openingVertices[id(door)] = first, second
            openingKeys[id(door)] = (id(door), doorKey[index], door.measurementFlipped,
                                     first.x(), first.y(), second.x(), second.y())
        settingsKey = tuple(sorted(settings.items()))
        openingRecords = {}
        dimensions = []
        preparedCutters = PrepareMeasurementPolygons([[(point.x(), point.y()) for point in cutter] for cutter in cutters])
        for polygon in Paths.Contours(worldTransform.map(boundaryPath)):
            segments = MergeMeasurementSegments([(point.x(), point.y()) for point in polygon])
            segments = [(QtCore.QPointF(*first), QtCore.QPointF(*second), QtCore.QPointF(*direction))
                        for first, second, direction in segments]
            for first, second, direction in segments:
                owners = []
                midpoint = (first + second) / 2
                firstX, firstY = first.x(), first.y()
                secondX, secondY = second.x(), second.y()
                directionX, directionY = direction.x(), direction.y()
                # The exact owner predicate allows a small angular tolerance.
                # Include its maximum drift along long spans in the broad phase.
                margin = max(.02 + QtCore.QLineF(first, second).length() * 1e-6,
                             16 * max(math.ulp(value) for value in (firstX, firstY, secondX, secondY)))
                spanBounds = QtCore.QRectF(first, second).normalized().adjusted(-margin, -margin, margin, margin)
                spanIdentity = (measureCaps, firstX, firstY, secondX, secondY)
                previous = previousSpans.get(spanIdentity)
                if previous is not None and not any(spanBounds.intersects(bounds) for bounds in changedAxes):
                    ownerKey, cached = previous
                else:
                    candidates = axisIndex.Query(spanBounds)
                    ownerKey = spanIdentity + (tuple((id(wall), type(wall), wallX, wallY, axisX, axisY, wallLength, halfWidth)
                                      for wall, wallX, wallY, axisX, axisY, wallLength, halfWidth in candidates),)
                    cached = ownerCache.get(ownerKey)
                ownerCache.pop(ownerKey, None)
                if cached is not None:
                    owners = list(cached)
                else:
                    ownerIndices = FindMeasurementOwners((firstX, firstY), (secondX, secondY), (directionX, directionY),
                        [(index, wallX, wallY, axisX, axisY, wallLength, halfWidth, measureCaps or isinstance(wall, Pillar))
                         for index, (wall, wallX, wallY, axisX, axisY, wallLength, halfWidth) in enumerate(candidates)])
                    owners = [candidates[index][0] for index in ownerIndices]
                ownerCache[ownerKey] = tuple(owners)
                ownerSpans[spanIdentity] = (ownerKey, tuple(owners))
                # Walls measure long sides; counters also measure exposed end caps.
                if owners:
                    ownerDoors = [doors[index] for index in sorted({index for owner in owners
                                  for index in doorsByWall.get(id(owner), ())})]
                    spanKey = (ownerKey, tuple(openingKeys[id(door)] for door in ownerDoors), settingsKey, cutterKey)
                    cached = spanCache.pop(spanKey, None)
                    if cached is not None:
                        spanCache[spanKey] = cached
                        dimensions.extend(cached[0])
                        continue
                    spanStart = len(dimensions)
                    # Door jambs split the relevant side. Project onto
                    # the exposed span so room corners and wall intersections still clip it.
                    spanLength = QtCore.QLineF(first, second).length()
                    numericFirst, numericSecond = (firstX, firstY), (secondX, secondY)
                    numericDirection = (directionX, directionY)
                    records = []
                    for door in ownerDoors:
                        record = openingRecords.get(id(door))
                        if record is None:
                            openingFirst, openingSecond = openingVertices[id(door)]
                            parentFirst, parentSecond = door.parentWall.firstVertex, door.parentWall.secondVertex
                            isDoor = isinstance(door, (Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway))
                            mode = settings["doors" if isDoor else "windows"]
                            oneSided = not isDoor or isinstance(door, (Door, DoubleDoor, SlidingDoor, BarnDoor))
                            flipped = False
                            if mode == 1 and oneSided and not isinstance(door, Fireplace):
                                flipped = door.panelsFlipped if isinstance(door, SlidingDoor) else door.swingsOutwards
                                flipped = bool(flipped) ^ isinstance(door, BarnDoor) ^ bool(door.measurementFlipped)
                            fireplace = None
                            if isinstance(door, Fireplace):
                                tangent, normal = door.Axes()
                                center = (openingFirst + openingSecond) / 2
                                fireplace = (normal.x(), normal.y(), center.x(), center.y(), door.depth, door.depthOffset)
                            record = MeasurementOpening(id(door), (openingFirst.x(), openingFirst.y()),
                                (openingSecond.x(), openingSecond.y()), (parentFirst.x(), parentFirst.y()),
                                (parentSecond.x(), parentSecond.y()), mode, oneSided, flipped,
                                isinstance(door, PocketDoor), getattr(door, "hingeAtSecond", False), fireplace)
                            openingRecords[id(door)] = record
                        records.append(record)
                    ownerObjects = {id(owner): owner for owner in owners + ownerDoors}
                    wallOwnerKeys = [id(owner) for owner in owners]
                    spans = BuildOpeningDimensions(numericFirst, numericSecond, numericDirection, spanLength,
                        (midpoint.x(), midpoint.y()), wallOwnerKeys, records, preparedCutters)
                    dimensions.extend((QtCore.QPointF(*start), QtCore.QPointF(*end),
                                       owners if spanOwners is wallOwnerKeys else [ownerObjects[key] for key in spanOwners])
                                      for start, end, spanOwners in spans)
                    cached = tuple(dimensions[spanStart:])
                    points = len(cached) * 2 + len(ownerKey[-1]) * 2
                    if points <= 32768:
                        spanCache[spanKey] = (cached, points)
                        self.dimensionSpanCachePoints += points
        self.dimensionCacheKey = cacheKey
        if blockers:
            exposedDimensions = []
            preparedBlockers = PrepareMeasurementPolygons([[(point.x(), point.y()) for point in polygon]
                                                           for polygon in blockers if len(polygon) >= 3])
            for first, second, owners in dimensions:
                spans = ExposedMeasurementSpans((first.x(), first.y()), (second.x(), second.y()), preparedBlockers)
                exposedDimensions.extend((QtCore.QPointF(*start), QtCore.QPointF(*end), owners) for start, end in spans)
            dimensions = exposedDimensions
        while len(ownerCache) > max(1024, len(walls) * 8):
            ownerCache.pop(next(iter(ownerCache)))
        while len(spanCache) > min(8192, max(1024, len(walls) * 8)) or self.dimensionSpanCachePoints > 32768:
            spans, points = spanCache.pop(next(iter(spanCache)))
            self.dimensionSpanCachePoints -= points
        self.dimensionOwnerState = ((ownerStateKey, axisValues, ownerSpans)
                                    if len(axisValues) <= 4096 and len(ownerSpans) <= 8192 else None)
        self.dimensionCache = dimensions
        return dimensions

    def ObjectCorners(self, drawingObject):
        if isinstance(drawingObject, AngleGuide):
            return list(ObjectControlPoints(drawingObject))
        if isinstance(drawingObject, Column):
            return [QtCore.QPointF(*point) for point in ColumnHandleCorners(
                (drawingObject.firstVertex.x(), drawingObject.firstVertex.y()),
                (drawingObject.secondVertex.x(), drawingObject.secondVertex.y()), drawingObject.width)]
        if isinstance(drawingObject, (Arrow, MeasurementGuide)):
            return [drawingObject.firstVertex, drawingObject.secondVertex]
        return list(self.ObjectFootprint(drawingObject)[1])

    def ObjectFootprint(self, drawingObject):
        if isinstance(drawingObject, AngleGuide):
            points = ObjectControlPoints(drawingObject)
            path, labelRect, label, arcMiddle = self.AngleLayout(drawingObject, selected = True)
            bounds = path.boundingRect().united(labelRect) if label else path.boundingRect()
            worldBounds = QtCore.QRectF(self.ViewportToWorld(bounds.topLeft()), self.ViewportToWorld(bounds.bottomRight())).normalized()
            footprint = worldBounds, points, (QtCore.QPointF(1, 0), QtCore.QPointF(0, 1))
            key = tuple((point.x(), point.y()) for point in points) + ((drawingObject.textOffset.x(), drawingObject.textOffset.y(), self.zoom),)
            drawingObject.footprintCache = key, footprint
            drawingObject.numericCollisionFootprint = None
            return footprint
        if isinstance(drawingObject, BoundaryLine):
            points = ObjectControlPoints(drawingObject)
            widthRole = lineWeightClasses[drawingObject.weightClass][1] if isinstance(drawingObject, DashedLine) else "dimensions"
            padding = max(1, self.lineWidths[widthRole]) / (self.basePixelsPerMillimeter * self.zoom)
            bounds = QtGui.QPolygonF(points).boundingRect().adjusted(-padding, -padding, padding, padding)
            footprint = bounds, points, (QtCore.QPointF(1, 0), QtCore.QPointF(0, 1))
            drawingObject.footprintCache = (tuple((point.x(), point.y()) for point in points), self.zoom, padding), footprint
            drawingObject.numericCollisionFootprint = None
            return footprint
        if isinstance(drawingObject, MeasurementGuide):
            points = ObjectControlPoints(drawingObject)
            labelBounds = self.MeasurementLabelLayout(drawingObject)[3].boundingRect()
            labelWorld = QtCore.QRectF(self.ViewportToWorld(labelBounds.topLeft()), self.ViewportToWorld(labelBounds.bottomRight())).normalized()
            bounds = QtGui.QPolygonF(points).boundingRect().united(labelWorld)
            depth = drawingObject.depth if type(drawingObject) is MeasurementGuide else 0
            if depth != 0:
                offset = QtCore.QPointF(*GuideDepthOffset((drawingObject.firstVertex.x(), drawingObject.firstVertex.y()),
                                                       (drawingObject.secondVertex.x(), drawingObject.secondVertex.y()), depth))
                bounds = bounds.united(QtGui.QPolygonF([drawingObject.firstVertex, drawingObject.secondVertex,
                    drawingObject.firstVertex + offset, drawingObject.secondVertex + offset]).boundingRect())
            footprint = bounds, points, (QtCore.QPointF(1, 0), QtCore.QPointF(0, 1))
            key = tuple((point.x(), point.y()) for point in points) + ((drawingObject.textOffset.x(), drawingObject.textOffset.y(), self.zoom, self.unitsMode, depth),)
            drawingObject.footprintCache = key, footprint
            drawingObject.numericCollisionFootprint = None
            return footprint
        if isinstance(drawingObject, Fireplace):
            key = (drawingObject.firstVertex.x(), drawingObject.firstVertex.y(),
                   drawingObject.secondVertex.x(), drawingObject.secondVertex.y(), drawingObject.depth,
                   drawingObject.depthOffset)
            cached = getattr(drawingObject, "footprintCache", None)
            if cached is not None and cached[0] == key:
                return cached[1]
            tangent, normal = drawingObject.Axes()
            rectangle, corners, axes = FireplaceFootprint(key[:2], key[2:4], (normal.x(), normal.y()),
                                                        drawingObject.width, key[4], key[5])
            footprint = (QtCore.QRectF(*rectangle), tuple(QtCore.QPointF(*point) for point in corners),
                         tuple(QtCore.QPointF(*axis) for axis in axes))
            drawingObject.numericCollisionFootprint = None
            drawingObject.footprintCache = (key, footprint)
            return footprint
        batch = getattr(self, "collisionPassCache", None)
        if batch is not None:
            batch.setdefault("references", {})[id(drawingObject)] = drawingObject
            footprint = batch.get("footprints", {}).get(id(drawingObject))
            if footprint is not None:
                return footprint
        first = drawingObject.firstVertex
        second = drawingObject.secondVertex
        width = drawingObject.width
        key = (first.x(), first.y(), second.x(), second.y(), width)
        cached = getattr(drawingObject, "footprintCache", None)
        if cached is not None and cached[0] == key:
            if batch is not None:
                batch.setdefault("footprints", {})[id(drawingObject)] = cached[1]
            return cached[1]
        rectangle, corners, axes = RectangleFootprint((first.x(), first.y()), (second.x(), second.y()), width)
        footprint = (QtCore.QRectF(*rectangle), tuple(QtCore.QPointF(*point) for point in corners),
                     tuple(QtCore.QPointF(*axis) for axis in axes))
        if corners and isinstance(drawingObject, Column):
            corners = tuple(ColumnPolygon(drawingObject))
            axes = PolygonAxes(tuple((point.x(), point.y()) for point in corners))
            footprint = (QtGui.QPolygonF(corners).boundingRect(), corners,
                         tuple(QtCore.QPointF(*axis) for axis in axes))
        drawingObject.numericCollisionFootprint = None
        drawingObject.footprintCache = (key, footprint)
        if batch is not None:
            batch.setdefault("footprints", {})[id(drawingObject)] = footprint
        return footprint

    def ObjectsOverlap(self, first, second, contactTolerance = .01):
        if not self.CollisionEnabled(first, second):
            return False
        if ExcludesFootprintCollision(CollisionFlags(type(first)), CollisionFlags(type(second))):
            return False
        # A separating-axis test checks the actual oriented footprints; mere
        # edge contact is allowed, and rotated rectangles do not falsely collide.
        firstBounds, firstCorners, firstAxes = self.ObjectFootprint(first)
        secondBounds, secondCorners, secondAxes = self.ObjectFootprint(second)
        if not firstBounds.intersects(secondBounds) or not firstCorners or not secondCorners:
            return False
        firstCorners, firstAxes = self.NumericCollisionFootprint(first, (firstBounds, firstCorners, firstAxes))
        secondCorners, secondAxes = self.NumericCollisionFootprint(second, (secondBounds, secondCorners, secondAxes))
        firstCompound = isinstance(first, Furnishing) and first.definition.get("components")
        secondCompound = isinstance(second, Furnishing) and second.definition.get("components")
        if firstCompound or secondCompound:
            firstParts = FurnishingCollisionFootprints(first) if firstCompound else ((firstBounds, firstCorners, firstAxes),)
            secondParts = FurnishingCollisionFootprints(second) if secondCompound else ((secondBounds, secondCorners, secondAxes),)
            return any(firstPart[0].intersects(secondPart[0]) and FootprintsOverlap(
                firstPart[1], firstPart[2], secondPart[1], secondPart[2], contactTolerance)
                for firstPart in firstParts for secondPart in secondParts)
        return FootprintsOverlap(firstCorners, firstAxes, secondCorners, secondAxes, contactTolerance)

    def NumericCollisionFootprint(self, obj, footprint):
        # One lazy numeric mirror per object, never a cache of object pairs.
        # Point tuple identity survives warm calls and changes with every rebuild.
        cached = getattr(obj, "numericCollisionFootprint", None)
        if cached is not None and cached[0] is footprint[1] and cached[1] is footprint[2]:
            return cached[2]
        numeric = (tuple((point.x(), point.y()) for point in footprint[1]),
                   tuple((axis.x(), axis.y()) for axis in footprint[2]))
        obj.numericCollisionFootprint = (footprint[1], footprint[2], numeric)
        return numeric


class FootprintGeometry(GeometryMixin):
    """Independent geometry results and caches for a structural object class."""

    def __init__(self, scale, owner = None):
        self.owner = owner
        self.basePixelsPerMillimeter = scale
        self.zoom = 1.0
        self.wallGeometryKey = None
        self.wallGeometryPath = QtGui.QPainterPath()
        self.wallFillPolygons = []
        self.wallGeometryComponents = []
        self.wallComponentCache = {}
        self.wallBodyCache = {}
        self.wallJunctionCache = {}
        self.wallSectorCache = {}
        self.wallOwnershipCache = {}
        self.wallPolygonCache = {}
        self.wallPolygonPointCount = 0
        self.dimensionOwnerCache = {}
        self.dimensionSpanCache = {}
        self.dimensionSpanCachePoints = 0
        self.dimensionOwnerState = None
        self.wallBoundaryCache = {}
        self.wallBoundaryEdgeCache = {}
        self.wallTraceState = None
        self.wallTraceContexts = {}
        self.wallTraceContextPoints = 0
        self.wallContourCache = {}
        self.wallContourCachePoints = 0
        self.wallMaterialPathCache = {}
        self.wallDimensionComponentCache = {}
        self.materialGeometryKey = None
        self.dimensionCacheKey = None
        self.dimensionCache = []
        self.dimensionBoundaryKey = None
        self.dimensionBoundaryValues = ()

    def __getattr__(self, name):
        if self.owner is None:
            raise AttributeError(name)
        return getattr(self.owner, name)

    def WorldToViewport(self, point):
        if self.owner is not None:
            return self.owner.WorldToViewport(point)
        return QtCore.QPointF(point.x(), -point.y()) * self.basePixelsPerMillimeter
