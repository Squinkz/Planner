"""Frozen opening placement and edit transforms before extraction."""
import math
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import *
from planner_app.viewport.polygon_clipping import SplitPolygon

class ReferencePlacement:
    def FindWindowPlacement(self, position, length = None, preferredWall = None, openingType = Window, exclude = None, modifiers = None):
        if length is None:
            length = self.openingDefaultSizes[openingType.__name__] * (20 if openingType in (SlidingDoor, PocketDoor, BarnDoor) else 10)
        if modifiers is None:
            modifiers = QtWidgets.QApplication.keyboardModifiers()
        worldPosition = self.ViewportToWorld(position)
        nearest = None
        nearestGuides = []
        nearestDistance = float("inf")
        solidWalls = [wall for wall in self.walls if type(wall) in (Wall, Pillar, Column)]
        footprintKey = (self.basePixelsPerMillimeter, tuple((id(wall), wall.firstVertex.x(), wall.firstVertex.y(),
                        wall.secondVertex.x(), wall.secondVertex.y(), wall.width, wall.firstMiter, wall.secondMiter)
                        for wall in solidWalls))
        if footprintKey != getattr(self, "openingFootprintKey", None):
            from planner_app.viewport.geometry import FootprintGeometry
            workspace = getattr(self, "openingFootprintWorkspace", None)
            if workspace is None:
                workspace = FootprintGeometry(self.basePixelsPerMillimeter)
                self.openingFootprintWorkspace = workspace
            workspace.basePixelsPerMillimeter = self.basePixelsPerMillimeter
            workspace.ConnectedWallPath(solidWalls, traceContours = False)
            transform = QtGui.QTransform().scale(1 / self.basePixelsPerMillimeter, -1 / self.basePixelsPerMillimeter)
            # Include raw rectangles as well as joined geometry, matching the
            # two collision checks used by OpeningFits.
            self.openingFootprints = [(owner, transform.map(polygon)) for owner, polygon in workspace.wallFillPolygons]
            self.openingFootprints.extend((wall, QtGui.QPolygonF(self.ObjectFootprint(wall)[1])) for wall in solidWalls)
            self.openingFootprintKey = footprintKey
        walls = ([preferredWall] + [wall for wall in reversed(self.walls) if wall is not preferredWall]
                 if preferredWall is not None else reversed(self.walls))
        for wall in walls:
            if type(wall) is not Wall or not self.IsObjectVisible(wall):
                continue
            direction = wall.secondVertex - wall.firstVertex
            lengthSquared = QtCore.QPointF.dotProduct(direction, direction)
            if lengthSquared < 1.0:
                continue
            fraction = max(0.0, min(1.0, QtCore.QPointF.dotProduct(worldPosition - wall.firstVertex, direction) / lengthSquared))
            projected = wall.firstVertex + direction * fraction
            distance = QtCore.QLineF(position, self.WorldToViewport(projected)).length()
            reach = wall.width * self.basePixelsPerMillimeter * self.zoom / 2 + 24
            if distance <= reach and distance < nearestDistance:
                parentLength = math.sqrt(lengthSquared)
                gapStart, gapEnd = 0.0, 1.0
                # Every wall-mounted opening fits the free interval under the
                # cursor, including the entire length of a short, empty wall.
                for other in self.windows:
                    if other is exclude or other.parentWall is not wall:
                        continue
                    if other.secondFraction <= fraction + 1e-8:
                        gapStart = max(gapStart, other.secondFraction)
                    elif other.firstFraction >= fraction - 1e-8:
                        gapEnd = min(gapEnd, other.firstFraction)
                    else:
                        gapEnd = gapStart
                        break
                if (gapEnd - gapStart) * parentLength < 1.0:
                    continue
                parentCorners = self.ObjectCorners(wall)
                parentBounds = QtGui.QPolygonF(parentCorners).boundingRect()
                area = sum(parentCorners[index].x() * parentCorners[(index + 1) % 4].y() -
                           parentCorners[(index + 1) % 4].x() * parentCorners[index].y() for index in range(4))
                orientation = 1 if area > 0 else -1
                blocked = []
                for owner, polygon in self.openingFootprints:
                    if owner is wall or not parentBounds.intersects(polygon.boundingRect()):
                        continue
                    points = list(polygon)
                    for index, first in enumerate(parentCorners):
                        points, outside = SplitPolygon(points, first, parentCorners[(index + 1) % 4], orientation)
                        if len(points) < 3:
                            break
                    if len(points) < 3:
                        continue
                    overlapArea = abs(sum(points[index].x() * points[(index + 1) % len(points)].y() -
                                          points[(index + 1) % len(points)].x() * points[index].y()
                                          for index in range(len(points))))
                    if overlapArea < 1e-6:
                        continue
                    bounds = [QtCore.QPointF.dotProduct(point - wall.firstVertex, direction) / lengthSquared for point in points]
                    blocked.append((max(0.0, min(bounds)), min(1.0, max(bounds))))
                for start, end in blocked:
                    if end <= fraction + 1e-8:
                        gapStart = max(gapStart, end)
                    elif start >= fraction - 1e-8:
                        gapEnd = min(gapEnd, start)
                    else:
                        gapEnd = gapStart
                        break
                if (gapEnd - gapStart) * parentLength < 1.0:
                    continue
                span = min(length / parentLength, gapEnd - gapStart)
                minimumCenter = gapStart + span / 2
                maximumCenter = gapEnd - span / 2
                center = max(minimumCenter, min(maximumCenter, fraction))
                midpoint = wall.firstVertex + direction * center
                anchors = (midpoint, midpoint - direction * (span / 2), midpoint + direction * (span / 2))
                # A raw placement is a fallback, not a zero-distance snap target.
                placements = [(3, float("inf"), openingType(wall, center - span / 2, center + span / 2), [])]
                for anchor in (() if openingType is Fireplace else anchors):
                    snapped = self.SnapPosition(anchor, modifiers, wall.firstVertex, direction / parentLength)
                    if not self.snapApplied:
                        continue
                    snappedCenter = center + QtCore.QPointF.dotProduct(snapped - anchor, direction) / lengthSquared
                    if snappedCenter < minimumCenter - 1e-8 or snappedCenter > maximumCenter + 1e-8:
                        continue
                    snappedCenter = max(minimumCenter, min(maximumCenter, snappedCenter))
                    candidate = openingType(wall, snappedCenter - span / 2, snappedCenter + span / 2)
                    correctionDistance = QtCore.QLineF(self.WorldToViewport(anchor), self.WorldToViewport(snapped)).length()
                    placements.append((self.snapPriority, correctionDistance, candidate, self.alignmentGuides))
                for priority, correctionDistance, candidate, guides in sorted(placements, key = lambda placement: placement[:2]):
                    if self.OpeningFits(candidate, exclude):
                        nearest = candidate
                        nearestGuides = guides
                        nearestDistance = distance
                        break
        self.alignmentGuides = nearestGuides
        return nearest

    def FindFireplacePlacement(self, position, modifiers, source = None, initialSize = None):
        worldPosition = self.ViewportToWorld(position)
        width = initialSize[0] if initialSize is not None else source.width if source is not None else self.miscDefaultSizes["Fireplace"] * 10
        fireplace = self.FindWindowPlacement(position, width,
            source.parentWall if source is not None else None, Fireplace, source, modifiers)
        if fireplace is None and source is not None:
            direction, normal = source.Axes()
            across = QtCore.QPointF.dotProduct(worldPosition - source.parentWall.firstVertex, normal)
            reach = source.depth / 2 + abs(source.depthOffset) + 24 / (self.basePixelsPerMillimeter * self.zoom)
            if abs(across) <= reach:
                searchPosition = self.WorldToViewport(worldPosition - normal * across)
                fireplace = self.FindWindowPlacement(searchPosition, width, source.parentWall, Fireplace, source, modifiers)
        if fireplace is None:
            return None
        if type(fireplace.parentWall) is not Wall:
            return None
        if source is not None:
            fireplace.depth = initialSize[1] if initialSize is not None else source.depth
            fireplace.swingsOutwards = source.swingsOutwards
            fireplace.material = source.material
        direction, normal = fireplace.Axes()
        offset = QtCore.QPointF.dotProduct(worldPosition - fireplace.parentWall.firstVertex, normal)
        limit = (fireplace.depth - fireplace.parentWall.width) / 2
        offset = max(-limit, min(limit, offset))
        fireplace.depthOffset = offset
        center = (fireplace.firstVertex + fireplace.secondVertex) / 2 + normal * offset
        originalFraction = fireplace.centerFraction
        placements = [(3, float("inf"), QtCore.QPointF(), [])]
        snapTargets = self.StairSnapTargets(source)
        # Snap the complete footprint, including both front/back faces, rather
        # than the two opening endpoints on the parent wall's centerline.
        for anchor in self.ObjectCorners(fireplace) + [center]:
            snapped = self.SnapPosition(anchor, modifiers, snapTargets = snapTargets)
            if self.snapApplied:
                correction = snapped - anchor
                placements.append((self.snapPriority, QtCore.QLineF(anchor, snapped).length(),
                                   correction, list(self.alignmentGuides)))
        offsetSnap = None
        if self.alignmentSnapEnabled and self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            target = min((-limit, 0.0, limit), key = lambda target: abs(target - offset))
            if abs(target - offset) * self.basePixelsPerMillimeter * self.zoom <= self.vertexSnapRange:
                offsetSnap = target
        wallLength = QtCore.QLineF(fireplace.parentWall.firstVertex, fireplace.parentWall.secondVertex).length()
        halfSpan = fireplace.length / (2 * wallLength)
        self.alignmentGuides = []
        self.snapApplied = False
        for priority, distance, correction, guides in sorted(placements, key = lambda candidate: candidate[:2]):
            fraction = originalFraction + QtCore.QPointF.dotProduct(correction, direction) / wallLength
            depthOffset = offset + QtCore.QPointF.dotProduct(correction, normal)
            # Center/flush depth snapping must not compete with an independent
            # sideways alignment (a zero depth correction would always win).
            applyOffsetSnap = offsetSnap is not None and abs(depthOffset - offset) < 1e-8
            if applyOffsetSnap:
                depthOffset = offsetSnap
            if not halfSpan - 1e-8 <= fraction <= 1 - halfSpan + 1e-8 or abs(depthOffset) > limit + 1e-8:
                continue
            fireplace.centerFraction = max(halfSpan, min(1 - halfSpan, fraction))
            fireplace.depthOffset = depthOffset
            if not self.OpeningFits(fireplace, source):
                continue
            self.alignmentGuides = guides
            self.snapApplied = priority < 3 or applyOffsetSnap
            self.snapPriority = min(priority, 1) if applyOffsetSnap else priority
            break
        else:
            return None
        if source is None:
            fireplace.swingsOutwards = QtCore.QPointF.dotProduct(worldPosition - fireplace.parentWall.firstVertex, normal) > 0
        return fireplace

    def OrientDoor(self, door, position):
        direction = door.secondVertex - door.firstVertex
        length = math.hypot(direction.x(), direction.y())
        if length < 1e-10:
            return
        direction /= length
        offset = self.ViewportToWorld(position) - (door.firstVertex + door.secondVertex) / 2
        along = QtCore.QPointF.dotProduct(offset, direction)
        across = QtCore.QPointF.dotProduct(offset, QtCore.QPointF(-direction.y(), direction.x()))
        # A small axis dead zone avoids flickering when the pointer is on a divider.
        pixelsPerMillimeter = self.basePixelsPerMillimeter * self.zoom
        if isinstance(door, (Door, SlidingDoor, PocketDoor, CasementWindow)) and abs(along) * pixelsPerMillimeter > 2:
            door.hingeAtSecond = along < 0 if isinstance(door, SlidingDoor) else along > 0
        if abs(across) * pixelsPerMillimeter > 2:
            if isinstance(door, SlidingDoor):
                door.panelsFlipped = across < 0
            elif type(door) in (Window, SilledWindow, CasementWindow):
                door.swingsOutwards = across > 0
            elif isinstance(door, (Door, BarnDoor, BifoldDoor)):
                door.swingsOutwards = across < 0

    def InactiveOpening(self, center, openingType, source = None, initialSize = None):
        length = (source.length if source is not None else self.miscDefaultSizes["Fireplace"] * 10 if openingType is Fireplace else
                  self.openingDefaultSizes[openingType.__name__] * (20 if openingType in (SlidingDoor, PocketDoor, BarnDoor) else 10))
        width = source.width if source is not None else self.newWallWidth
        if openingType is Fireplace:
            # Fireplace.width is its span, not its supporting wall's thickness.
            # A synthetic wall that thick forces the preview depth up to the span.
            width = source.parentWall.width if source is not None else self.newWallWidth
            if initialSize is not None:
                length = initialSize[0]
                width = min(width, initialSize[1])
        direction = (source.parentWall.secondVertex - source.parentWall.firstVertex) if source is not None else QtCore.QPointF(1, 0)
        direction /= math.hypot(direction.x(), direction.y())
        parent = Wall(center - direction * (length / 2), center + direction * (length / 2), width)
        preview = openingType(parent, 0.0, 1.0)
        if isinstance(preview, (Door, SlidingDoor, PocketDoor, CasementWindow)) and source is not None:
            preview.hingeAtSecond = source.hingeAtSecond
        if type(preview) in (Window, Door, SilledWindow, CasementWindow, BarnDoor, BifoldDoor) and source is not None:
            preview.swingsOutwards = source.swingsOutwards
        elif isinstance(preview, SlidingDoor) and source is not None:
            preview.panelsFlipped = source.panelsFlipped
        if isinstance(preview, SilledWindow) and source is not None:
            preview.sillDepth = source.sillDepth
        if isinstance(preview, Fireplace) and source is not None:
            preview.depth = initialSize[1] if initialSize is not None else source.depth
            preview.material = source.material
            preview.swingsOutwards = source.swingsOutwards
        return preview


