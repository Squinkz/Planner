"""Pre-extraction reference, adapted for the five-result chamfer junction API."""
import math
from PySide6 import QtCore, QtGui
from planner_app.viewport.geometry import BoundsIndex, SubtractConvexPolygon
from planner_app.models import OpenDoorway, Door, PocketDoor, BarnDoor, BifoldDoor, SlidingDoor, MeasurementGuide, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Window, SilledWindow, CasementWindow, Label, Furnishing, NorthArrow, Fireplace
from planner_app.models import Elevator

"""Native column curves and cached tolerance-based collision approximations."""
import math
from PySide6 import QtCore, QtGui


def ColumnPath(column):
    center = (column.firstVertex + column.secondVertex) / 2
    along = (column.secondVertex - column.firstVertex) / 2
    length = math.hypot(along.x(), along.y())
    if length < 1e-8 or column.width <= 0:
        return QtGui.QPainterPath()
    key = (along.x(), along.y(), column.width)
    cached = getattr(column, "ellipsePathCache", None)
    if cached is None or cached[0] != key:
        across = QtCore.QPointF(-along.y(), along.x()) * (column.width / (2 * length))
        ellipse = QtGui.QPainterPath()
        ellipse.addEllipse(QtCore.QRectF(-1, -1, 2, 2))
        # Use a positive determinant so native ellipses match wall winding.
        transform = QtGui.QTransform(across.x(), across.y(), -along.x(), -along.y(), 0, 0)
        cached = (key, transform.map(ellipse))
        column.ellipsePathCache = cached
    return QtGui.QTransform().translate(center.x(), center.y()).map(cached[1])


def ColumnContains(column, position):
    along = (column.secondVertex - column.firstVertex) / 2
    length = math.hypot(along.x(), along.y())
    if length < 1e-8 or column.width <= 0:
        return False
    offset = position - (column.firstVertex + column.secondVertex) / 2
    direction = along / length
    normal = QtCore.QPointF(-direction.y(), direction.x())
    return ((QtCore.QPointF.dotProduct(offset, direction) / length) ** 2
            + (QtCore.QPointF.dotProduct(offset, normal) / (column.width / 2)) ** 2 <= 1)


def ColumnPolygon(column, tolerance = .5):
    center = (column.firstVertex + column.secondVertex) / 2
    along = (column.secondVertex - column.firstVertex) / 2
    length = math.hypot(along.x(), along.y())
    if length < 1e-8 or column.width <= 0:
        return QtGui.QPolygonF()
    across = QtCore.QPointF(-along.y(), along.x()) * (column.width / (2 * length))
    key = (along.x(), along.y(), column.width, tolerance)
    cached = getattr(column, "ellipsePolygonCache", None)
    if cached is None or cached[0] != key:
        # Bound chord error in world millimetres using the larger semiaxis.
        radius = max(length, column.width / 2)
        step = math.acos(max(-1, min(1, 1 - tolerance / radius)))
        count = max(16, 4 * math.ceil(math.pi / (4 * step)))
        polygon = QtGui.QPolygonF([across * math.cos(index * math.tau / count)
                                  + along * math.sin(index * math.tau / count) for index in range(count)])
        cached = (key, polygon)
        column.ellipsePolygonCache = cached
    return cached[1].translated(center)

"""Solid tapered U-shaped fireplace body, in world coordinates."""
from PySide6 import QtCore, QtGui


def FireplacePath(fireplace):
    direction, normal = fireplace.Axes()
    center = (fireplace.firstVertex + fireplace.secondVertex) / 2 + normal * fireplace.depthOffset
    if fireplace.swingsOutwards:
        normal = -normal
    width, depth = fireplace.width, fireplace.depth
    path = QtGui.QPainterPath()
    for index, (x, y) in enumerate(((-.5, -.5), (-.5, .5), (.5, .5), (.5, -.5),
                                   (.30, -.5), (.20, 0), (-.20, 0), (-.30, -.5))):
        point = center + direction * (x * width) + normal * (y * depth)
        path.moveTo(point) if index == 0 else path.lineTo(point)
    path.closeSubpath()
    return path


