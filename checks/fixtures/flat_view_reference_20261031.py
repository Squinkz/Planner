from planner_app.viewport.geometry import FootprintGeometry
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



"""Frozen flat.plan validity/snapshot methods before lazy-renderer fixes."""
"""Viewport grid, scene painting, dimensions, rulers and selection feedback."""
from planner_app.graphics.text import PathTextPainter
from planner_app.models import AngleGuide, ObjectControlPoints

from planner_app.models import Elevator
from planner_app.models import lineWeightClasses

import math
from contextlib import ExitStack
from itertools import chain
from time import perf_counter
from planner_app.graphics.path_operations import Paths
from PySide6 import QtCore, QtGui

from planner_app.graphics.north_arrow import DrawNorthArrow
from planner_app.graphics.fireplace import FireplacePath
from planner_app.graphics.object_composite import ObjectPaintDevice
from planner_app.graphics.palette import themeColors
from planner_app.graphics.fonts import fontFamily
from planner_app.graphics import palette
from planner_app.graphics.linework import LinePen
from planner_app.graphics.furnishings import DrawFurnishing, SelectedFurnishingRenderer, FurnishingArtworkBounds, FurnishingRenderer, FurnishingRendererCache
from planner_app.paths import furnishingsDirectory
from planner_app.graphics.symbols import DrawOpeningSymbol, DrawStairSymbol, DrawStairArrows, WallOpeningPolygons
from planner_app.geometry.stair_annotations import StairArrowRuns, StairEndpointNeighbors
from planner_app.graphics.arrows import ArrowPaths, ConnectedArrowDirections, ConnectedArrowCorners
from planner_app.models import OpenDoorway, Door, SwingingDoor, DoubleDoor, Furnishing, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, SlidingDoor, MeasurementGuide, BoundaryLine, DashedLine, SolidLine, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, Window, NorthArrow, Fireplace
from planner_app.units import MetricUnit, FormatLength, PropertyUnit, GridUnit, imperialModes
from planner_app.graphics.measurement_text import MeasurementTextPath
from planner_app.graphics.retained_dimensions import RetainedDimensions
from planner_app.geometry.measurement_stacks import BuildMeasurementStacks, VisibleWallDimensionSpans, StackedDimensionLengths
from planner_app.geometry.measurements import GuideDepthOffset
from planner_app.viewport.geometry import CollisionPass
from planner_app.viewport.spatial_index import BoundsIndex
from planner_app.viewport.diagnostics import MeasurePaint
from planner_app.viewport.edit_cache import EditPaintCacheMixin
from planner_app.viewport.paint_candidates import PaintCandidatesMixin
from planner_app.viewport.polygon_clipping import SubtractConvexPolygon

toolTipRows = {
    "searchFurnishings": ("Space", "Search furnishings"),
    "holdDoor": ("D", "(Hold) Place door"),
    "holdWindow": ("S", "(Hold) Place window"),
    "thickness": ("Q/W", "Set wall thickness"),
    "placeDoor": ("Left mouse", "Place door"),
    "placeWindow": ("Left mouse", "Place window"),
    "releaseDoor": ("D", "(Release) Cancel"),
    "releaseWindow": ("S", "(Release) Cancel"),
    "doorType": ("Scroll", "Set door type"),
    "windowType": ("Scroll", "Set window type"),
    "select": ("Left mouse", "Select or move object"),
    "placeWall": ("Right mouse", "(Drag) Place wall"),
    "segments": ("Scroll", "Change segment count"),
    "square": ("Ctrl", "Constrain to a square"),
    "circle": ("Ctrl", "Constrain to a circle"),
    "center": ("Shift", "Expand from center"),
    "cancelDraw": ("Left mouse", "Cancel"),
    "angle": ("Ctrl", "Snap to 15\u00b0 increments"),
    "extrude": ("Shift", "Extrude"),
    "duplicate": ("Shift", "Duplicate object"),
    "axes": ("Ctrl", "Constrain to axes"),
    "localAxes": ("Ctrl", "Constrain to local axes"),
    "localAngle": ("Ctrl", "Snap to local 15\u00b0 increments"),
    "axisOrigin": ("Scroll", "Switch axis origin"),
    "face": ("Ctrl", "Face cursor"),
    "hinge": ("Ctrl", "Adjust hinge side"),
    "cancelMove": ("Right mouse", "Cancel"),
    "calibrationPlace": ("Left Mouse", "Place point"),
    "calibrationConfirm": ("Enter", "Confirm"),
    "calibrationCancel": ("Escape", "Cancel"),
}