class ReferenceScene:
    def MoveSpecial(self, x, y, angle, localOrigins = False):
        objects = list({id(obj): obj for obj, index in self.SelectionEntries()}.values())
        if not objects:
            return "Select an object to move."
        if not all(math.isfinite(value) for value in (x, y, angle)):
            return "Enter finite movement and angle values."
        if x == 0 and y == 0 and angle % 360 == 0:
            return None
        self.CancelInteraction()
        before = self.CaptureState()
        bounds = self.ObjectFootprint(objects[0])[0]
        for obj in objects[1:]:
            bounds = bounds.united(self.ObjectFootprint(obj)[0])
        sharedOrigin = QtCore.QPointF(self.rotationPivot) if self.rotationPivot is not None else bounds.center()
        delta = QtCore.QPointF(x, y)
        radians = math.radians(angle % 360)
        cosine, sine = math.cos(radians), math.sin(radians)
        vertices = {}
        openingTargets = []
        for obj in objects:
            origin = (obj.firstVertex + obj.secondVertex) / 2 if localOrigins else sharedOrigin
            if isinstance(obj, Window):
                center = (obj.firstVertex + obj.secondVertex) / 2
                offset = center - origin
                direction = obj.secondVertex - obj.firstVertex
                openingTargets.append((obj, origin + QtCore.QPointF(offset.x() * cosine - offset.y() * sine,
                    offset.x() * sine + offset.y() * cosine) + delta,
                    QtCore.QPointF(direction.x() * cosine - direction.y() * sine,
                                  direction.x() * sine + direction.y() * cosine)))
            else:
                for index, vertex in enumerate((obj.firstVertex, obj.secondVertex)):
                    vertices[(id(obj), index)] = (obj, index, QtCore.QPointF(vertex), origin)
        originalIndex = self.selectedVertex
        if self.connectedEnabled:
            for obj in objects:
                if isinstance(obj, (Window, Label)) or isinstance(obj, Furnishing) and type(obj) is not Furnishing:
                    continue
                origin = (obj.firstVertex + obj.secondVertex) / 2 if localOrigins else sharedOrigin
                indices = (None,) if self.connectedObjectsEnabled or self.connectedVerticesEnabled else ()
                for index in indices:
                    self.selectedVertex = index
                    for attached, vertexIndex, vertex in self.AttachedVertices(obj):
                        vertices.setdefault((id(attached), vertexIndex), (attached, vertexIndex, vertex, origin))
        self.selectedVertex = originalIndex
        self.dragConstraints = []
        for obj, index, vertex, origin in vertices.values():
            offset = vertex - origin
            target = origin + QtCore.QPointF(offset.x() * cosine - offset.y() * sine,
                                            offset.x() * sine + offset.y() * cosine) + delta
            if index == 0:
                obj.firstVertex = target
            else:
                obj.secondVertex = target
        # Stretching a connected neighbor must carry its openings by the same
        # anchor/fraction rules as a canvas drag before validating collisions.
        if not self.FitWallOpenings(before, validateFurnishings = False, validateScene = False):
            self.RestoreState(before)
            return "This move would overlap an object or obstruct an opening."
        for opening, target, targetDirection in openingTargets:
            parent = opening.parentWall
            direction = parent.secondVertex - parent.firstVertex
            lengthSquared = QtCore.QPointF.dotProduct(direction, direction)
            offset = target - parent.firstVertex
            length = math.sqrt(lengthSquared)
            if (length < 1 or abs(offset.x() * direction.y() - offset.y() * direction.x()) > .01 * length
                    or abs(targetDirection.x() * direction.y() - targetDirection.y() * direction.x()) > .01 * length):
                self.RestoreState(before)
                return "Doors and windows must stay on their wall. Select the wall to move or rotate them together."
            opening.centerFraction = QtCore.QPointF.dotProduct(offset, direction) / lengthSquared
            if QtCore.QPointF.dotProduct(targetDirection, direction) < 0:
                for name in ("hingeAtSecond", "swingsOutwards", "panelsFlipped"):
                    if hasattr(opening, name):
                        setattr(opening, name, not getattr(opening, name))
        if not self.OpeningsValid(before = before):
            self.RestoreState(before)
            return "This move would overlap an object or obstruct an opening."
        for obj, index, vertex, origin in vertices.values():
            self.PropagateMiter(obj, index)
        self.RecordEdit(before)
        self.selectionChanged.emit()
        self.update()
        return None

    def SubdivideWalls(self, objects):
        self.CancelInteraction()
        walls = [wall for wall in self.walls if type(wall) is Wall and any(wall is obj for obj in objects)]
        if not walls:
            return False
        splitFractions = {}
        for wall in walls:
            length = QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
            if length < 2e-8:
                return False
            intervals = sorted((opening.firstFraction, opening.secondFraction) for opening in self.windows
                               if opening.parentWall is wall)
            direction = wall.secondVertex - wall.firstVertex
            for other in self.walls + self.furnishings:
                if other is wall:
                    continue
                bounds, corners, axes = self.ObjectFootprint(other)
                if not corners:
                    continue
                start, end = 0.0, 1.0
                # Clip the wall centerline against each rectangular footprint.
                # Boundary contact is a valid split; only its interior is occupied.
                for axis in axes:
                    projections = [QtCore.QPointF.dotProduct(corner, axis) for corner in corners]
                    low, high = min(projections), max(projections)
                    origin = QtCore.QPointF.dotProduct(wall.firstVertex, axis)
                    travel = QtCore.QPointF.dotProduct(direction, axis)
                    if abs(travel) < 1e-8:
                        if origin <= low + 1e-8 or origin >= high - 1e-8:
                            end = start
                            break
                    else:
                        first, second = (low - origin) / travel, (high - origin) / travel
                        start, end = max(start, min(first, second)), min(end, max(first, second))
                    if end <= start:
                        break
                if end - start > 1e-8:
                    intervals.append((start, end))
            intervals.sort()
            candidates = []
            cursor = 0.0
            for start, end in intervals + [(1.0, 1.0)]:
                if start - cursor > 1e-8:
                    fraction = max(cursor, min(start, .5))
                    if 1e-8 < fraction < 1 - 1e-8:
                        candidates.append(fraction)
                cursor = max(cursor, end)
            if not candidates:
                self.clipboardMessage.emit("Cannot subdivide: no clear wall segment is available.")
                return False
            splitFractions[id(wall)] = min(candidates, key = lambda fraction: (abs(fraction - .5), fraction))
        before = self.CaptureState()
        replacements = {}
        for wall in walls:
            midpoint = wall.firstVertex + (wall.secondVertex - wall.firstVertex) * splitFractions[id(wall)]
            first = Wall(QtCore.QPointF(wall.firstVertex), QtCore.QPointF(midpoint), wall.width,
                         wall.firstMiter, 1.0, wall.material)
            second = Wall(QtCore.QPointF(midpoint), QtCore.QPointF(wall.secondVertex), wall.width,
                          1.0, wall.secondMiter, wall.material)
            replacements[id(wall)] = (first, second)
        for opening in self.windows:
            halves = replacements.get(id(opening.parentWall))
            if halves is not None:
                fraction = splitFractions[id(opening.parentWall)]
                secondHalf = opening.centerFraction > fraction
                opening.parentWall = halves[int(secondHalf)]
                opening.centerFraction = ((opening.centerFraction - fraction) / (1 - fraction) if secondHalf
                                          else opening.centerFraction / fraction)
        self.walls = [part for wall in self.walls for part in replacements.get(id(wall), (wall,))]
        self.objectGroups = [tuple(part for obj in group for part in replacements.get(id(obj), (obj,)))
                             for group in self.objectGroups]
        self.hiddenObjects = [part for obj in self.hiddenObjects for part in replacements.get(id(obj), (obj,))]
        self.hiddenObjectIds = {id(obj) for obj in self.hiddenObjects}
        self.SetSelection([(part, None) for wall in walls for part in replacements[id(wall)]])
        self.RecordEdit(before)
        self.selectionChanged.emit()
        self.update()
        return True

    def DissolveWalls(self, vertex):
        self.CancelInteraction()
        walls = [wall for wall in self.walls if type(wall) is Wall and any(
            QtCore.QLineF(vertex, endpoint).length() <= .01 for endpoint in (wall.firstVertex, wall.secondVertex))]
        if len(walls) != 2:
            return False
        self.EnsureObjectIds()
        source, other = sorted(walls, key = lambda wall: wall.objectId)
        sourceFirstShared = QtCore.QLineF(vertex, source.firstVertex).length() <= .01
        otherFirstShared = QtCore.QLineF(vertex, other.firstVertex).length() <= .01
        otherOuter = other.secondVertex if otherFirstShared else other.firstVertex
        otherMiter = other.secondMiter if otherFirstShared else other.firstMiter
        first = otherOuter if sourceFirstShared else source.firstVertex
        second = source.secondVertex if sourceFirstShared else otherOuter
        direction = second - first
        length = math.hypot(direction.x(), direction.y())
        if length < 1e-8:
            self.clipboardMessage.emit("Cannot dissolve: the new wall would have zero length.")
            return False
        merged = Wall(QtCore.QPointF(first), QtCore.QPointF(second), source.width,
                      otherMiter if sourceFirstShared else source.firstMiter,
                      source.secondMiter if sourceFirstShared else otherMiter, source.material)
        wallIds = {id(wall) for wall in walls}
        openings = []
        for opening in self.windows:
            if id(opening.parentWall) not in wallIds:
                continue
            center = (opening.firstVertex + opening.secondVertex) / 2
            clone = self.CloneOpening(opening, merged)
            clone.centerFraction = QtCore.QPointF.dotProduct(center - first, direction) / (length * length)
            halfSpan = clone.length / (2 * length)
            if not halfSpan <= clone.centerFraction <= 1 - halfSpan:
                self.clipboardMessage.emit("Cannot dissolve: an opening would not fit the new wall.")
                return False
            oldDirection = opening.parentWall.secondVertex - opening.parentWall.firstVertex
            if QtCore.QPointF.dotProduct(oldDirection, direction) < 0:
                for flag in ("hingeAtSecond", "swingsOutwards", "panelsFlipped"):
                    if hasattr(clone, flag):
                        setattr(clone, flag, not getattr(clone, flag))
            openings.append((opening, clone))
        candidates = [clone for opening, clone in openings] + [opening for opening in self.windows if id(opening.parentWall) not in wallIds]
        if (any(self.OpeningsOverlap(firstOpening, secondOpening) for index, firstOpening in enumerate(candidates)
                for secondOpening in candidates[index + 1:]) or
                any(self.JoinedObjectsOverlap(merged, obj, contactTolerance = 1.0, excludedWalls = wallIds) for obj in
                    self.furnishings + [wall for wall in self.walls if isinstance(wall, (Stair, Counter))])):
            self.clipboardMessage.emit("Cannot dissolve: objects would overlap on the new wall.")
            return False
        before = self.CaptureState()
        for opening, clone in openings:
            opening.parentWall, opening.centerFraction = merged, clone.centerFraction
            for flag in ("hingeAtSecond", "swingsOutwards", "panelsFlipped"):
                if hasattr(clone, flag):
                    setattr(opening, flag, getattr(clone, flag))
        replacementIndex = min(index for index, wall in enumerate(self.walls) if id(wall) in wallIds)
        self.walls = [wall for wall in self.walls if id(wall) not in wallIds]
        self.walls.insert(replacementIndex, merged)
        self.objectGroups = [tuple(obj for obj in group if id(obj) not in wallIds) +
                             ((merged,) if any(obj is source for obj in group) else ()) for group in self.objectGroups]
        hidden = all(any(obj is wall for obj in self.hiddenObjects) for wall in walls)
        self.hiddenObjects = [obj for obj in self.hiddenObjects if id(obj) not in wallIds] + ([merged] if hidden else [])
        self.hiddenObjectIds = {id(obj) for obj in self.hiddenObjects}
        self.SetSelection([(merged, None)])
        self.RecordEdit(before)
        self.selectionChanged.emit()
        self.update()
        return True


