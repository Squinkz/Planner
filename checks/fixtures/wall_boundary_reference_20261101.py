"""Frozen wall assembly before eliminating redundant overlap probes."""
from planner_app.viewport.geometry import *

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
        # Snapping, room detection and paint alternate between full and partial
        # wall sets. Keep their exact assembled results within the shared native
        # budget. Limit retention/accounting overhead by enabling this for larger sets.
        assemblies = self.__dict__.get("wallAssemblyCache")
        if assemblies is None and len(walls) >= 16:
            assemblies = self.wallAssemblyCache = NativeGeometryCache(self.geometryCacheBudget)
        cachedAssembly = assemblies.get(geometryKey) if assemblies is not None else None
        if cachedAssembly is not None:
            (self.wallGeometryPath, self.wallFillPolygons,
             self.wallFootprintCuts, self.wallGeometryComponents) = cachedAssembly
            self.wallGeometryKey = geometryKey
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
        if assemblies is not None:
            # Admit repeated assemblies, rather than accounting every unique
            # cursor position. Hashes are only an admission hint: actual cache
            # lookup still uses the complete exact geometry key.
            candidates = self.__dict__.setdefault("wallAssemblyCandidates", {})
            signature = hash(geometryKey)
            if signature in candidates:
                assemblies[geometryKey] = (self.wallGeometryPath, self.wallFillPolygons,
                                           self.wallFootprintCuts, self.wallGeometryComponents)
            else:
                candidates[signature] = None
                while len(candidates) > 16:
                    candidates.pop(next(iter(candidates)))
            while len(assemblies) > 4:
                assemblies.popitem(last = False)
        return viewTransform.map(combined)