"""Opaque physical-scene retention during unconstrained wall endpoint drags."""
from planner_app.graphics.text import PathTextPainter
import math
from planner_app.graphics.path_operations import Paths
from PySide6 import QtCore, QtGui
from planner_app.models import Wall, Pillar, Column, Window, Fireplace, Furnishing, Label, NorthArrow
from planner_app.graphics.furnishings import FurnishingArtworkBounds



from planner_app.viewport.widget import DrawingViewport

class ReferenceViewport(DrawingViewport):
    def SceneRenderValueKey(self, backgroundKey):
        diagnostics = self.renderDiagnostics if self.renderDiagnostics is not None and self.renderDiagnostics.enabled else None
        started = perf_counter() if diagnostics is not None else None
        # Capture mutable properties as values: settings/property tools and
        # history can edit objects in place without changing sceneRevision.
        objectKeys = []
        for obj in self.walls + self.windows + self.furnishings + self.labels:
            first, second = obj.firstVertex, obj.secondVertex
            key = (id(obj), type(obj), first.x(), first.y(), second.x(), second.y(), obj.width, obj.measurementHidden,
                   tuple(getattr(obj, "geometryIssues", ())))
            if isinstance(obj, MeasurementGuide):
                key += (obj.textOffset.x(), obj.textOffset.y())
                if type(obj) is MeasurementGuide:
                    key += (obj.depth,)
            if isinstance(obj, DashedLine):
                key += (obj.weightClass,)
            if isinstance(obj, AngleGuide):
                key += (obj.middleVertex.x(), obj.middleVertex.y())
            if isinstance(obj, Window):
                key += (id(obj.parentWall), obj.centerFraction, obj.length, obj.measurementFlipped,
                        getattr(obj, "hingeAtSecond", None), getattr(obj, "swingsOutwards", None),
                        getattr(obj, "panelsFlipped", None), getattr(obj, "sillDepth", None),
                        getattr(obj, "windowWell", False), getattr(obj, "wellDepth", 600.0), getattr(obj, "wellDashed", False))
                if isinstance(obj, Fireplace):
                    key += (obj.depth, obj.depthOffset, obj.manualDepth, obj.manualDepthOffset, obj.material)
            elif isinstance(obj, Label):
                key += (obj.text, obj.intensity, getattr(obj, "unitsOverride", None))
            elif isinstance(obj, NorthArrow):
                key += (obj.intensity,)
            elif isinstance(obj, Furnishing):
                definitionKey = obj.definition["key"]
                key += (definitionKey, id(self.furnishingRenderers[definitionKey]),
                         id(self.selectedFurnishingRenderers[definitionKey]), obj.flipHorizontal, obj.flipVertical, obj.behindCounters)
            else:
                key += (obj.material, obj.firstMiter, obj.secondMiter)
                if isinstance(obj, Stair):
                    key += (obj.directionReversed, obj.autosize, obj.manualStepCount, obj.stepSizeBounds)
                elif isinstance(obj, Railing):
                    key += (obj.autosize, obj.manualPostCount, obj.spacingBounds)
                elif isinstance(obj, Arrow):
                    key += (obj.solidTip, obj.tipSize, obj.intensity, obj.directionReversed)
            objectKeys.append(key)
        selection = self.pendingShiftSelection[0] if self.pendingShiftSelection is not None else self.SelectionEntries()
        key = (backgroundKey, palette.labelFont, tuple(self.lineWidths.items()), tuple(objectKeys), tuple((id(obj), index) for obj, index in selection),
                tuple(tuple(id(obj) for obj in group) for group in self.objectGroups),
                frozenset(self.hiddenObjectIds), tuple(self.visibility.items()), self.showMeasurements, self.measurementPrecision,
                tuple(self.measurementVisibility.items()), tuple(self.measurementSettings.items()), self.wallMeasurementMode, self.wallMeasurementReference,
                tuple(self.collisionSettings.items()), getattr(self, "exportRender", False))
        if diagnostics is not None:
            diagnostics.RecordPhase("scene-key", started)
        return key

    def EditSceneSnapshot(self, drawingRect, origin, pixelsPerMillimeter, values):
        changes = self.renderChanges
        key = (values[:3], values[4:], changes.appearance, changes.topology, changes.visibility,
               self.wallStyle, tuple(self.collisionSettings.items()),
               self.connectedVerticesEnabled, self.connectedObjectsEnabled,
               tuple((id(wall), index) for wall, index, position in self.ActiveAttachments()))
        objects = {id(obj): obj for obj in self.walls + self.windows + self.furnishings + self.labels}
        objectKeys = {entry[0]: entry for entry in values[3]}
        walls = [obj for obj in self.walls if type(obj) in (Wall, Pillar, Column) and self.IsObjectVisible(obj)]
        self.ConnectedWallPath(walls)
        contained = {id(wall) for wall in self.ContainedWalls(walls)}
        duplicates = {id(obj) for obj in self.DuplicateFurnishings()}
        transform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
        owned = {}
        for owner, polygon in self.wallFillPolygons:
            coordinates, bounds, normalized = self.PreparedWallPolygon(polygon)
            owned.setdefault(id(owner), []).append((coordinates, bounds))
        snapshot = {}
        previous = self.viewportEditSnapshot if key == self.viewportEditKey and self.viewportEditSnapshot is not None else {}
        padding = 4 * max(self.lineWidths.values()) + 3
        for identity, obj in objects.items():
            if not self.IsObjectVisible(obj):
                continue
            objectKey = objectKeys[identity]
            if isinstance(obj, Window):
                # A parent's extension can change an opening's error color even
                # when its absolute endpoints have not moved.
                objectKey += (objectKeys.get(id(obj.parentWall)),)
                if getattr(obj, "geometryIssues", ()):
                    from planner_app.geometry_recovery import ActiveGeometryIssues
                    objectKey += (tuple(ActiveGeometryIssues(obj, self)),)
            pieces = owned.get(identity, ())
            signature = (objectKey, tuple(coordinates for coordinates, bounds in pieces), identity in contained, identity in duplicates)
            old = previous.get(identity)
            if old is not None and old[0] == signature:
                snapshot[identity] = old
                continue
            bounds = self.ObjectFootprint(obj)[0]
            if isinstance(obj, Furnishing) and not isinstance(obj, (Label, NorthArrow)):
                bounds = bounds.united(FurnishingArtworkBounds(obj, self.furnishingRenderers[obj.definition["key"]]))
            screenBounds = QtCore.QRectF(self.WorldToViewport(bounds.topLeft()), self.WorldToViewport(bounds.bottomRight())).normalized()
            if isinstance(obj, Window):
                if not isinstance(obj, Fireplace):
                    extent = (obj.length + obj.width / 2 + getattr(obj, "sillDepth", 0)
                              + (obj.wellDepth + 150 if obj.windowWell else 0)) * pixelsPerMillimeter
                    screenBounds = screenBounds.adjusted(-extent, -extent, extent, extent)
            for coordinates, region in pieces:
                screenBounds = screenBounds.united(transform.mapRect(region))
            screenBounds = screenBounds.adjusted(-padding, -padding, padding, padding)
            snapshot[identity] = (signature, screenBounds.intersected(drawingRect))
        return key, snapshot


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
        bodyOverlap = self.ObjectsOverlap(first, second, contactTolerance = contactTolerance)
        # Joined runs can remove body corners as well as add miters. A raw
        # rectangle overlap cannot prove a collision after those footprint cuts.
        if (not any(type(obj) in (Wall, Stair, Counter, Railing) for obj in (first, second))
                and bodyOverlap):
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
        paths, clippedBodies = [], []
        cache = getattr(self, "collisionFootprintCache", {})
        for obj in (first, second):
            pathKey = (id(obj), excludedKey)
            if batch is not None and pathKey in batch.get("paths", {}):
                paths.append(batch["paths"][pathKey])
                clippedBodies.append(batch.get("bodyFootprints", {}).get(pathKey))
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
                        workspace = workspaces.get(type(obj))
                        if workspace is None:
                            workspace = FootprintGeometry(self.basePixelsPerMillimeter, cacheBudget = getattr(self, "geometryCacheBudget", None))
                            workspaces[type(obj)] = workspace
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
                    # Material sectors partition overlapping bodies between owners.
                    # Physical bodies retain their overlap, clipped only by actual
                    # footprint planes. Keep the clipped convex data for SAT too:
                    # native booleans can lose coincident, nearly horizontal faces.
                    bodyFootprints = {}
                    physicalBodies = workspace.PhysicalWallBodies(members)
                    for wall in members:
                        body = physicalBodies.get(id(wall))
                        if body is None:
                            continue
                        corners, axes = body
                        if axes is not None:
                            bodyFootprints[id(wall)] = corners, axes
                        if PolygonTwiceArea(corners) > 0:
                            corners = tuple(reversed(corners))
                        path = ownerPaths.setdefault(id(wall), QtGui.QPainterPath())
                        path.setFillRule(QtCore.Qt.FillRule.WindingFill)
                        path.addPolygon(QtGui.QPolygonF([QtCore.QPointF(*point) for point in corners]))
                        path.closeSubpath()
                    cache[type(obj)] = (key, ownerPaths, bodyFootprints)
                paths.append(cache[type(obj)][1].get(id(obj), QtGui.QPainterPath()))
                clippedBodies.append(cache[type(obj)][2].get(id(obj)))
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
                clippedBodies.append(None)
            if batch is not None:
                batch.setdefault("paths", {})[pathKey] = paths[-1]
                batch.setdefault("bodyFootprints", {})[pathKey] = clippedBodies[-1]
        self.collisionFootprintCache = cache
        if bodyOverlap:
            if all(body is None for body in clippedBodies):
                result = True
            else:
                parts = []
                for obj, clipped in zip((first, second), clippedBodies):
                    if clipped is not None:
                        parts.append((clipped,))
                    elif isinstance(obj, Furnishing) and obj.definition.get("components"):
                        parts.append(tuple((corners, axes) for bounds, corners, axes in FurnishingCollisionFootprints(obj)))
                    else:
                        parts.append((self.NumericCollisionFootprint(obj, self.ObjectFootprint(obj)),))
                result = any(FootprintsOverlap(firstCorners, firstAxes, secondCorners, secondAxes, contactTolerance)
                             for firstCorners, firstAxes in parts[0] for secondCorners, secondAxes in parts[1])
            if result:
                resultCache[resultKey] = True
                pairEpochs[resultKey] = epoch
                pairKeys.pop(resultKey, None)
                return True
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
        # Keep a filled interior farther than half the allowed contact width
        # from the intersection boundary. Area/perimeter is not a distance:
        # it misses triangular miter intersections and depends on owner splits.
        origin = overlap.boundingRect().center()
        overlap = QtGui.QTransform().translate(-origin.x(), -origin.y()).map(overlap)
        if contactTolerance > 0:
            stroke = Paths.PrepareStroke(width = contactTolerance, cap = 'flat', join = 'round')
            overlap = Paths.Difference(overlap, stroke(overlap))
        result = SignificantPathOverlap(([(point.x(), point.y()) for point in polygon]
                                         for polygon in Paths.FillPolygons(overlap)), 0)
        resultCache[resultKey] = result
        return result
