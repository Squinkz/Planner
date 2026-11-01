from planner_app.viewport.geometry import *

class ReferenceGeometry:
    def CollisionCategoryGeometry(self, obj, excludedKey):
        """Share the exact owner/body footprints used by collision predicates."""
        batch = getattr(self, "collisionPassCache", None)
        cache = getattr(self, "collisionFootprintCache", {})
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
        self.collisionFootprintCache = cache
        return cache[type(obj)]