class ReferenceGeometry:
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
            first = QtCore.QPointF(wall.firstVertex.x(), -wall.firstVertex.y()) * geometryScale
            second = QtCore.QPointF(wall.secondVertex.x(), -wall.secondVertex.y()) * geometryScale
            direction = second - first
            length = math.hypot(direction.x(), direction.y())
            if length < 1e-10:
                continue
            normal = QtCore.QPointF(-direction.y(), direction.x()) * (wall.width * geometryScale / (2 * length))
            polygons.append(QtGui.QPolygonF([first + normal, second + normal, second - normal, first - normal]))
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
            # The fifth result clips finite bodies as well as join patches.
            # Keep a standalone clipping loop here rather than delegating the
            # reference construction to the app's numeric polygon backend.
            sources = list(zip(polygonWalls, polygons[:len(polygonWalls)])) + materialJoins + materialTransitions
            clippedSources = []
            for sourceIndex, (owner, polygon) in enumerate(sources):
                coordinates = self.PreparedWallPolygon(polygon)[0]
                for planeOrigin, normal in footprintCuts.get(id(owner), ()):
                    points = []
                    distances = [(x - planeOrigin[0]) * normal[0] + (y - planeOrigin[1]) * normal[1] for x, y in coordinates]
                    for index, first in enumerate(coordinates):
                        second = coordinates[(index + 1) % len(coordinates)]
                        firstDistance, secondDistance = distances[index], distances[(index + 1) % len(coordinates)]
                        if firstDistance <= 0:
                            points.append(first)
                        if (firstDistance <= 0) != (secondDistance <= 0):
                            fraction = firstDistance / (firstDistance - secondDistance)
                            points.append((first[0] + (second[0] - first[0]) * fraction,
                                           first[1] + (second[1] - first[1]) * fraction))
                    coordinates = points
                if sourceIndex >= len(polygonWalls):
                    area = sum(x * coordinates[(index + 1) % len(coordinates)][1]
                               - coordinates[(index + 1) % len(coordinates)][0] * y
                               for index, (x, y) in enumerate(coordinates))
                    if abs(area) <= 1e-9:
                        continue
                # Uncut sources keep their original Qt vertices and ordering.
                if footprintCuts.get(id(owner)):
                    polygon = QtGui.QPolygonF([QtCore.QPointF(*point) for point in coordinates])
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
        self.wallGeometryPath = (self.TraceWallBoundary(combinedPath, traceKey = ("walls", tuple(id(wall) for wall in walls)),
                                                      sourcePolygons = tracePolygons)
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
        self.wallGeometryKey = geometryKey
        return viewTransform.map(self.wallGeometryPath)


    def ObjectCorners(self, drawingObject):
        if isinstance(drawingObject, Column):
            delta = drawingObject.secondVertex - drawingObject.firstVertex
            length = math.hypot(delta.x(), delta.y())
            if length < 1e-8:
                return []
            offset = QtCore.QPointF(-delta.y(), delta.x()) * (drawingObject.width / (2 * length))
            return [drawingObject.firstVertex + offset, drawingObject.secondVertex + offset,
                    drawingObject.secondVertex - offset, drawingObject.firstVertex - offset]
        if isinstance(drawingObject, (Arrow, MeasurementGuide)):
            return [drawingObject.firstVertex, drawingObject.secondVertex]
        return list(self.ObjectFootprint(drawingObject)[1])


    def ObjectFootprint(self, drawingObject):
        if isinstance(drawingObject, Fireplace):
            key = (drawingObject.firstVertex.x(), drawingObject.firstVertex.y(),
                   drawingObject.secondVertex.x(), drawingObject.secondVertex.y(), drawingObject.depth,
                   drawingObject.depthOffset)
            cached = getattr(drawingObject, "footprintCache", None)
            if cached is not None and cached[0] == key:
                return cached[1]
            # Freeze the historical helper too: the live UI box now names its
            # axes like a wall, while collision geometry must remain identical.
            normal = drawingObject.Axes()[1]
            center = (drawingObject.firstVertex + drawingObject.secondVertex) / 2 + normal * drawingObject.depthOffset
            box = Furnishing({"key": "fireplace", "width": drawingObject.width, "length": drawingObject.depth}, center)
            box.firstVertex = center - normal * (drawingObject.depth / 2)
            box.secondVertex = center + normal * (drawingObject.depth / 2)
            footprint = self.ObjectFootprint(box)
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
        delta = second - first
        length = math.hypot(delta.x(), delta.y())
        if length < 1e-8:
            footprint = (QtCore.QRectF(), (), ())
        else:
            direction = delta / length
            normal = QtCore.QPointF(-direction.y(), direction.x())
            offset = normal * (width / 2)
            corners = (first + offset, second + offset, second - offset, first - offset)
            bounds = QtCore.QRectF(min(first.x(), second.x()) - abs(offset.x()),
                                  min(first.y(), second.y()) - abs(offset.y()),
                                  abs(delta.x()) + 2 * abs(offset.x()), abs(delta.y()) + 2 * abs(offset.y()))
            footprint = (bounds, corners, (direction, normal))
            if isinstance(drawingObject, Column):
                corners = tuple(ColumnPolygon(drawingObject))
                axes = []
                for index, point in enumerate(corners):
                    edge = corners[(index + 1) % len(corners)] - point
                    edgeLength = math.hypot(edge.x(), edge.y())
                    axes.append(QtCore.QPointF(-edge.y(), edge.x()) / edgeLength)
                footprint = (QtGui.QPolygonF(corners).boundingRect(), corners, tuple(axes))
        drawingObject.footprintCache = (key, footprint)
        if batch is not None:
            batch.setdefault("footprints", {})[id(drawingObject)] = footprint
        return footprint


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
                    for door in ownerDoors:
                        isDoor = isinstance(door, (Door, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway))
                        mode = self.measurementSettings["doors" if isDoor else "windows"]
                        if mode == 2 and not isinstance(door, Fireplace):
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
                        openingFirst, openingSecond = openingVertices[id(door)]
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
                            for fireplace in ownerDoors:
                                if not isinstance(fireplace, Fireplace):
                                    continue
                                fireplaceFirst, fireplaceSecond = openingVertices[id(fireplace)]
                                limits = sorted((QtCore.QPointF.dotProduct(fireplaceFirst - first, direction),
                                                 QtCore.QPointF.dotProduct(fireplaceSecond - first, direction)))
                                if openingStart < limits[0] - .01 or end > limits[1] + .01:
                                    continue
                                tangent, normal = fireplace.Axes()
                                wallCenter = (fireplaceFirst + fireplaceSecond) / 2
                                wallSide = QtCore.QPointF.dotProduct((dimensionFirst + dimensionSecond) / 2 - wallCenter, normal)
                                edge = fireplace.depthOffset + (fireplace.depth / 2 if wallSide > 0 else -fireplace.depth / 2)
                                shift = normal * (edge - wallSide)
                                dimensionFirst += shift
                                dimensionSecond += shift
                                break
                            openingOwners = [opening for opening in ownerDoors
                                             if min(QtCore.QPointF.dotProduct(openingVertices[id(opening)][0] - first, direction),
                                                    QtCore.QPointF.dotProduct(openingVertices[id(opening)][1] - first, direction)) <= openingStart + .01
                                             and max(QtCore.QPointF.dotProduct(openingVertices[id(opening)][0] - first, direction),
                                                     QtCore.QPointF.dotProduct(openingVertices[id(opening)][1] - first, direction)) >= end - .01]
                            dimensions.append((dimensionFirst, dimensionSecond, openingOwners or owners))
                        cursor = max(cursor, end)
                    if spanLength - cursor > 0.0001:
                        dimensions.append((first + direction * cursor, second, owners))
                    cached = tuple(dimensions[spanStart:])
                    points = len(cached) * 2 + len(ownerKey[-1]) * 2
                    if points <= 32768:
                        spanCache[spanKey] = (cached, points)
                        self.dimensionSpanCachePoints += points
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
        while len(spanCache) > min(8192, max(1024, len(walls) * 8)) or self.dimensionSpanCachePoints > 32768:
            spans, points = spanCache.pop(next(iter(spanCache)))
            self.dimensionSpanCachePoints -= points
        self.dimensionOwnerState = ((ownerStateKey, axisValues, ownerSpans)
                                    if len(axisValues) <= 4096 and len(ownerSpans) <= 8192 else None)
        self.dimensionCache = dimensions
        return dimensions