class ReferenceHandles:
    def UpdateFurnishingHandleDrag(self, position, modifiers):
        state = self.furnishingHandleDrag
        furnishing = state["object"]
        if (position - self.dragStart).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
            self.isDragging = True
        if not self.isDragging:
            return
        mode, field, sign, handlePosition, outward = state["handle"]
        if mode == "rotate":
            duplicate = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)
            if duplicate != bool(state["copies"]):
                copyIds = {id(obj) for obj in state["copies"]}
                self.furnishings = [obj for obj in self.furnishings if id(obj) not in copyIds]
                self.labels = [obj for obj in self.labels if id(obj) not in copyIds]
                self.walls = [obj for obj in self.walls if id(obj) not in copyIds]
                self.objectGroups = list(self.interactionBefore[6])
                state["copies"] = []
                for obj, first, second, width, angle in state["sourceStates"]:
                    obj.firstVertex, obj.secondVertex, obj.width = QtCore.QPointF(first), QtCore.QPointF(second), width
                if duplicate:
                    copies = {}
                    for obj, first, second, width, angle in state["sourceStates"]:
                        if isinstance(obj, Pillar):
                            copy = type(obj)(QtCore.QPointF(first), QtCore.QPointF(second), width,
                                             obj.firstMiter, obj.secondMiter, obj.material)
                            copy.measurementHidden = obj.measurementHidden
                            self.walls.append(copy)
                        else:
                            copy = obj.Clone()
                            (self.labels if isinstance(obj, Label) else self.furnishings).append(copy)
                        copies[id(obj)] = copy
                        state["copies"].append(copy)
                    for group in self.interactionBefore[6]:
                        copiedGroup = tuple(copies[id(obj)] for obj in group if id(obj) in copies)
                        if len(copiedGroup) >= 2:
                            self.objectGroups.append(copiedGroup)
                    state["object"] = state["sourceObject"] if state["members"] else state["copies"][0]
                    if state["members"]:
                        state["members"] = [(copies[id(obj)], first, second, width, angle)
                                            for obj, first, second, width, angle in state["sourceStates"]]
                        state["object"].selectionMembers = tuple(state["copies"])
                    self.SetSelection([(obj, None) for obj in state["copies"]])
                    self.furnishingRotationObject = state["copies"][-1]
                else:
                    state["object"] = state["sourceObject"]
                    if state["members"]:
                        state["members"] = list(state["sourceStates"])
                        state["object"].selectionMembers = tuple(entry[0] for entry in state["sourceStates"])
                    self.SetSelection(state["sourceEntries"])
                    self.furnishingRotationObject = state["sourceRotationObject"]
                # Selection normally clears a temporary pivot; this selection is
                # the same gesture transferred to its duplicate.
                self.rotationPivot = QtCore.QPointF(state["pivot"])
            furnishing = state["object"]
        state["centeredResize"] = mode == "resize" and bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)
        if mode == "pivot":
            delta = self.ViewportToWorld(position) - self.ViewportToWorld(self.dragStart)
            self.rotationPivot = state["pivot"] + self.SnapObjectMovement(
                [state["pivot"]], delta, modifiers,
                snapTargets = list(self.SnapVertices()) + self.StairSnapTargets())
            if self.axisConstraintOrigin is not None:
                self.axisConstraintOrigin = state["pivot"]
            self.update()
            return
        north = state["north"]
        center = QtCore.QPointF(state["center"])
        furnishing.width = state["width"]
        furnishing.firstVertex = center - north * (state["length"] / 2)
        furnishing.secondVertex = center + north * (state["length"] / 2)
        if mode == "rotate":
            offset = self.ViewportToWorld(position) - state["pivot"]
            if math.hypot(offset.x(), offset.y()) > 1e-8:
                angle = state["angle"] + math.degrees(math.atan2(offset.y(), offset.x())) - state["mouseAngle"]
                if self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
                    angle = round(angle / 15) * 15
                furnishing.angle = angle
                rotation = math.radians(angle - state["angle"])
                offset = state["center"] - state["pivot"]
                targetCenter = state["pivot"] + QtCore.QPointF(
                    offset.x() * math.cos(rotation) - offset.y() * math.sin(rotation),
                    offset.x() * math.sin(rotation) + offset.y() * math.cos(rotation))
                furnishing.firstVertex += targetCenter - center
                furnishing.secondVertex += targetCenter - center
        else:
            east = QtCore.QPointF(north.y(), -north.x())
            delta = self.ViewportToWorld(position) - self.ViewportToWorld(self.dragStart)
            factor = 2 if state["centeredResize"] else 1
            if field == "corner":
                eastSign, northSign = sign
                diagonal = east * (eastSign * state["width"]) + north * (northSign * state["length"])
                scale = 1 + factor * QtCore.QPointF.dotProduct(delta, diagonal) / QtCore.QPointF.dotProduct(diagonal, diagonal)
                minimumSize = .001 if isinstance(furnishing, Label) else 1
                scale = max(minimumSize / min(state["width"], state["length"]), scale)
                width = state["width"] * scale
                length = state["length"] * scale
                width, length = self.SnapFurnishingResize(state, width, length, modifiers)
                if not state["centeredResize"]:
                    center += east * (eastSign * (width - state["width"]) / 2)
                    center += north * (northSign * (length - state["length"]) / 2)
            else:
                axis = north if field == "length" else east
                size = max(1.0, state[field] + factor * sign * QtCore.QPointF.dotProduct(delta, axis))
                length = size if field == "length" else state["length"]
                width = size if field == "width" else state["width"]
                width, length = self.SnapFurnishingResize(state, width, length, modifiers)
                size = length if field == "length" else width
                if not state["centeredResize"]:
                    center = state["center"] + axis * (sign * (size - state[field]) / 2)
            furnishing.width = width
            furnishing.firstVertex = center - north * (length / 2)
            furnishing.secondVertex = center + north * (length / 2)
        if state["members"]:
            self.TransformFurnishingSelection(state)
        if state.get("fireplace") is not None:
            fireplace = state["fireplace"]
            parentLength = QtCore.QLineF(fireplace.parentWall.firstVertex, fireplace.parentWall.secondVertex).length()
            maxWidth, minDepth = parentLength, fireplace.parentWall.width
            if state.get("centeredResize", False):
                direction, normal = fireplace.Axes()
                offset = state["center"] - fireplace.parentWall.firstVertex
                along = QtCore.QPointF.dotProduct(offset, direction)
                maxWidth = 2 * min(along, parentLength - along)
                minDepth += 2 * abs(QtCore.QPointF.dotProduct(offset, normal))
            fireplace.width = min(furnishing.width, maxWidth)
            fireplace.depth = max(furnishing.length, minDepth)
            fireplace.SetCenter((furnishing.firstVertex + furnishing.secondVertex) / 2)
        self.selectionChanged.emit()
        self.update()

    def TransformFurnishingSelection(self, state):
        box = state["object"]
        center = (box.firstVertex + box.secondVertex) / 2
        rotation = math.radians(box.angle - state["angle"])
        cosine, sine = math.cos(rotation), math.sin(rotation)
        scaleX, scaleY = box.width / state["width"], box.length / state["length"]
        mode, field = state["handle"][:2]
        if mode == "resize" and field in ("width", "length"):
            axis = 0 if field == "width" else 1
            desiredSpan = box.width if axis == 0 else box.length
            span = self.FurnishingSelectionSpan(state, scaleX, scaleY, axis)
            if abs(span - desiredSpan) > 1e-6:
                # Rotated members remain rectangles, so fit the actual group edge
                # to the requested size rather than merely scaling its centers.
                low, high = 0.0, max(1.0, scaleX if axis == 0 else scaleY)
                while self.FurnishingSelectionSpan(state, high if axis == 0 else scaleX,
                                                   high if axis == 1 else scaleY, axis) < desiredSpan:
                    high *= 2
                for iteration in range(40):
                    scale = (low + high) / 2
                    span = self.FurnishingSelectionSpan(state, scale if axis == 0 else scaleX,
                                                       scale if axis == 1 else scaleY, axis)
                    if span < desiredSpan:
                        low = scale
                    else:
                        high = scale
                if axis == 0:
                    scaleX = (low + high) / 2
                else:
                    scaleY = (low + high) / 2
        for obj, first, second, width, angle in state["members"]:
            originalCenter = (first + second) / 2
            offset = originalCenter - state["center"]
            offset = QtCore.QPointF(offset.x() * scaleX, offset.y() * scaleY)
            targetCenter = center + QtCore.QPointF(offset.x() * cosine - offset.y() * sine,
                                                 offset.x() * sine + offset.y() * cosine)
            length = QtCore.QLineF(first, second).length()
            originalNorth = (second - first) / length
            originalEast = QtCore.QPointF(originalNorth.y(), -originalNorth.x())
            # Furnishings remain rectangles when a group is stretched in one axis.
            obj.width = width * math.hypot(originalEast.x() * scaleX, originalEast.y() * scaleY)
            length *= math.hypot(originalNorth.x() * scaleX, originalNorth.y() * scaleY)
            obj.firstVertex = targetCenter - originalNorth * (length / 2)
            obj.secondVertex = targetCenter + originalNorth * (length / 2)
            obj.angle = angle + math.degrees(rotation)
        if state["handle"][0] == "resize":
            bounds = QtCore.QRectF(self.ObjectFootprint(state["members"][0][0])[0])
            for obj, first, second, width, angle in state["members"][1:]:
                bounds = bounds.united(self.ObjectFootprint(obj)[0])
            field, sign = state["handle"][1:3]
            correction = center - bounds.center()
            if field == "width" and not state.get("centeredResize", False):
                anchoredX = state["center"].x() - sign * state["width"] / 2
                correction.setX(anchoredX - (bounds.center().x() - sign * bounds.width() / 2))
            elif field == "length" and not state.get("centeredResize", False):
                anchoredY = state["center"].y() - sign * state["length"] / 2
                correction.setY(anchoredY - (bounds.center().y() - sign * bounds.height() / 2))
            for obj, first, second, width, angle in state["members"]:
                obj.firstVertex += correction
                obj.secondVertex += correction

    def FurnishingSelectionSpan(self, state, scaleX, scaleY, axis):
        minimum, maximum = float("inf"), -float("inf")
        for obj, first, second, width, angle in state["members"]:
            length = QtCore.QLineF(first, second).length()
            north = (second - first) / length
            east = QtCore.QPointF(north.y(), -north.x())
            scaledWidth = width * math.hypot(east.x() * scaleX, east.y() * scaleY)
            scaledLength = length * math.hypot(north.x() * scaleX, north.y() * scaleY)
            offset = (first + second) / 2 - state["center"]
            center = offset.x() * scaleX if axis == 0 else offset.y() * scaleY
            halfSpan = (abs(east.x()) * scaledWidth + abs(north.x()) * scaledLength) / 2 if axis == 0 else (
                abs(east.y()) * scaledWidth + abs(north.y()) * scaledLength) / 2
            minimum = min(minimum, center - halfSpan)
            maximum = max(maximum, center + halfSpan)
        return maximum - minimum


