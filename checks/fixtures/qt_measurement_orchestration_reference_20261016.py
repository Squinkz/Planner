"""Frozen measurement orchestration before Qt separation."""
import math
from PySide6 import QtCore, QtGui
from planner_app.models import *
from planner_app.viewport.geometry import FootprintGeometry
from planner_app.viewport.spatial_index import BoundsIndex
from planner_app.geometry.measurements import *

class ReferenceMeasurements:
    def WallDimensions(self, walls, boundaryPath, openings = None, cachedBoundary = False,
                       measureCaps = False, blockers = ()):
        cutters = []
        if walls and type(walls[0]) in (Wall, Pillar, Column, Railing):
            if not hasattr(self, "measurementCutterWorkspaces"):
                self.measurementCutterWorkspaces = {}
            toWorld = QtGui.QTransform().scale(1 / self.basePixelsPerMillimeter, -1 / self.basePixelsPerMillimeter)
            for objectClass, key in ((Stair, "stairs"), (Counter, "counters")):
                if self.measurementSettings[key] != 0:
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
            return self.BuildWallDimensions(walls, boundaryPath, openings, cachedBoundary, measureCaps, blockers, cutters)
        doors = list(self.windows if openings is None else openings)
        blockerKey = tuple(tuple((point.x(), point.y()) for point in polygon) for polygon in blockers)
        cutterKey = tuple(tuple((point.x(), point.y()) for point in polygon) for polygon in cutters)
        origin = self.WorldToViewport(QtCore.QPointF())
        transform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
        dimensions = []
        for geometryKey, members, path in components:
            memberIds = {id(wall) for wall in members}
            componentDoors = [door for door in doors if id(door.parentWall) in memberIds]
            doorKey = tuple((id(door), type(door), door.firstFraction, door.secondFraction,
                             getattr(door, "hingeAtSecond", None), getattr(door, "swingsOutwards", None),
                             getattr(door, "panelsFlipped", None), door.measurementFlipped,
                             (door.depth, door.depthOffset) if isinstance(door, Fireplace) else None) for door in componentDoors)
            key = (geometryKey, doorKey, tuple(sorted(self.measurementSettings.items())), measureCaps, blockerKey, cutterKey)
            if hasattr(self, "SelectionEntries"):
                key += (frozenset(id(obj) for obj, index in self.SelectionEntries() if id(obj) in memberIds),)
            cached = self.wallDimensionComponentCache.pop(key, None)
            if cached is None:
                cached = self.BuildWallDimensions(members, transform.map(path), componentDoors,
                                                   measureCaps = measureCaps, blockers = blockers, cutters = cutters)
            self.wallDimensionComponentCache[key] = cached
            dimensions.extend(cached)
        while len(self.wallDimensionComponentCache) > max(128, len(components) * 2):
            self.wallDimensionComponentCache.pop(next(iter(self.wallDimensionComponentCache)))
        self.dimensionCacheKey = None
        self.dimensionCache = dimensions
        return dimensions


    def BuildWallDimensions(self, walls, boundaryPath, openings = None, cachedBoundary = False,
                            measureCaps = False, blockers = (), cutters = ()):
        selectedIds = {id(obj) for obj, index in self.SelectionEntries()} if hasattr(self, "SelectionEntries") else set()
        selectionKey = frozenset(id(wall) for wall in walls if id(wall) in selectedIds)
        doors = list(self.windows if openings is None else openings)
        wallKey = tuple((id(wall), wall.firstVertex.x(), wall.firstVertex.y(), wall.secondVertex.x(),
                         wall.secondVertex.y(), wall.width, wall.firstMiter, wall.secondMiter) for wall in walls)
        doorKey = tuple((id(door), type(door), id(door.parentWall), door.firstFraction, door.secondFraction,
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
        settingsKey = tuple(sorted(self.measurementSettings.items()))
        dimensions = []
        preparedCutters = PrepareMeasurementPolygons([[(point.x(), point.y()) for point in cutter] for cutter in cutters])
        for polygon in worldTransform.map(boundaryPath).toSubpathPolygons():
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
                    if any(id(owner) in selectedIds for owner in owners):
                        dimensions.append((first, second, owners))
                        continue
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
                    interruptions = CoveredMeasurementSpans(numericFirst, numericDirection, spanLength,
                                                            preparedCutters, .02, mergeTolerance = .02)
                    projectedOpenings = []
                    projectedFireplaces = []
                    for door in ownerDoors:
                        openingFirst, openingSecond = openingVertices[id(door)]
                        low, high = OpeningProjection(numericFirst, numericDirection,
                            (openingFirst.x(), openingFirst.y()), (openingSecond.x(), openingSecond.y()))
                        projectedOpenings.append((id(door), low, high))
                        if isinstance(door, Fireplace):
                            tangent, normal = door.Axes()
                            center = (openingFirst + openingSecond) / 2
                            projectedFireplaces.append((low, high, normal.x(), normal.y(), center.x(), center.y(),
                                                        door.depth, door.depthOffset))
                    for door in ownerDoors:
                        isDoor = isinstance(door, (Door, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway))
                        mode = self.measurementSettings["doors" if isDoor else "windows"]
                        if mode == 2 and not isinstance(door, Fireplace):
                            continue
                        if mode == 1 and not isinstance(door, Fireplace) and (not isDoor or isinstance(door, (Door, SlidingDoor, BarnDoor))):
                            flippedSide = door.swingsOutwards if not isinstance(door, SlidingDoor) else door.panelsFlipped
                            flippedSide = bool(flippedSide) ^ isinstance(door, BarnDoor) ^ bool(door.measurementFlipped)
                            # In world coordinates this is opposite the window's crossbar/sill side.
                            parentFirst, parentSecond = door.parentWall.firstVertex, door.parentWall.secondVertex
                            if not OpeningOnMeasuredSide((midpoint.x(), midpoint.y()), (parentFirst.x(), parentFirst.y()),
                                                         (parentSecond.x(), parentSecond.y()), flippedSide):
                                continue
                        openingFirst, openingSecond = openingVertices[id(door)]
                        low, high = OpeningProjection(numericFirst, numericDirection,
                            (openingFirst.x(), openingFirst.y()), (openingSecond.x(), openingSecond.y()),
                            isinstance(door, PocketDoor), getattr(door, "hingeAtSecond", False))
                        start, end = max(0.0, low), min(spanLength, high)
                        if end - start > 0.0001:
                            interruptions.append((start, end))
                    ownerObjects = {id(owner): owner for owner in owners + ownerDoors}
                    wallOwnerKeys = [id(owner) for owner in owners]
                    spans = BuildMeasurementSpan(numericFirst, numericSecond, numericDirection,
                        wallOwnerKeys, interruptions, projectedOpenings, projectedFireplaces)
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
                if any(id(owner) in selectedIds for owner in owners):
                    exposedDimensions.append((first, second, owners))
                    continue
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


