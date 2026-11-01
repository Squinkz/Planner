"""Frozen wall preparation and edit eligibility before the room-edit pass."""
from planner_app.viewport.geometry import *
from planner_app.viewport.widget import DrawingViewport


class ReferenceViewport(DrawingViewport):
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

    def CanCacheEditScene(self):
        suppressed = getattr(self, "viewportEditSuppressedGesture", None)
        if suppressed is not None:
            if suppressed is not self.interactionBefore:
                self.viewportEditSuppressedGesture = None
        return (getattr(self, "editPaintEnabled", True) and self.solidObjects
                and len(self.walls) + len(self.windows) + len(self.furnishings) + len(self.labels) >= getattr(self, "editPaintMinimumObjects", 16)
                and self.dragStart is not None and self.isDragging and not self.isPanning
                and type(self.selectedWall) is Wall and self.selectedVertex is not None
                and not self.groupDrag and not self.dragCopies and not self.pendingShapeWalls
                and self.pendingWall is None and self.furnishingHandleDrag is None and not self.guiDragActive
                and self.axisConstraintOrigin is None and not self.alignmentGuides
                and len(self.SelectionEntries()) == 1
                and all(preview is None for preview in (self.furnishingPreview, self.windowDropPreview,
                    self.inactiveOpeningPreview, self.counterPreview, self.arrowPreview, self.labelPreview))
                and all(type(wall) is Wall for wall, index, position in self.ActiveAttachments()))