class ReferenceWindow:
    def SetVertex(self, vertexIndex, position):
        direction = self.parentWall.secondVertex - self.parentWall.firstVertex
        lengthSquared = QtCore.QPointF.dotProduct(direction, direction)
        if lengthSquared < 1e-10:
            return
        fraction = QtCore.QPointF.dotProduct(position - self.parentWall.firstVertex, direction) / lengthSquared
        minimumSpan = min(1.0, 1.0 / math.sqrt(lengthSquared))
        if vertexIndex == 0:
            self.firstFraction = max(0.0, min(self.secondFraction - minimumSpan, fraction))
        else:
            self.secondFraction = min(1.0, max(self.firstFraction + minimumSpan, fraction))


class ReferenceFireplace:
    def SetCenter(self, position):
        direction, normal = self.Axes()
        wallLength = QtCore.QLineF(self.parentWall.firstVertex, self.parentWall.secondVertex).length()
        halfSpan = self.width / (2 * max(wallLength, 1e-8))
        self.centerFraction = max(halfSpan, min(1 - halfSpan,
            QtCore.QPointF.dotProduct(position - self.parentWall.firstVertex, direction) / max(wallLength, 1e-8)))
        self.depthOffset = QtCore.QPointF.dotProduct(position - self.parentWall.firstVertex, normal)


class ReferenceFurnishing:
    def SetAngle(self, value):
        center = (self.firstVertex + self.secondVertex) / 2
        radians = math.radians(value % 360)
        halfAxis = QtCore.QPointF(-math.sin(radians), math.cos(radians)) * (self.length / 2)
        self.firstVertex = center - halfAxis
        self.secondVertex = center + halfAxis
