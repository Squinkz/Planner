"""Opaque physical-scene retention during unconstrained wall endpoint drags."""
import math
from planner_app.graphics.path_operations import Paths
from PySide6 import QtCore, QtGui
from planner_app.models import Wall, Pillar, Column, Window, Fireplace, Furnishing, Label, NorthArrow
from planner_app.graphics.furnishings import FurnishingArtworkBounds


class EditPaintCacheMixin:
    def DrawPanWallStroke(self, painter, path, brush, dirtyRects, clipPaths, drawingRect):
        """Keep Qt's antialiasing work local without another alpha blend."""
        device = painter.device()
        if not dirtyRects or not isinstance(device, QtGui.QPixmap):
            painter.fillPath(path, brush)
            return
        ratio = device.devicePixelRatioF()
        # Keep Qt's original edge-coverage rules for partially covered physical
        # viewport pixels. Interior strips can use small devices exactly.
        if any(abs(value * ratio - round(value * ratio)) > 1e-7
               for value in (drawingRect.left(), drawingRect.top(), drawingRect.right(), drawingRect.bottom())):
            painter.fillPath(path, brush)
            return
        region = QtGui.QRegion()
        dirtyPath = QtGui.QPainterPath()
        dirtyPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
        for rect in dirtyRects:
            dirtyPath.addRect(rect)
            physical = QtCore.QRectF(rect.x() * ratio, rect.y() * ratio,
                                     rect.width() * ratio, rect.height() * ratio).toAlignedRect()
            region = region.united(QtGui.QRegion(physical))
        region = region.intersected(device.rect())
        patches = [(rect, rect.adjusted(-16, -16, 16, 16).intersected(device.rect())) for rect in region]
        if any(self.rasterCacheBudget.RetainedBytes() + bounds.width() * bounds.height() * 4 > self.viewportRasterByteLimit
               for rect, bounds in patches):
            painter.fillPath(path, brush)
            return
        for rect, bounds in patches:
            # Use guard pixels so the rasterizer does not cut angled edges at
            # the copy boundary. Disjoint write regions prevent double ink.
            patch = device.copy(bounds)
            with QtGui.QPainter(patch) as localPainter:
                localPainter.setRenderHints(painter.renderHints())
                localPainter.translate(-bounds.x() / ratio, -bounds.y() / ratio)
                localPainter.setClipPath(dirtyPath)
                for clip in clipPaths:
                    localPainter.setClipPath(clip, QtCore.Qt.ClipOperation.IntersectClip)
                localPainter.setClipRect(QtCore.QRectF(rect.x() / ratio, rect.y() / ratio,
                                                      rect.width() / ratio, rect.height() / ratio),
                                        QtCore.Qt.ClipOperation.IntersectClip)
                localPainter.setOpacity(painter.opacity())
                localPainter.setCompositionMode(painter.compositionMode())
                localPainter.fillPath(path, brush)
            # The patch already contains the old destination and the completed
            # stroke. Copy it once, without applying the original clip/alpha again.
            painter.save()
            painter.setClipping(False)
            painter.setOpacity(1)
            painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Source)
            painter.drawPixmap(QtCore.QPointF(bounds.x() / ratio, bounds.y() / ratio), patch)
            painter.restore()
            # Release this scratch surface before allocating the next one.
            del localPainter, patch

    def DrawDirtyWallOutline(self, painter, path, dirtyRects, wholeContours = False):
        """Keep complete joins in the dirty area, cutting paths only outside it."""
        if (not dirtyRects or painter.pen().style() != QtCore.Qt.PenStyle.SolidLine
                or any(path.elementAt(index).isCurveTo() for index in range(path.elementCount()))):
            painter.drawPath(path)
            return
        margin = max(1, painter.pen().widthF()) * max(4, painter.pen().miterLimit() * 2) + 3
        # Numeric bounds avoid allocating a QRectF (and temporary QPoints)
        # for every distant edge of a large contour on each partial repaint.
        regions = [(rect.left() - margin, rect.top() - margin,
                    rect.right() + margin, rect.bottom() + margin) for rect in dirtyRects]
        fragments = QtGui.QPainterPath()
        for polygon in Paths.Contours(path):
            count = len(polygon) - 1
            if count <= 0:
                continue
            bounds = polygon.boundingRect()
            if not any(bounds.left() - margin < right and bounds.right() + margin > left
                       and bounds.top() - margin < bottom and bounds.bottom() + margin > top
                       for left, top, right, bottom in regions):
                continue
            if wholeContours:
                fragments.addPolygon(polygon)
                fragments.closeSubpath()
                continue
            coordinates = [(point.x(), point.y()) for point in polygon]
            visible = []
            for index in range(count):
                firstX, firstY = coordinates[index]
                secondX, secondY = coordinates[index + 1]
                left, right = min(firstX, secondX) - margin, max(firstX, secondX) + margin
                top, bottom = min(firstY, secondY) - margin, max(firstY, secondY) + margin
                visible.append(any(left < regionRight and right > regionLeft and top < regionBottom and bottom > regionTop
                                   for regionLeft, regionTop, regionRight, regionBottom in regions))
            if all(visible):
                fragments.addPolygon(polygon)
                fragments.closeSubpath()
                continue
            # Begin after an omitted span so runs crossing the contour's first
            # point remain joined. End caps then lie outside the dirty clip.
            start = visible.index(False)
            drawing = False
            for offset in range(1, count + 1):
                index = (start + offset) % count
                if visible[index]:
                    if not drawing:
                        fragments.moveTo(polygon[index])
                    fragments.lineTo(polygon[index + 1])
                drawing = visible[index]
        painter.drawPath(fragments)

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

    def DrawEditScene(self, painter, drawingRect, rasterRect, origin, pixelsPerMillimeter, backgroundKey):
        if self.viewportBackground is None:
            return None
        values = self.SceneRenderValueKey(backgroundKey)
        changes = self.renderChanges
        frameKey = (values, changes.appearance, changes.topology, self.wallStyle,
                    tuple(self.collisionSettings.items()), self.connectedEnabled,
                    self.connectedVerticesEnabled, self.connectedObjectsEnabled,
                    tuple((id(wall), index) for wall, index, position in self.ActiveAttachments()),
                    tuple((id(opening), tuple(opening.geometryIssues)) for opening in self.windows if getattr(opening, "geometryIssues", ())))
        dirtyRects = []
        if self.viewportEditRaster is None or frameKey != self.viewportEditFrameKey:
            full = (self.viewportEditRaster is None or backgroundKey != self.viewportEditBackgroundKey
                    or self.viewportEditSuppressedGesture is self.interactionBefore and self.interactionBefore is not None)
            snapshot = None
            key = None
            if not full:
                key, snapshot = self.EditSceneSnapshot(drawingRect, origin, pixelsPerMillimeter, values)
                previous = self.viewportEditSnapshot
                full = previous is None or key != self.viewportEditKey
                if not full:
                    for identity in snapshot.keys() | previous.keys():
                        old, new = previous.get(identity), snapshot.get(identity)
                        if old is not None and new is not None and old[0] == new[0]:
                            continue
                        for entry in (old, new):
                            if entry is not None and not entry[1].isEmpty():
                                dirtyRects.append(entry[1])
                    region = QtGui.QRegion()
                    for rect in dirtyRects:
                        region |= QtGui.QRegion(rect.toAlignedRect())
                    area = sum(rect.width() * rect.height() for rect in region)
                    if area > drawingRect.width() * drawingRect.height() * getattr(self, "editDirtyFractionLimit", .45):
                        # Broad changes use whole-frame painting for this gesture,
                        # but identical later frames can still reuse the result.
                        self.viewportEditSuppressedGesture = self.interactionBefore
                        full = True
            ratio = self.devicePixelRatioF()
            if self.viewportEditRaster is None or backgroundKey != self.viewportEditBackgroundKey:
                frameBytes = math.ceil(self.width() * ratio) * math.ceil(self.height() * ratio) * 4
                if not self.rasterCacheBudget.Prepare("edit", frameBytes, preserve = ("background",)):
                    return None
                self.viewportEditRaster = QtGui.QImage(math.ceil(self.width() * ratio), math.ceil(self.height() * ratio),
                                                      QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                self.viewportEditRaster.setDevicePixelRatio(ratio)
            if full:
                dirtyRects = [drawingRect]
            # Seed the local snapshot after painting the first whole frame.
            # Later broad frames skip that preparation entirely.
            if dirtyRects:
                dirtyRegion = QtGui.QRegion()
                for rect in dirtyRects:
                    left, top = math.floor(rect.left() * ratio), math.floor(rect.top() * ratio)
                    right, bottom = math.ceil(rect.right() * ratio), math.ceil(rect.bottom() * ratio)
                    dirtyRegion |= QtGui.QRegion(left, top, right - left, bottom - top)
                with QtGui.QPainter(self.viewportEditRaster) as editPainter:
                    editPainter.setFont(painter.font())
                    if full:
                        editPainter.drawPixmap(0, 0, self.viewportBackground)
                        editPainter.setClipRect(drawingRect)
                    else:
                        # A device-pixel region avoids introducing another
                        # antialiased path mask over existing object clips.
                        editPainter.scale(1 / ratio, 1 / ratio)
                        editPainter.setClipRegion(dirtyRegion)
                        editPainter.resetTransform()
                        editPainter.drawPixmap(0, 0, self.viewportBackground)
                        editPainter.setClipRect(drawingRect, QtCore.Qt.ClipOperation.IntersectClip)
                    editPainter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                    self.viewportEditState = self.DrawScene(editPainter, drawingRect, origin, pixelsPerMillimeter,
                                                           dirtyRects = None if full else dirtyRects, drawAnnotations = False)
            else:
                # An offscreen edit may still change a visible measurement's
                # validity; skip pixels but refresh that part of the scene state.
                from planner_app.models import Counter, Railing, Stair, Elevator
                moving = {id(wall): wall for wall in [self.selectedWall] + [wall for wall, index, position in self.ActiveAttachments()]}
                blockers = self.furnishings + [wall for wall in self.walls if isinstance(wall, (Counter, Railing, Stair, Elevator))]
                state = list(self.viewportEditState)
                state[3] = {identity: wall for identity, wall in moving.items() if not self.WallFits(wall, blockers = blockers)}
                self.viewportEditState = tuple(state)
            if snapshot is None and self.viewportEditSuppressedGesture is not self.interactionBefore:
                key, snapshot = self.EditSceneSnapshot(drawingRect, origin, pixelsPerMillimeter, values)
            self.viewportEditKey, self.viewportEditSnapshot = key, snapshot
            self.viewportEditFrameKey = frameKey
            self.viewportEditBackgroundKey = backgroundKey
        self.viewportEditDirtyRects = dirtyRects
        painter.setClipRect(rasterRect)
        painter.drawImage(0, 0, self.viewportEditRaster)
        painter.setClipRect(drawingRect)
        state = self.viewportEditState
        self.DrawSceneMeasurements(painter, drawingRect, state)
        self.DrawLabels(painter, pixelsPerMillimeter, state[1], drawOutlines = False, drawingRect = drawingRect)
        return state
