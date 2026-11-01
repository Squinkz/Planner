from planner_app.viewport.geometry import *


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
        self.wallFootprintCuts = footprintCuts
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
                    area = PolygonTwiceArea(coordinates)
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
            fragments = ownershipCache.get(ownershipKey)
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
