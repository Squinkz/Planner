"""Frozen viewport methods after the first drag/railing optimization pass."""
from planner_app.viewport.geometry import *
from planner_app.viewport.rendering import *
from planner_app.viewport.widget import DrawingViewport

class ReferenceGeometry:
    def ContainedWalls(self, walls = None):
        walls = [wall for wall in (self.walls if walls is None else walls) if not isinstance(wall, (Stair, Arrow, MeasurementGuide, Railing))]
        footprints = [self.ObjectFootprint(wall) for wall in walls]
        cacheKey = tuple((id(wall), wall.footprintCache[0]) for wall in walls)
        if cacheKey == self.containedWallKey:
            return self.containedWallCache
        contained = []
        tolerance = .01
        expandedBounds = [bounds.adjusted(-tolerance, -tolerance, tolerance, tolerance) for bounds, corners, axes in footprints]
        boundsArray = None
        if len(walls) >= 64:
            np = LoadNumPy()
            boundsArray = np.array([bounds.getCoords() for bounds, corners, axes in footprints], dtype = np.float64)
            expandedArray = np.array([bounds.getCoords() for bounds in expandedBounds], dtype = np.float64)
            if not np.isfinite(boundsArray).all() or not np.isfinite(expandedArray).all():
                boundsArray = None
            else:
                # Qt accepts reversed rectangles. Normalize endpoints without
                # changing the original QRectF used by the final bounds check.
                boundsArray = np.column_stack((np.minimum(boundsArray[:, :2], boundsArray[:, 2:]),
                                               np.maximum(boundsArray[:, :2], boundsArray[:, 2:])))
                expandedArray = np.column_stack((np.minimum(expandedArray[:, :2], expandedArray[:, 2:]),
                                                 np.maximum(expandedArray[:, :2], expandedArray[:, 2:])))
                validCorners = np.array([bool(corners) for bounds, corners, axes in footprints])
        for index, wall in enumerate(walls):
            if boundsArray is not None and index % 64 == 0:
                # Bound temporary memory to 64 rows, not a retained N-by-N
                # matrix. Candidate columns preserve original ownership order.
                block = boundsArray[index:index + 64]
                candidates = expandedArray[None, :, 0] <= block[:, None, 0]
                candidates &= expandedArray[None, :, 1] <= block[:, None, 1]
                candidates &= expandedArray[None, :, 2] >= block[:, None, 2]
                candidates &= expandedArray[None, :, 3] >= block[:, None, 3]
                candidates &= validCorners[None, :]
            bounds, corners, axes = footprints[index]
            if not corners:
                continue
            otherIndices = np.flatnonzero(candidates[index % 64]) if boundsArray is not None else range(len(walls))
            for otherIndex in otherIndices:
                if index == otherIndex:
                    continue
                otherBounds, otherCorners, otherAxes = footprints[otherIndex]
                if not otherCorners or not expandedBounds[otherIndex].contains(bounds):
                    continue
                numericCorners, numericAxes = self.NumericCollisionFootprint(wall, footprints[index])
                otherNumericCorners, otherNumericAxes = self.NumericCollisionFootprint(walls[otherIndex], footprints[otherIndex])
                containedOnAxes, equalBounds = FootprintContainment(numericCorners, otherNumericCorners,
                                                                   otherNumericAxes, tolerance)
                # Coincident duplicates flag the later wall, leaving one normal wall.
                if containedOnAxes and (not equalBounds or index > otherIndex):
                    contained.append(wall)
                    break
        self.containedWallKey = cacheKey
        self.containedWallCache = contained
        return contained

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

