"""Frozen geometry methods before history-size budgeting."""
from planner_app.viewport.geometry import *
from planner_app.viewport.geometry import GeometryMixin as CurrentGeometryMixin
from planner_app.viewport.widget import DrawingViewport


class ReferenceGeometryMixin(CurrentGeometryMixin):
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


class ReferenceViewport(ReferenceGeometryMixin, DrawingViewport):
    pass