class ReferenceRendering:
    def DrawScene(self, painter, drawingRect, origin, pixelsPerMillimeter, dirtyRects = None,
                  drawAnnotations = True, retainAnnotations = False, bakePassageClips = False, passageClearance = None):
        bakePassageClips = (bakePassageClips or bool(self.windows)
                           and painter.paintEngine().type() == QtGui.QPaintEngine.Type.SVG)
        if passageClearance is None:
            passageClearance = 0
            # Remove clipped wall-stroke fringes in both room styles. Canvas
            # passages get explicit thin edges instead of leftover stroke ink.
            # Retain destination sampling/DPR through transparent recording.
            inverseDevice, invertible = painter.deviceTransform().inverted()
            if invertible:
                passageClearance = math.hypot(inverseDevice.m11(), inverseDevice.m12(), inverseDevice.m21(), inverseDevice.m22())
        if not self.solidObjects:
            retainCapture = getattr(self, "retainExportCapture", False) and isinstance(painter.device(), QtGui.QImage)
            captures = getattr(self, "exportObjectCaptures", [])
            captureKey = None
            retained = None
            if retainCapture:
                captureKey = self.SceneRenderKey((self.zoom, self.basePixelsPerMillimeter,
                    self.width(), self.height(), drawingRect.x(), drawingRect.y(), drawingRect.width(), drawingRect.height(),
                    origin.x(), origin.y(), pixelsPerMillimeter, bakePassageClips, passageClearance,
                    self.floors, self.wallStyle, self.font().toString(), painter.font().toString(),
                    painter.renderHints().value, painter.device().logicalDpiX(), painter.device().logicalDpiY(),
                    tuple(themeColors.items())))
                for index, capture in enumerate(captures):
                    if capture[0] == captureKey:
                        retained = capture
                        captures.append(captures.pop(index))
                        break
            if retained is not None:
                device, sceneState = retained[1:3]
            else:
                device = ObjectPaintDevice(self.size(), themeColors["canvas"])
                sourcePainter = PathTextPainter(device)
                originalRenderers = (self.furnishingRenderers, self.selectedFurnishingRenderers, self.groupedFurnishingRenderers)
                try:
                    sourcePainter.setFont(painter.font())
                    sourcePainter.setRenderHints(painter.renderHints())
                    sourcePainter.setClipRect(drawingRect)
                    self.solidObjects = True
                    self.objectCaptureEngine = device.engine
                    captureRenderers = (
                        (renderers.Copy(solidBackground = True) if hasattr(renderers, "Copy") else
                         {key: getattr(renderer, "solidRenderer", renderer) for key, renderer in renderers.items()})
                        for renderers in originalRenderers)
                    # These are temporary paint resources, not a scene edit.
                    # Bypass the viewport's edit observer while borrowing them,
                    # then restore the exact original maps and their ownership.
                    for name, renderers in zip(("furnishingRenderers", "selectedFurnishingRenderers", "groupedFurnishingRenderers"), captureRenderers):
                        object.__setattr__(self, name, renderers)
                    sceneState = self.DrawScene(sourcePainter, drawingRect, origin, pixelsPerMillimeter,
                                                dirtyRects, drawAnnotations = False, bakePassageClips = bakePassageClips,
                                                passageClearance = passageClearance)
                finally:
                    sourcePainter.end()
                    self.solidObjects = False
                    self.objectCaptureEngine = None
                    for name, renderers in zip(("furnishingRenderers", "selectedFurnishingRenderers", "groupedFurnishingRenderers"), originalRenderers):
                        object.__setattr__(self, name, renderers)
                if retainCapture:
                    elements = imageBytes = 0
                    seenClips = set()
                    for path, pen, brush, transform, opacity, clip, mask, hints, brushOrigin in device.engine.commands:
                        if isinstance(path, tuple):
                            imageBytes += path[1].sizeInBytes()
                        else:
                            elements += path.elementCount()
                        elements += mask.elementCount()
                        if clip is not None and id(clip) not in seenClips:
                            seenClips.add(id(clip))
                            elements += clip.elementCount()
                    captures.append((captureKey, device, sceneState, elements, imageBytes))
                    # Retain original Qt commands, not a serialized or scaled
                    # picture. Bound both native geometry and embedded images.
                    while captures and (len(captures) > 4 or sum(len(item[1].engine.commands) for item in captures) > 8192
                            or sum(item[3] for item in captures) > 262144 or sum(item[4] for item in captures) > 16 * 1024 * 1024):
                        captures.pop(0)
                    self.exportObjectCaptures = captures
            device.engine.Replay(painter, drawingRect, clipCache = self.objectClipCache)
            if drawAnnotations:
                self.DrawSceneMeasurements(painter, drawingRect, sceneState, dirtyRects, retainCommands = retainAnnotations)
            return sceneState
        stablePreparation = (self.dragStart is None and not self.isDragging and self.pendingWall is None
                             and not self.pendingShapeWalls and self.furnishingHandleDrag is None and not self.guiDragActive
                             and all(preview is None for preview in (self.furnishingPreview, self.windowDropPreview,
                                     self.inactiveOpeningPreview, self.counterPreview, self.arrowPreview, self.labelPreview)))
        changes = self.renderChanges
        preparationKey = (changes.geometry, changes.appearance, changes.topology, changes.visibility,
                          tuple(self.visibility.items()), tuple(self.collisionSettings.items()),
                          getattr(self, "exportRender", False), self.basePixelsPerMillimeter)
        preparation = getattr(self, "scenePreparation", None)
        if not stablePreparation or preparation is None or preparation[0] != preparationKey:
            prepared = {}
            if stablePreparation:
                self.scenePreparation = (preparationKey, prepared)
        else:
            prepared = preparation[1]
        containedObjects = prepared.get("containedObjects")
        if containedObjects is None:
            containedObjects = prepared["containedObjects"] = ([] if getattr(self, "exportRender", False) else
                self.ContainedWalls([obj for obj in self.walls if self.IsObjectVisible(obj)]))
        advisoryIds = prepared.get("architecturalAdvisories")
        if advisoryIds is None:
            advisoryIds = prepared["architecturalAdvisories"] = ({id(obj) for obj in containedObjects + self.DuplicateArchitecturalObjects()}
                if not getattr(self, "exportRender", False) else set())
        invalidArchitecture = prepared.get("invalidArchitecture")
        if invalidArchitecture is None:
            invalidArchitecture = prepared["invalidArchitecture"] = self.InvalidArchitecturalObjects()
        highlightedWall = (self.windowDropPreview if self.windowDropPreview is not None else
                           self.counterPreview if self.counterPreview is not None else
                           self.pendingWall if self.pendingWall is not None else
                           None if self.inactiveOpeningPreview is not None and self.dragStart is not None else self.selectedWall)
        renderedSelection = (self.pendingShiftSelection[0] if self.pendingShiftSelection is not None and not self.isDragging
                             else self.SelectionEntries())
        highlightedObjects = [obj for obj, index in renderedSelection]
        if self.inactiveOpeningPreview is not None:
            highlightedObjects = []
        if self.windowDropPreview is not None or self.counterPreview is not None or self.pendingWall is not None:
            highlightedObjects = self.pendingShapeWalls or [highlightedWall]
        highlightedObjects = list({id(obj): obj for obj in highlightedObjects}.values())
        highlightedObjects = [obj for obj in highlightedObjects if self.IsObjectVisible(obj)]
        highlightedIds = {id(obj) for obj in highlightedObjects}
        groupedIds = prepared.get("groups")
        if groupedIds is None:
            groupedIds = prepared["groups"] = {id(obj) for group in self.objectGroups for obj in group}
        movingFurnishingIds = {id(obj) for obj, index, position in self.ActiveAttachments() if isinstance(obj, Furnishing)}
        if isinstance(self.selectedWall, Furnishing) and self.dragStart is not None:
            movingFurnishingIds.add(id(self.selectedWall))
        handleMembers = self.furnishingHandleDrag["members"] if self.furnishingHandleDrag is not None else []
        handleMemberIds = {id(state[0]) for state in handleMembers}
        movingFurnishingIds.update(handleMemberIds)
        handleState = self.furnishingHandleDrag
        invalidHandleGroup = (not handleState["rotationValid"] if handleState is not None and handleState.get("structuralRotation", False)
                              else any(not self.FurnishingFits(state[0]) for state in handleMembers))
        invalidWalls = {id(wall): wall for wall in self.walls
                        if type(wall) in (Wall, Pillar, Column, Elevator) and id(wall) in invalidArchitecture}
        if self.pendingShapeWalls:
            extent = self.pendingWall.secondVertex - self.pendingWall.firstVertex
            if abs(extent.x()) < 1 or abs(extent.y()) < 1 or any(not self.WallFits(wall) for wall in self.pendingShapeWalls):
                invalidWalls.update({id(wall): wall for wall in self.pendingShapeWalls})
        elif self.pendingWall is not None and not self.WallFits(self.pendingWall):
            invalidWalls[id(self.pendingWall)] = self.pendingWall
        selectedVertexKeys = {(id(obj), index) for obj, index in renderedSelection if index is not None}
        visibleCounters = prepared.get("counters")
        if visibleCounters is None:
            visibleCounters = [counter for counter in self.walls if isinstance(counter, Counter)]
            if self.counterPreview is not None:
                visibleCounters.append(self.counterPreview)
            visibleCounters = prepared["counters"] = [counter for counter in visibleCounters if self.IsObjectVisible(counter)]
        self.preparedCounterMembers = visibleCounters if stablePreparation else None
        validationKey = prepared.get("blockers")
        if validationKey is None:
            blockerKeys = []
            for wall in self.walls:
                self.ObjectFootprint(wall)
                blockerKeys.append((id(wall), wall.footprintCache[0]))
            validationKey = prepared["blockers"] = tuple(blockerKeys)
        if validationKey != self.furnishingValidationKey:
            self.furnishingValidationKey = validationKey
            self.furnishingValidationCache = {}
        validationCache = dict(self.furnishingValidationCache) if dirtyRects is not None else {}
        duplicateIds = prepared.get("duplicateFurnishings")
        if duplicateIds is None:
            duplicateIds = prepared["duplicateFurnishings"] = {id(obj) for obj in self.DuplicateFurnishings()}
        furnishingLayers = prepared.get("furnishingLayers")
        if furnishingLayers is None:
            furnishingLayers = {True: [], False: []}
            for obj in self.furnishings + ([self.furnishingPreview] if self.furnishingPreview is not None else []):
                if not isinstance(obj, NorthArrow) and self.IsObjectVisible(obj):
                    furnishingLayers[obj.behindCounters].append(obj)
            prepared["furnishingLayers"] = furnishingLayers
        furnishingBounds = prepared.setdefault("furnishingBounds", {})
        occludedFurnishings = prepared.get("occludedFurnishings")
        if occludedFurnishings is None:
            occludedFurnishings = prepared["occludedFurnishings"] = {
                id(obj) for group in self.CoincidentObjectGroups() if type(group[0]) is Furnishing for obj in group[:-1]}
        def DrawFurnishings(behindCounters):
            for obj in furnishingLayers[behindCounters]:
                # Exact rear copies cannot contribute visible artwork. Painting
                # their dark strokes under the warning leaves dark antialias fringes.
                if id(obj) in occludedFurnishings:
                    continue
                bounds = furnishingBounds.get(id(obj))
                if bounds is None:
                    renderers = self.furnishingRenderers
                    artwork = (renderers.ArtworkGeometry(obj.definition["key"]) if hasattr(renderers, "ArtworkGeometry")
                               else renderers[obj.definition["key"]])
                    bounds = self.ObjectFootprint(obj)[0].united(FurnishingArtworkBounds(obj, artwork))
                    furnishingBounds[id(obj)] = bounds
                screenBounds = QtCore.QRectF(self.WorldToViewport(bounds.topLeft()), self.WorldToViewport(bounds.bottomRight())).normalized()
                if not screenBounds.adjusted(-2, -2, 2, 2).intersects(drawingRect):
                    continue
                padding = self.lineWidths["furnishings"] + 2
                if dirtyRects is not None and not any(screenBounds.adjusted(-padding, -padding, padding, padding).intersects(rect) for rect in dirtyRects):
                    continue
                self.ObjectFootprint(obj)
                key = obj.footprintCache[0]
                cached = self.furnishingValidationCache.get(id(obj))
                if self.dragStart is not None and obj is not self.furnishingPreview and id(obj) not in movingFurnishingIds:
                    invalid = False
                    # Suppression is not a validated result. Keep this entry
                    # absent so release/cancel performs the real check.
                    validationCache.pop(id(obj), None)
                else:
                    invalid = cached[1] if cached is not None and cached[0] == key else not self.FurnishingFits(obj)
                    validationCache[id(obj)] = (key, invalid)
                if id(obj) in handleMemberIds and invalidHandleGroup:
                    invalid = True
                renderers = self.selectedFurnishingRenderers if id(obj) in highlightedIds and not invalid else self.furnishingRenderers
                if id(obj) in highlightedIds and id(obj) in groupedIds and not invalid:
                    key = obj.definition["key"]
                    if key not in self.groupedFurnishingRenderers:
                        self.groupedFurnishingRenderers[key] = SelectedFurnishingRenderer(obj.definition.get("graphicData") or obj.definition["imagePath"], self.SelectionColor(obj),
                            lineWidth = self.lineWidths["furnishings"], nominalSize = (obj.definition["width"], obj.definition["length"]))
                    renderers = self.groupedFurnishingRenderers
                duplicate = id(obj) in duplicateIds
                if duplicate and not invalid:
                    warningRenderers = prepared.setdefault("duplicateRenderers", {})
                    key = obj.definition["key"]
                    if key not in warningRenderers:
                        warningRenderers[key] = FurnishingRenderer(obj.definition.get("graphicData") or obj.definition["imagePath"],
                            selectionColor = themeColors["warningOutline"], lineWidth = self.lineWidths["furnishings"],
                            nominalSize = (obj.definition["width"], obj.definition["length"]))
                    renderers = warningRenderers
                painter.save()
                try:
                    DrawFurnishing(painter, obj, self.WorldToViewport(obj.firstVertex), self.WorldToViewport(obj.secondVertex),
                                   pixelsPerMillimeter, renderers[obj.definition["key"]],
                                   id(obj) in highlightedIds, invalid, selectionColor = themeColors["warningOutline"] if duplicate else self.SelectionColor(obj),
                                   drawBounds = id(obj) not in highlightedIds)
                finally:
                    painter.restore()
        DrawFurnishings(True)
        invalidCounterIds = set()
        if visibleCounters:
            painter.save()
            counterPath, _, counterPolygons = self.ConnectedCounterPath(visibleCounters, False)
            painter.fillPath(counterPath, QtGui.QColor(themeColors["canvas"]))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(LinePen(themeColors["wallOutline"], self.lineWidths["architectural"]))
            painter.drawPath(counterPath)
            movingCounterIds = {id(obj) for obj, index, position in self.ActiveAttachments() if isinstance(obj, Counter)}
            if self.dragStart is not None and isinstance(self.selectedWall, Counter):
                movingCounterIds.add(id(self.selectedWall))
            if self.counterPreview is not None:
                movingCounterIds.add(id(self.counterPreview))
            for counter in visibleCounters:
                invalid = id(counter) in invalidArchitecture or id(counter) in movingCounterIds and not self.CounterFits(counter)
                warning = id(counter) in advisoryIds or id(counter) in invalidArchitecture and self.dragStart is None
                if invalid:
                    invalidCounterIds.add(id(counter))
                if id(counter) not in highlightedIds and not invalid and not warning:
                    continue
                clip = QtGui.QPainterPath()
                clip.setFillRule(QtCore.Qt.FillRule.WindingFill)
                for owner, polygon in counterPolygons:
                    if owner is counter:
                        clip.addPolygon(polygon)
                        clip.closeSubpath()
                clip = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom).map(clip)
                # Merging coincident counters can assign their entire surface to
                # the rear owner. The front warning still owns its footprint.
                if clip.isEmpty() and (invalid or warning):
                    clip.addPolygon(self.WallPolygon(counter))
                    clip.closeSubpath()
                painter.save()
                painter.setClipPath(clip, QtCore.Qt.ClipOperation.IntersectClip)
                if id(counter) in highlightedIds and not invalid and not warning:
                    painter.fillPath(counterPath, QtGui.QColor(themeColors["groupSelectionFill"] if id(counter) in groupedIds else themeColors["selectionFill"]))
                painter.restore()
                # Include the full stroke, rather than leaving half the normal
                # outline visible outside the surface clip.
                stroke = QtGui.QPainterPathStroker()
                stroke.setWidth(self.lineWidths["architectural"] + 2)
                painter.save()
                painter.setClipPath(clip.united(stroke.createStroke(clip)), QtCore.Qt.ClipOperation.IntersectClip)
                color = (themeColors["warningOutline"] if warning else
                         themeColors["invalidOutline"] if invalid else self.SelectionColor(counter))
                painter.setPen(LinePen(color, self.lineWidths["architectural"]))
                painter.drawPath(counterPath)
                painter.restore()
            painter.restore()
        DrawFurnishings(False)
        self.furnishingValidationCache = validationCache
        previewWalls = self.pendingShapeWalls or ([self.pendingWall] if self.pendingWall is not None else [])
        visibleWalls = prepared.get("walls")
        if visibleWalls is None:
            visibleWalls = [wall for wall in self.walls if type(wall) in (Wall, Pillar, Column)] + previewWalls
        if isinstance(self.arrowPreview, Pillar) and not isinstance(self.arrowPreview, Elevator):
            visibleWalls.append(self.arrowPreview)
            if not self.WallFits(self.arrowPreview):
                invalidWalls[id(self.arrowPreview)] = self.arrowPreview
        if "walls" not in prepared:
            visibleWalls = prepared["walls"] = [wall for wall in visibleWalls if self.IsObjectVisible(wall)]
        containedWalls = prepared.get("contained")
        if containedWalls is None:
            containedWalls = prepared["contained"] = [obj for obj in containedObjects if type(obj) in (Wall, Pillar, Column)]
            if previewWalls:
                containedWalls = prepared["contained"] = list({id(obj): obj for obj in
                    containedWalls + self.ContainedWalls(visibleWalls)}.values())
        self.preparedWallMembers = visibleWalls if stablePreparation else None
        self.preparedWallRevision = preparationKey
        combinedPath = self.ConnectedWallPath(visibleWalls)
        # Validation can reuse the exact owner fills prepared for this frame.
        if self.dragStart is not None and self.isDragging:
            movingWalls = {id(wall): wall for wall in [self.selectedWall] + [wall for wall, index, position in self.ActiveAttachments()]}
            blockers = self.furnishings + [wall for wall in self.walls if isinstance(wall, (Counter, Railing, Stair, Elevator))]
            invalidWalls.update({wallId: wall for wallId, wall in movingWalls.items()
                                 if type(wall) in (Wall, Pillar, Column, Elevator) and not self.WallFits(wall, blockers = blockers)})
        # Share one pattern origin so hatching continues across wall junctions.
        painter.setBrushOrigin(origin)
        detachedIds = {id(obj) for obj, index in self.groupEntries} if self.groupOpeningPreviews else {id(self.selectedWall)}
        visibleWindows = [opening for opening in self.windows
                          if not (self.inactiveOpeningPreview is not None and self.dragStart is not None
                                  and id(opening) in detachedIds)] + ([self.windowDropPreview] if isinstance(self.windowDropPreview, Window) else [])
        visibleWindows = [opening for opening in visibleWindows if self.IsObjectVisible(opening)]
        # Parent projection/fraction clamping is scene geometry, not camera work.
        # Keep detached world endpoints under the existing revision key, then
        # transform them at the exact current camera position for native pixels.
        worldOpeningPositions = prepared.get("openingPositions")
        if worldOpeningPositions is None:
            worldOpeningPositions = prepared["openingPositions"] = {
                id(opening): (opening.firstVertex, opening.secondVertex) for opening in visibleWindows}
        openingPositions = {key: (self.WorldToViewport(first), self.WorldToViewport(second))
                            for key, (first, second) in worldOpeningPositions.items()}
        painter.save()
        doorwayClip = QtGui.QPainterPath()
        doorwayClip.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
        doorwayClip.addRect(drawingRect)
        openingClipRect = drawingRect.adjusted(-2, -2, 2, 2)
        # A scrolled pan raster only paints these exposed strips. Distant holes
        # enlarge Qt's clip work even though none of their pixels can be written.
        openingPaintRects = ([rect.adjusted(-2, -2, 2, 2) for rect in dirtyRects]
                             if self.isPanning and dirtyRects is not None else (openingClipRect,))
        jambNeighbors = prepared.setdefault("openingJambNeighbors", {})
        openingCuts = []
        openingCutPolygons = []
        for opening in visibleWindows:
            # Actual wall cuts end at the square-capped jambs. Do not enlarge
            # them along with the separate stair occlusion clearance below.
            firstPoint, secondPoint = openingPositions[id(opening)]
            # Clear the stroke's antialias fringe across passages. Only
            # the wall-normal clearance grows; jamb positions stay exact.
            for polygonIndex, polygon in enumerate(WallOpeningPolygons(opening, firstPoint, secondPoint, pixelsPerMillimeter, self.lineWidths["walls"],
                                                                       outlineClearance = passageClearance)):
                convexCuts = [polygon]
                if passageClearance > 0 and (not isinstance(opening, PocketDoor) or polygonIndex == 0):
                    # Protect a jamb only where another wall actually meets it;
                    # blanket protection leaves short fringes at small scales.
                    along = polygon[1] - polygon[0]
                    length = math.hypot(along.x(), along.y())
                    across = polygon[0] - polygon[3]
                    thickness = math.hypot(across.x(), across.y())
                    if length > 1e-10 and thickness > 1e-10:
                        neighborKey = id(opening), polygonIndex
                        protected = jambNeighbors.get(neighborKey)
                        if protected is None:
                            worldFirst, worldSecond = worldOpeningPositions[id(opening)]
                            worldDirection = worldSecond - worldFirst
                            worldLength = math.hypot(worldDirection.x(), worldDirection.y())
                            halfWidth = (opening.parentWall.width if isinstance(opening, Fireplace) else opening.width) / 2
                            worldNormal = QtCore.QPointF(-worldDirection.y(), worldDirection.x()) * (halfWidth / max(worldLength, 1e-20))
                            jambTolerance = .1
                            run = secondPoint - firstPoint
                            runSquared = QtCore.QPointF.dotProduct(run, run)
                            protected = []
                            for endpoint in ((polygon[0] + polygon[3]) / 2, (polygon[1] + polygon[2]) / 2):
                                fraction = QtCore.QPointF.dotProduct(endpoint - firstPoint, run) / max(runSquared, 1e-20)
                                position = worldFirst + (worldSecond - worldFirst) * fraction
                                jambPoints = (position, position + worldNormal, position - worldNormal)
                                touchesWall = False
                                for wall in visibleWalls:
                                    if wall is opening.parentWall:
                                        continue
                                    bounds, corners, _ = self.ObjectFootprint(wall)
                                    if not any(bounds.adjusted(-jambTolerance, -jambTolerance, jambTolerance, jambTolerance).contains(jambPoint) for jambPoint in jambPoints):
                                        continue
                                    footprint = QtGui.QPolygonF(corners)
                                    if any(footprint.containsPoint(jambPoint + offset, QtCore.Qt.FillRule.OddEvenFill)
                                           for jambPoint in jambPoints
                                           for offset in (QtCore.QPointF(), QtCore.QPointF(jambTolerance, 0), QtCore.QPointF(-jambTolerance, 0),
                                                          QtCore.QPointF(0, jambTolerance), QtCore.QPointF(0, -jambTolerance),
                                                          QtCore.QPointF(jambTolerance, jambTolerance), QtCore.QPointF(-jambTolerance, jambTolerance),
                                                          QtCore.QPointF(jambTolerance, -jambTolerance), QtCore.QPointF(-jambTolerance, -jambTolerance))):
                                        touchesWall = True
                                        break
                                protected.append(touchesWall)
                            jambNeighbors[neighborKey] = protected
                        if any(protected):
                            inset = along / length * min(self.lineWidths["walls"] / 2, length / 2)
                            firstInset = inset if protected[0] else QtCore.QPointF()
                            secondInset = inset if protected[1] else QtCore.QPointF()
                            guard = across / thickness * (passageClearance + self.lineWidths["walls"] / 2)
                            first, second, third, fourth = polygon
                            polygon = QtGui.QPolygonF([first - guard, first + firstInset - guard, first + firstInset,
                                second - secondInset, second - secondInset - guard, second - guard,
                                third + guard, third - secondInset + guard, third - secondInset,
                                fourth + firstInset, fourth + firstInset + guard, fourth + guard])
                            convexCuts = [QtGui.QPolygonF([first + firstInset, second - secondInset,
                                                          third - secondInset, fourth + firstInset])]
                            if protected[0]:
                                convexCuts.append(QtGui.QPolygonF([first - guard, first + firstInset - guard,
                                                                   fourth + firstInset + guard, fourth + guard]))
                            if protected[1]:
                                convexCuts.append(QtGui.QPolygonF([second - secondInset - guard, second - guard,
                                                                   third + guard, third - secondInset + guard]))
                if self.isPanning and not any(polygon.boundingRect().intersects(rect) for rect in openingPaintRects):
                    continue
                doorwayClip.addPolygon(polygon)
                doorwayClip.closeSubpath()
                if bakePassageClips:
                    openingCutPolygons.extend((cut.boundingRect(), cut) for cut in convexCuts)
                    cut = QtGui.QPainterPath()
                    cut.addPolygon(polygon)
                    cut.closeSubpath()
                    openingCuts.append(cut)
        if not bakePassageClips:
            painter.setClipPath(doorwayClip, QtCore.Qt.ClipOperation.IntersectClip)
        materialKey = prepared.get("materials")
        if materialKey is None:
            materialKey = prepared["materials"] = (self.wallGeometryKey, tuple((type(wall), wall.material) for wall in visibleWalls))
        if materialKey != self.materialGeometryKey:
            self.materialPaths = {}
            self.wallMaterialPaths = {}
            ownerPolygons = {}
            for wall, polygon in self.wallFillPolygons:
                ownerPolygons.setdefault(id(wall), (wall, []))[1].append(polygon)
            columnPaths = getattr(self, "columnMaterialPaths", {})
            columnFill = QtGui.QPainterPath()
            columnFill.setFillRule(QtCore.Qt.FillRule.WindingFill)
            for path in columnPaths.values():
                columnFill.addPath(path)
            for wall, polygons in ownerPolygons.values():
                polygons = tuple(polygons)
                cached = self.wallMaterialPathCache.get(id(wall))
                if isinstance(wall, Column):
                    wallPath = columnPaths[id(wall)]
                elif cached is None or cached[0] != polygons:
                    wallPath = QtGui.QPainterPath()
                    wallPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
                    for polygon in polygons:
                        area = sum(polygon[index].x() * polygon[(index + 1) % len(polygon)].y()
                                   - polygon[(index + 1) % len(polygon)].x() * polygon[index].y()
                                   for index in range(len(polygon)))
                        polygon = QtGui.QPolygonF(list(reversed(polygon))) if area < 0 else polygon
                        wallPath.addPolygon(polygon)
                        wallPath.closeSubpath()
                    self.wallMaterialPathCache[id(wall)] = (polygons, wallPath)
                else:
                    wallPath = cached[1]
                if not isinstance(wall, Column) and not columnFill.isEmpty() and wallPath.boundingRect().intersects(columnFill.boundingRect()):
                    wallPath = Paths.Difference(wallPath, columnFill)
                path = self.materialPaths.setdefault(wall.material, QtGui.QPainterPath())
                path.setFillRule(QtCore.Qt.FillRule.WindingFill)
                path.addPath(wallPath)
                self.wallMaterialPaths[id(wall)] = wallPath
            self.wallMaterialPathCache = {wallId: cached for wallId, cached in self.wallMaterialPathCache.items()
                                          if wallId in self.wallMaterialPaths}
            self.materialGeometryKey = materialKey
        viewTransform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
        captureEngine = getattr(self, "objectCaptureEngine", None)
        if captureEngine is not None:
            captureEngine.captureBackground = False
        if self.wallStyle != "Outline":
            materialPaths = self.materialPaths
            if dirtyRects is not None and self.viewportEditRaster is not None and self.CanCacheEditScene():
                materialPaths = {}
                owners = {id(wall): wall for wall in visibleWalls}
                for wallId, path in self.wallMaterialPaths.items():
                    bounds = viewTransform.mapRect(path.boundingRect()).adjusted(-2, -2, 2, 2)
                    if any(bounds.intersects(rect) for rect in dirtyRects):
                        material = owners[wallId].material
                        localPath = materialPaths.setdefault(material, QtGui.QPainterPath())
                        localPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
                        localPath.addPath(path)
            if bakePassageClips:
                # Clip each owner's simple footprint before regrouping fills.
                # A boolean against the building-sized compound path can lose
                # unrelated wall strips when nearly coincident edges collapse.
                materialPaths = {}
                owners = {id(wall): wall for wall in visibleWalls}
                columnPaths = getattr(self, "columnMaterialPaths", {})
                clippedOwners = set()
                for owner, polygon in self.wallFillPolygons:
                    if isinstance(owner, Column):
                        continue
                    if columnPaths:
                        if id(owner) in clippedOwners:
                            continue
                        clippedOwners.add(id(owner))
                        # These owner paths already exclude native column fills.
                        fragments = [list(polygon) for polygon in viewTransform.map(self.wallMaterialPaths[id(owner)]).toFillPolygons()]
                    else:
                        fragments = [list(viewTransform.map(polygon))]
                    material = owner.material
                    localPath = materialPaths.setdefault(material, QtGui.QPainterPath())
                    localPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
                    localPath.addPath(self.CutOpeningPolygons(fragments, openingCutPolygons))
                for wallId, ownerPath in self.wallMaterialPaths.items():
                    if not isinstance(owners[wallId], Column):
                        continue
                    clipped = viewTransform.map(ownerPath)
                    for cut in openingCuts:
                        if clipped.boundingRect().intersects(cut.boundingRect()):
                            clipped = clipped.subtracted(cut)
                    localPath = materialPaths.setdefault(owners[wallId].material, QtGui.QPainterPath())
                    localPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
                    localPath.addPath(clipped)
            for material, path in materialPaths.items():
                brush = QtGui.QBrush(QtGui.QColor(themeColors["wallOutline"])) if self.wallStyle == "Solid" else self.materialBrushes[(material, False)]
                fillPath = path if bakePassageClips else viewTransform.map(path)
                painter.fillPath(fillPath, brush)
        if captureEngine is not None:
            captureEngine.captureBackground = True
        for selectedObject in highlightedObjects:
            if isinstance(selectedObject, (Arrow, MeasurementGuide, Counter, Railing, Stair, Furnishing, Label, Fireplace, Elevator)) or id(selectedObject) in invalidWalls:
                continue
            selectionPath = QtGui.QPainterPath()
            if isinstance(selectedObject, Column):
                selectionPath = viewTransform.map(self.columnMaterialPaths[id(selectedObject)])
            else:
                selectionPath.addPolygon(self.WallPolygon(selectedObject))
                selectionPath.closeSubpath()
            # This polygon is already included in combinedPath. A boolean
            # intersection at coincident angled edges can spill into neighbors.
            material = selectedObject.material if isinstance(selectedObject, Wall) else "Generic"
            painter.save()
            if isinstance(selectedObject, Wall):
                painter.setClipPath(viewTransform.map(self.wallMaterialPaths.get(id(selectedObject), QtGui.QPainterPath())),
                                    QtCore.Qt.ClipOperation.IntersectClip)
            brush = self.groupedMaterialBrushes[material] if id(selectedObject) in groupedIds else self.materialBrushes[(material, True)]
            painter.fillPath(selectionPath, brush)
            painter.restore()
        painter.save()
        # Installing a building-sized clip can dominate SVG rendering even
        # when there are no lumber cross-lines to draw. Submit it lazily for
        # the first visible lumber wall, just as during panning.
        lumberClipSet = False
        for wall in visibleWalls:
            if wall.material == "Lumber":
                polygon = self.WallPolygon(wall)
                if len(polygon) == 4 and polygon.boundingRect().intersects(drawingRect):
                    if not lumberClipSet:
                        painter.setClipPath(combinedPath, QtCore.Qt.ClipOperation.IntersectClip)
                        lumberClipSet = True
                    painter.save()
                    painter.setClipPath(viewTransform.map(self.wallMaterialPaths.get(id(wall), QtGui.QPainterPath())),
                                        QtCore.Qt.ClipOperation.IntersectClip)
                    painter.setPen(QtGui.QPen(QtGui.QColor(self.SelectionColor(wall) if id(wall) in highlightedIds and id(wall) not in invalidWalls else themeColors["invalidOutline"]), 1))
                    cuts = {0.0, 1.0}
                    for opening in visibleWindows:
                        if opening.parentWall is wall:
                            cuts.update((max(0.0, min(1.0, opening.firstFraction)),
                                         max(0.0, min(1.0, opening.secondFraction))))
                    cuts = sorted(cuts)
                    firstEdge = polygon[1] - polygon[0]
                    secondEdge = polygon[2] - polygon[3]
                    for start, end in zip(cuts, cuts[1:]):
                        if end - start < 1e-10:
                            continue
                        painter.drawLine(QtCore.QLineF(polygon[0] + firstEdge * start,
                                                       polygon[3] + secondEdge * end))
                        painter.drawLine(QtCore.QLineF(polygon[3] + secondEdge * start,
                                                       polygon[0] + firstEdge * end))
                    painter.restore()
        painter.restore()
        windowOutlineClip = QtGui.QPainterPath()
        windowOutlineCuts = []
        windowOutlineClip.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
        windowOutlineClip.addRect(drawingRect)
        for window in visibleWindows:
            if isinstance(window, (Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway, Fireplace)):
                continue
            polygon = self.WallPolygon(window)
            if self.isPanning:
                bounds = polygon.boundingRect().adjusted(-self.lineWidths["walls"] - 2, -self.lineWidths["walls"] - 2,
                                                         self.lineWidths["walls"] + 2, self.lineWidths["walls"] + 2)
                if not any(bounds.intersects(rect) for rect in openingPaintRects):
                    continue
            openingPath = QtGui.QPainterPath()
            openingPath.addPolygon(polygon)
            openingPath.closeSubpath()
            painter.fillPath(openingPath, QtGui.QColor(themeColors["canvas"]))
            firstPoint, secondPoint = openingPositions[id(window)]
            direction = secondPoint - firstPoint
            length = math.hypot(direction.x(), direction.y())
            if length > 1e-10:
                # Suppress the heavy wall outline within the window span. Its
                # perimeter is drawn afterward using the architectural weight.
                normal = QtCore.QPointF(-direction.y(), direction.x()) / length * (
                    window.width * pixelsPerMillimeter / 2 + self.lineWidths["walls"] + 1)
                outlineHole = QtGui.QPolygonF([firstPoint + normal, secondPoint + normal,
                                               secondPoint - normal, firstPoint - normal])
                # Distant openings cannot mask visible outlines. Including their
                # holes extends Qt's clip raster far beyond the viewport.
                if not self.isPanning or any(outlineHole.boundingRect().intersects(rect) for rect in openingPaintRects):
                    windowOutlineClip.addPolygon(outlineHole)
                    windowOutlineClip.closeSubpath()
                    if bakePassageClips:
                        windowOutlineCuts.append((outlineHole.boundingRect(), outlineHole))
        painter.save()
        if not bakePassageClips:
            painter.setClipPath(windowOutlineClip, QtCore.Qt.ClipOperation.IntersectClip)
        painter.setPen(LinePen(themeColors["wallOutline"], self.lineWidths["walls"]))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        columnOutlines = getattr(self, "columnOutlinePaths", ())
        if columnOutlines:
            for path, occluders in columnOutlines:
                painter.save()
                if not occluders.isEmpty() and path.boundingRect().intersects(occluders.boundingRect()):
                    clip = QtGui.QPainterPath()
                    clip.addRect(drawingRect)
                    painter.setClipPath(Paths.Difference(clip, viewTransform.map(occluders)),
                                        QtCore.Qt.ClipOperation.IntersectClip)
                outlinePath = viewTransform.map(path)
                if bakePassageClips:
                    # SVG viewers differ in their support for inverse clips.
                    # Cut the actual stroke/fill geometry at passage openings.
                    if painter.pen().style() != QtCore.Qt.PenStyle.NoPen:
                        stroke = Paths.PreparePenStroke(painter.pen())
                        outlinePath = stroke(outlinePath).intersected(windowOutlineClip)
                        for cut in openingCuts:
                            outlinePath = outlinePath.subtracted(cut)
                        if not occluders.isEmpty():
                            outlinePath = outlinePath.subtracted(viewTransform.map(occluders))
                        painter.fillPath(outlinePath, painter.pen().brush())
                else:
                    painter.drawPath(outlinePath)
                painter.restore()
        else:
            strokeDrawn = False
            if bakePassageClips:
                if painter.pen().style() != QtCore.Qt.PenStyle.NoPen:
                    stroke = Paths.PreparePenStroke(painter.pen())
                    # The stroker emits overlapping winding contours. Normalize
                    # those before booleans: near-coincident edges can otherwise
                    # turn a room-sized hole into filled ink in SVG previews.
                    outlinePath = self.CutOpeningPolygons(stroke(combinedPath).simplified().toFillPolygons(),
                                                          openingCutPolygons + windowOutlineCuts)
                    painter.fillPath(outlinePath, painter.pen().brush())
                strokeDrawn = True
            if (not strokeDrawn and self.isPanning and captureEngine is None and self.viewportSceneByteLimit > 0
                    and painter.pen().style() == QtCore.Qt.PenStyle.SolidLine):
                # Qt's complete stroke preserves caps/joins. Preparing it in a
                # retained device-pixel phase avoids restroking on integer pans,
                # without introducing another raster/compositing pass.
                pen = painter.pen()
                ratio = painter.device().devicePixelRatioF()
                strokeKey = (self.wallGeometryKey, self.zoom, ratio, pen.widthF(), pen.capStyle(),
                             pen.joinStyle(), pen.miterLimit())
                cachedStroke = prepared.get("wallStroke")
                if cachedStroke is None or cachedStroke[0] != strokeKey:
                    stroke = Paths.PreparePenStroke(pen)
                    bounds = tuple(polygon.boundingRect() for polygon in Paths.Contours(combinedPath))
                    cachedStroke = (strokeKey, stroke(combinedPath), QtCore.QPointF(origin), bounds)
                    prepared["wallStroke"] = cachedStroke
                delta = origin - cachedStroke[2]
                if (abs(delta.x() * ratio - round(delta.x() * ratio)) < 1e-7
                        and abs(delta.y() * ratio - round(delta.y() * ratio)) < 1e-7
                        and any(bounds.translated(delta).contains(drawingRect) for bounds in cachedStroke[3])):
                    # Large spanning contours are costly to restroke. For smaller
                    # contours, native dirty-contour culling avoids filling the
                    # complete scene's stroke and remains the cheaper path.
                    self.DrawPanWallStroke(painter, cachedStroke[1].translated(delta), pen.brush(), dirtyRects,
                                           (doorwayClip, windowOutlineClip), drawingRect)
                    strokeDrawn = True
            if not strokeDrawn and dirtyRects is not None and (self.isPanning or self.viewportEditRaster is not None and self.CanCacheEditScene()):
                self.DrawDirtyWallOutline(painter, combinedPath, dirtyRects, wholeContours = self.isPanning)
            elif not strokeDrawn:
                painter.drawPath(combinedPath)
        painter.save()
        for wallId in invalidWalls:
            invalidPath = viewTransform.map(self.wallMaterialPaths.get(wallId, QtGui.QPainterPath()))
            warning = wallId in invalidArchitecture and self.dragStart is None
            painter.setOpacity(1 if warning else .55)
            painter.fillPath(invalidPath, self.warningMaterialBrushes[invalidWalls[wallId].material] if warning else QtGui.QColor(themeColors["canvas"]))
            painter.setOpacity(1)
            painter.setPen(LinePen(themeColors["warningOutline"] if warning else themeColors["invalidOutline"], self.lineWidths["walls"]))
            painter.drawPath(invalidPath)
        painter.restore()
        painter.restore()
        painter.restore()
        from planner_app.geometry_recovery import ActiveGeometryIssues
        recoveryErrorIds = {id(opening) for opening in self.windows if getattr(opening, "geometryIssues", ()) and ActiveGeometryIssues(opening, self)}
        openingPreviews = self.groupOpeningPreviews or ([self.inactiveOpeningPreview] if isinstance(self.inactiveOpeningPreview, Window) else [])
        previewIds = {id(opening) for opening in openingPreviews} | invalidArchitecture
        for opening in visibleWindows + openingPreviews:
            if not self.IsObjectVisible(opening):
                continue
            positions = openingPositions.get(id(opening))
            firstPoint, secondPoint = (positions if positions is not None else
                                       (self.WorldToViewport(opening.firstVertex), self.WorldToViewport(opening.secondVertex)))
            if dirtyRects is not None or self.isPanning or not getattr(self, "exportRender", False):
                bounds = QtCore.QRectF(firstPoint, secondPoint).normalized()
                # Swing tips extend a full leaf length from a hinge on the wall
                # face, not its centerline. Include that offset when a door
                # re-enters a newly exposed pan strip.
                reach = max(opening.length, opening.depth + abs(opening.depthOffset) if isinstance(opening, Fireplace) else 60)
                padding = (reach + opening.width / 2 + getattr(opening, "sillDepth", 0)
                           + (opening.wellDepth + 150 if opening.windowWell else 0)) * pixelsPerMillimeter + max(self.lineWidths.values()) + 24
                if not any(bounds.adjusted(-padding, -padding, padding, padding).intersects(rect)
                           for rect in (dirtyRects if dirtyRects is not None else (drawingRect,))):
                    continue
            warning = id(opening) in recoveryErrorIds or id(opening) in advisoryIds or id(opening) in invalidArchitecture and self.dragStart is None
            color = (themeColors["warningOutline"] if warning else
                     themeColors["invalidOutline"] if id(opening) in previewIds or id(opening.parentWall) in invalidWalls else
                     self.SelectionColor(opening) if id(opening) in highlightedIds else themeColors["objectOutline"])
            if isinstance(opening, Fireplace):
                transform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(pixelsPerMillimeter, -pixelsPerMillimeter)
                bodyColor = (themeColors["warningOutline"] if warning else
                             themeColors["invalidOutline"] if id(opening) in previewIds or id(opening.parentWall) in invalidWalls else
                             self.SelectionColor(opening) if id(opening) in highlightedIds else themeColors["wallOutline"])
                path = transform.map(FireplacePath(opening))
                if self.wallStyle != "Outline":
                    brush = (QtGui.QBrush(QtGui.QColor(bodyColor)) if self.wallStyle == "Solid" else
                             self.materialBrushes[(opening.material, id(opening) in highlightedIds)])
                    if captureEngine is not None:
                        captureEngine.captureBackground = False
                    painter.fillPath(path, brush)
                    if captureEngine is not None:
                        captureEngine.captureBackground = True
                painter.setPen(LinePen(bodyColor, self.lineWidths["walls"]))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
                continue
            DrawOpeningSymbol(painter, firstPoint, secondPoint,
                              opening.width * pixelsPerMillimeter, type(opening),
                              opening.hingeAtSecond if isinstance(opening, (Door, SwingingDoor, SlidingDoor, PocketDoor, CasementWindow)) else False,
                              opening.swingsOutwards if type(opening) in (Window, Door, DoubleDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, BarnDoor, BifoldDoor) else False, color,
                              opening.panelsFlipped if isinstance(opening, SlidingDoor) else False, pixelsPerMillimeter,
                              opening.sillDepth if isinstance(opening, SilledWindow) else 40.0,
                              lineWidth = self.lineWidths["architectural"], wallLineWidth = self.lineWidths["walls"],
                              wallColor = themeColors["warningOutline"] if warning else
                              themeColors["invalidOutline"] if id(opening) in invalidArchitecture or id(opening.parentWall) in invalidWalls else themeColors["wallOutline"],
                              windowWell = opening.windowWell, wellDepth = opening.wellDepth, wellDashed = opening.wellDashed,
                              # Keep the corrected passage policy; retain frozen containment preparation.
                              drawPassageEdges = self.drawOpeningOutlines if getattr(self, "exportRender", False) or self.exportOverlay.active else True)
        visibleStairs = [wall for wall in self.walls if isinstance(wall, Stair)]
        invalidStairs = []
        movingStairs = ([self.selectedWall] if isinstance(self.selectedWall, Stair) else []) + [
            wall for wall, index, position in self.ActiveAttachments() if isinstance(wall, Stair)]
        if movingStairs and self.dragStart is not None and not self.OpeningsValid():
            invalidStairs = list({id(stair): stair for stair in movingStairs}.values())
        invalidStairs = list({id(stair): stair for stair in invalidStairs + [
            stair for stair in visibleStairs if id(stair) in invalidArchitecture or id(stair) in advisoryIds]}.values())
        if isinstance(self.windowDropPreview, Stair):
            visibleStairs.append(self.windowDropPreview)
        visibleStairs = [stair for stair in visibleStairs if self.IsObjectVisible(stair)]
        if visibleStairs:
            endpointKey = tuple((id(stair), stair.firstVertex.x(), stair.firstVertex.y(), stair.secondVertex.x(), stair.secondVertex.y()) for stair in visibleStairs)
            if endpointKey != getattr(self, "stairEndpointKey", None):
                neighbors = StairEndpointNeighbors(visibleStairs)
                self.stairEndpointKey, self.stairEndpointNeighbors = endpointKey, neighbors
            stairPath = self.ConnectedStairPath(visibleStairs)
            connectedStairIds = {id(stair) for stair in visibleStairs
                                 if self.stairEndpointNeighbors[(id(stair), 0)] or self.stairEndpointNeighbors[(id(stair), 1)]}
            trims = {id(stair): self.StairLandingTrims(stair, self.stairEndpointNeighbors[(id(stair), 0)] + self.stairEndpointNeighbors[(id(stair), 1)])
                     for stair in visibleStairs}
            arrowKey = (self.stairGeometryKey, tuple((id(stair), stair.directionReversed) for stair in visibleStairs))
            if arrowKey != getattr(self, "stairArrowKey", None):
                self.stairArrowRuns = StairArrowRuns(visibleStairs, self.stairEndpointNeighbors, trims)
                self.stairArrowKey = arrowKey
            # Keep wall fills and their full stroke above stairs at shared edges.
            # Cache this independently of stair edits, which do not alter walls.
            wallClipKey = (self.wallGeometryKey, self.zoom, self.lineWidths["walls"], self.lineWidths["architectural"],
                           tuple((id(opening), type(opening), opening.firstVertex.x(), opening.firstVertex.y(),
                                  opening.secondVertex.x(), opening.secondVertex.y(), opening.width,
                                  getattr(opening, "hingeAtSecond", False)) for opening in visibleWindows))
            if wallClipKey != getattr(self, "stairWallClipKey", None):
                # Keep occlusion in scaled coordinates relative to the world origin.
                # Translation only maps this cached geometry; no path booleans are
                # needed merely because the camera or viewport rectangle changed.
                walls = QtGui.QTransform().scale(self.zoom, self.zoom).map(self.wallGeometryPath)
                occlusion = walls
                boundaryWidth = max(self.lineWidths["walls"], self.lineWidths["architectural"])
                if boundaryWidth > 0 and not walls.isEmpty():
                    stroke = Paths.PrepareStroke(width = boundaryWidth, join = 'bevel', cap = 'square')
                    occlusion = Paths.Union(occlusion, stroke(walls))
                # Door openings remove the wall fill and stroke above, so
                # stair outlines remain visible inside those same openings.
                openings = QtGui.QPainterPath()
                openings.setFillRule(QtCore.Qt.FillRule.WindingFill)
                for opening in visibleWindows:
                    first = QtCore.QPointF(opening.firstVertex.x(), -opening.firstVertex.y()) * pixelsPerMillimeter
                    second = QtCore.QPointF(opening.secondVertex.x(), -opening.secondVertex.y()) * pixelsPerMillimeter
                    # A cut exactly tangent to the stroke's outer edge can make
                    # Qt's subtraction fill an enclosed room at certain scales.
                    # Cross that edge fully, keeping the jamb endpoints fixed.
                    for polygon in WallOpeningPolygons(opening, first, second, pixelsPerMillimeter,
                                                        self.lineWidths["walls"], outlineClearance = boundaryWidth / 2):
                        openings.addPolygon(polygon)
                        openings.closeSubpath()
                if not openings.isEmpty():
                    occlusion = Paths.Difference(occlusion, openings)
                self.stairWallClipKey, self.stairWallOcclusion = wallClipKey, occlusion
                self.stairWallClipViewKey = None
            viewKey = (origin.x(), origin.y(), drawingRect)
            if viewKey != self.stairWallClipViewKey:
                clip = QtGui.QPainterPath()
                clip.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
                clip.addRect(drawingRect)
                clip.addPath(QtGui.QTransform().translate(origin.x(), origin.y()).map(self.stairWallOcclusion))
                self.stairWallClip, self.stairWallClipViewKey = clip, viewKey
            painter.save()
            painter.setClipPath(self.stairWallClip, QtCore.Qt.ClipOperation.IntersectClip)
            painter.fillPath(stairPath, QtGui.QColor(themeColors["canvas"]))
            painter.save()
            painter.setClipPath(stairPath, QtCore.Qt.ClipOperation.IntersectClip)
            for stair in visibleStairs:
                if not self.WallPolygon(stair).boundingRect().intersects(drawingRect):
                    continue
                if dirtyRects is not None:
                    bounds = self.WallPolygon(stair).boundingRect()
                    padding = self.lineWidths["architectural"] + 2
                    if not any(bounds.adjusted(-padding, -padding, padding, padding).intersects(rect) for rect in dirtyRects):
                        continue
                if id(stair) in highlightedIds and stair not in invalidStairs:
                    selectedPath = QtGui.QPainterPath()
                    selectedPath.addPolygon(self.WallPolygon(stair))
                    painter.fillPath(selectedPath, QtGui.QColor(themeColors["stairGroupSelectionFill"] if id(stair) in groupedIds else themeColors["stairSelectionFill"]))
                firstTrim, secondTrim = self.StairLandingTrims(stair, self.stairEndpointNeighbors[(id(stair), 0)] + self.stairEndpointNeighbors[(id(stair), 1)])
                treadCount, stepSize, landingCount = stair.StepLayout((firstTrim, secondTrim))
                DrawStairSymbol(painter, self.WorldToViewport(stair.firstVertex), self.WorldToViewport(stair.secondVertex),
                                stair.width * pixelsPerMillimeter, treadCount, stair.directionReversed,
                                self.SelectionColor(stair) if id(stair) in highlightedIds else themeColors["objectOutline"], outline = False,
                                firstTrim = firstTrim * pixelsPerMillimeter, secondTrim = secondTrim * pixelsPerMillimeter, clipRect = drawingRect,
                                lineWidth = self.lineWidths["architectural"], edgeInset = 25 * pixelsPerMillimeter,
                                drawInsetEdges = id(stair) not in connectedStairIds, drawArrow = id(stair) not in connectedStairIds)
                # Keep two joined end steps from becoming one double-depth step.
                for vertexIndex, (vertex, otherVertex) in enumerate(((stair.firstVertex, stair.secondVertex), (stair.secondVertex, stair.firstVertex))):
                    direction = otherVertex - vertex
                    length = math.hypot(direction.x(), direction.y())
                    if length < 1e-10:
                        continue
                    direction /= length
                    for other in self.stairEndpointNeighbors[(id(stair), vertexIndex)]:
                        if other is stair:
                            continue
                        shared = None
                        if QtCore.QLineF(vertex, other.firstVertex).length() <= .01:
                            shared = other.secondVertex - other.firstVertex
                        elif QtCore.QLineF(vertex, other.secondVertex).length() <= .01:
                            shared = other.firstVertex - other.secondVertex
                        if shared is not None and QtCore.QPointF.dotProduct(direction, shared) < 0:
                            cross = direction.x() * shared.y() - direction.y() * shared.x()
                            if abs(cross) < 1e-6:
                                center = self.WorldToViewport(vertex)
                                width = min(stair.width, other.width)
                                normal = QtCore.QPointF(-direction.y(), direction.x()) * ((width / 2 - min(25, width / 4)) * pixelsPerMillimeter)
                                painter.setPen(LinePen(self.SelectionColor(stair) if id(stair) in highlightedIds else themeColors["objectOutline"], self.lineWidths["architectural"]))
                                painter.drawLine(QtCore.QLineF(center - normal, center + normal))
                                break
            insetTransform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
            for stair, line in self.stairInsetLines:
                if stair in invalidStairs:
                    continue
                color = self.SelectionColor(stair) if id(stair) in highlightedIds else themeColors["objectOutline"]
                painter.setPen(LinePen(color, self.lineWidths["architectural"]))
                painter.drawLine(insetTransform.map(line))
            arrows = [(self.WorldToViewport(start), self.WorldToViewport(tip),
                       self.SelectionColor(stair) if id(stair) in highlightedIds else themeColors["objectOutline"], showTip)
                      for stair, start, tip, showTip in self.stairArrowRuns if stair not in invalidStairs and id(stair) in connectedStairIds]
            DrawStairArrows(painter, arrows, self.lineWidths["architectural"])
            painter.restore()
            painter.setPen(LinePen(themeColors["wallOutline"], self.lineWidths["architectural"]))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            origin = self.WorldToViewport(QtCore.QPointF())
            stairTransform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
            # The traced outline consists of independent line spans. Batched
            # lines avoid stroking a large path again on every fractional pan.
            painter.drawLines([stairTransform.map(line) for line in self.stairOutlineLines])
            painter.restore()
            for stair in invalidStairs:
                firstTrim, secondTrim = self.StairLandingTrims(stair, self.stairEndpointNeighbors[(id(stair), 0)] + self.stairEndpointNeighbors[(id(stair), 1)])
                treadCount, stepSize, landingCount = stair.StepLayout((firstTrim, secondTrim))
                DrawStairSymbol(painter, self.WorldToViewport(stair.firstVertex), self.WorldToViewport(stair.secondVertex),
                                stair.width * pixelsPerMillimeter, treadCount, stair.directionReversed,
                                themeColors["warningOutline"] if id(stair) in advisoryIds or id(stair) in invalidArchitecture and self.dragStart is None else themeColors["invalidOutline"],
                                firstTrim = firstTrim * pixelsPerMillimeter, secondTrim = secondTrim * pixelsPerMillimeter, clipRect = drawingRect,
                                lineWidth = self.lineWidths["architectural"], edgeInset = 25 * pixelsPerMillimeter)
        if isinstance(self.inactiveOpeningPreview, Stair):
            stair = self.inactiveOpeningPreview
            DrawStairSymbol(painter, self.WorldToViewport(stair.firstVertex), self.WorldToViewport(stair.secondVertex),
                            stair.width * pixelsPerMillimeter, stair.stepCount, stair.directionReversed, themeColors["invalidOutline"],
                            lineWidth = self.lineWidths["architectural"], edgeInset = 25 * pixelsPerMillimeter)
        visibleRailings = [obj for obj in self.walls if isinstance(obj, Railing) and self.IsObjectVisible(obj)]
        if isinstance(self.arrowPreview, Railing) and self.IsObjectVisible(self.arrowPreview):
            visibleRailings.append(self.arrowPreview)
        paintRailings = False
        if visibleRailings:
            railingPath, _ = self.ConnectedRailingPath(visibleRailings, False)
            padding = self.lineWidths["architectural"] + 2
            bounds = railingPath.boundingRect().adjusted(-padding, -padding, padding, padding)
            # Retain the complete list for handles and measurements, but avoid
            # rasterizing the wall-occlusion mask for railings outside this paint.
            paintRailings = (not self.isPanning or any(bounds.intersects(rect)
                             for rect in (dirtyRects if dirtyRects is not None else [drawingRect])))
        if paintRailings:
            # Railings cover counters and stairs, while solid walls remain above them.
            painter.save()
            railingClip = QtGui.QPainterPath()
            railingClip.addRect(drawingRect)
            painter.setClipPath(Paths.Difference(railingClip, combinedPath), QtCore.Qt.ClipOperation.IntersectClip)
            invalidRailing = isinstance(self.arrowPreview, Railing) and not self.WallFits(self.arrowPreview)
            painter.setPen(LinePen(themeColors["invalidOutline"] if invalidRailing else themeColors["objectOutline"], self.lineWidths["architectural"]))
            painter.setBrush(QtGui.QColor(themeColors["canvas"]))
            painter.drawPath(railingPath)
            origin = self.WorldToViewport(QtCore.QPointF())
            postTransform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
            postOutlines = postTransform.map(self.railingPostOutlinePath)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPath(postOutlines)
            for railing in visibleRailings:
                if id(railing) in highlightedIds or id(railing) in invalidArchitecture or id(railing) in advisoryIds:
                    selectionClip = QtGui.QPainterPath()
                    selectionClip.addPolygon(self.WallPolygon(railing))
                    selectionClip.closeSubpath()
                    stroke = QtGui.QPainterPathStroker()
                    stroke.setWidth(self.lineWidths["architectural"] + 2)
                    selectionClip = selectionClip.united(stroke.createStroke(selectionClip))
                    painter.save()
                    painter.setClipPath(selectionClip, QtCore.Qt.ClipOperation.IntersectClip)
                    color = (themeColors["warningOutline"] if id(railing) in advisoryIds or id(railing) in invalidArchitecture and self.dragStart is None else
                             themeColors["invalidOutline"] if id(railing) in invalidArchitecture else self.SelectionColor(railing))
                    painter.setPen(LinePen(color, self.lineWidths["architectural"]))
                    painter.setBrush(QtGui.QColor(themeColors["canvas"] if id(railing) in invalidArchitecture or id(railing) in advisoryIds else themeColors["stairSelectionFill"]))
                    painter.drawPath(railingPath)
                    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                    painter.drawPath(postOutlines)
                    painter.restore()
            painter.restore()
        # Containment is an advisory warning, independent of drag validity.
        # Draw these footprints above the merged wall surfaces so they remain visible.
        painter.save()
        painter.setClipPath(doorwayClip, QtCore.Qt.ClipOperation.IntersectClip)
        painter.setPen(LinePen(themeColors["warningOutline"], self.lineWidths["architectural"]))
        for wall in containedWalls:
            polygon = self.WallPolygon(wall)
            padding = self.lineWidths["architectural"] + 2
            if dirtyRects is not None and not any(polygon.boundingRect().adjusted(-padding, -padding, padding, padding).intersects(rect) for rect in dirtyRects):
                continue
            painter.setBrush(self.warningMaterialBrushes[wall.material])
            painter.drawPolygon(polygon)
            if wall.material == "Lumber" and len(polygon) == 4:
                painter.drawLine(QtCore.QLineF(polygon[0], polygon[2]))
                painter.drawLine(QtCore.QLineF(polygon[1], polygon[3]))
        painter.restore()
        if captureEngine is not None:
            captureEngine.captureBackground = False
        visibleElevators = [obj for obj in self.walls if isinstance(obj, Elevator) and self.IsObjectVisible(obj)]
        if isinstance(self.arrowPreview, Elevator) and self.IsObjectVisible(self.arrowPreview):
            visibleElevators.append(self.arrowPreview)
        elevatorRenderers = getattr(self, "elevatorRenderers", {})
        self.elevatorRenderers = elevatorRenderers
        if captureEngine is not None:
            captureEngine.captureBackground = True
        for elevator in visibleElevators:
            selected = id(elevator) in highlightedIds
            invalid = id(elevator) in invalidArchitecture or (elevator is self.arrowPreview or selected and (self.isDragging or self.furnishingHandleDrag is not None)) and not self.WallFits(elevator)
            warning = id(elevator) in advisoryIds or id(elevator) in invalidArchitecture and self.dragStart is None
            color = (themeColors["warningOutline"] if warning else themeColors["invalidOutline"] if invalid else
                     self.SelectionColor(elevator) if selected else themeColors["objectOutline"])
            key = (color, themeColors["canvas"], self.lineWidths["architectural"], palette.labelFont)
            if key not in elevatorRenderers:
                if len(elevatorRenderers) >= 8:
                    elevatorRenderers.pop(next(iter(elevatorRenderers)))
                elevatorRenderers[key] = FurnishingRenderer(furnishingsDirectory / "images/elevator.svg",
                    palette = {"outline": color, "background": themeColors["canvas"], "missing": themeColors["missing"]},
                    lineWidth = self.lineWidths["architectural"])
            DrawFurnishing(painter, elevator, self.WorldToViewport(elevator.firstVertex), self.WorldToViewport(elevator.secondVertex),
                           pixelsPerMillimeter, elevatorRenderers[key], selected, invalid and not warning, selectionColor = color, drawBounds = False)
        if captureEngine is not None:
            captureEngine.captureBackground = False
        visibleArrows = [obj for obj in self.walls if isinstance(obj, Arrow) and self.IsObjectVisible(obj)]
        if isinstance(self.arrowPreview, Arrow) and self.IsObjectVisible(self.arrowPreview):
            visibleArrows.append(self.arrowPreview)
        arrowDirections = ConnectedArrowDirections(visibleArrows)
        arrowCorners = ConnectedArrowCorners(visibleArrows, arrowDirections)
        arrowPath = QtGui.QPainterPath()
        arrowPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
        arrowColor = None
        for arrow in visibleArrows:
            first, second, showTip = arrowDirections[id(arrow)]
            tail, head = ArrowPaths(self.WorldToViewport(first), self.WorldToViewport(second), arrow.width,
                                    arrow.solidTip, arrow.tipSize, pixelsPerMillimeter, showTip,
                                    [[self.WorldToViewport(point) for point in polygon] for polygon in arrowCorners[id(arrow)]])
            color = QtGui.QColor(themeColors["invalidOutline"] if arrow is self.arrowPreview else
                                 self.SelectionColor(arrow) if id(arrow) in highlightedIds else themeColors["objectOutline"])
            color.setAlphaF(arrow.intensity)
            # Fill adjoining shapes of the same appearance in one operation.
            # Separate antialiased fills leave a seam at their shared diagonal
            # and apply intensity twice wherever the shafts overlap.
            if arrowColor is not None and color != arrowColor:
                painter.fillPath(arrowPath, arrowColor)
                arrowPath = QtGui.QPainterPath()
                arrowPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
            arrowColor = color
            arrowPath.addPath(tail)
            arrowPath.addPath(head)
        if arrowColor is not None:
            painter.fillPath(arrowPath, arrowColor)
        visibleGuides = [obj for obj in self.walls if isinstance(obj, MeasurementGuide) and self.IsObjectVisible(obj)]
        if isinstance(self.arrowPreview, MeasurementGuide) and self.IsObjectVisible(self.arrowPreview):
            visibleGuides.append(self.arrowPreview)
        visibleBoundaries = [guide for guide in visibleGuides if isinstance(guide, BoundaryLine)]
        if visibleBoundaries:
            painter.save()
            for guide in visibleBoundaries:
                colorRole, widthRole = lineWeightClasses[guide.weightClass] if isinstance(guide, DashedLine) else ("measurementLine", "dimensions")
                color = self.SelectionColor(guide) if id(guide) in highlightedIds else themeColors[colorRole]
                lineWidth = self.lineWidths[widthRole]
                style = QtCore.Qt.PenStyle.SolidLine if isinstance(guide, SolidLine) else QtCore.Qt.PenStyle.DashLine if isinstance(guide, DashedLine) else QtCore.Qt.PenStyle.DashDotLine
                pen = LinePen(color, lineWidth, style)
                if lineWidth > 0:
                    # Qt measures dash lengths in stroke widths. Keep thin
                    # dimension strokes from collapsing the pattern to pixels.
                    unit = max(1, lineWidth) / lineWidth
                    if isinstance(guide, DashedLine) and not isinstance(guide, SolidLine):
                        pen.setDashPattern([6 * unit, 3 * unit])
                    elif not isinstance(guide, SolidLine):
                        pen.setDashPattern([6 * unit, 3 * unit, unit, 3 * unit])
                painter.setPen(pen)
                painter.drawLine(QtCore.QLineF(self.WorldToViewport(guide.firstVertex), self.WorldToViewport(guide.secondVertex)))
            painter.restore()
        sceneState = (highlightedObjects, highlightedIds, selectedVertexKeys, invalidWalls, invalidCounterIds, invalidStairs,
                      visibleWalls, visibleCounters, visibleWindows, visibleStairs, visibleRailings, visibleArrows, visibleGuides)
        if drawAnnotations:
            self.DrawSceneMeasurements(painter, drawingRect, sceneState, dirtyRects, retainCommands = retainAnnotations)
        return sceneState


class ReferenceViewport(ReferenceGeometry, ReferenceRendering, DrawingViewport):
    pass
