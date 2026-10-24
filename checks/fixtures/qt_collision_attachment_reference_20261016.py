"""Frozen collision and attachment behavior before numeric extraction."""
import math
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import *
from planner_app.preferences import collisionDefaults
from planner_app.viewport.geometry import FootprintGeometry

class ReferenceGeometry:
    def CollisionEnabled(self, first, second):
        if isinstance(first, NorthArrow) or isinstance(second, NorthArrow):
            return False
        if isinstance(first, Window) or isinstance(second, Window):
            return True
        settings = getattr(self, "collisionSettings", collisionDefaults)
        if isinstance(first, Furnishing) or isinstance(second, Furnishing):
            if not settings["furnishings"]:
                return False
        if type(first) in (Wall, Pillar, Column) or type(second) in (Wall, Pillar, Column):
            return settings["walls"]
        return settings["architectural"]

    def ObjectsOverlap(self, first, second, contactTolerance = .01):
        if not self.CollisionEnabled(first, second):
            return False
        if isinstance(first, (Label, Arrow, MeasurementGuide)) or isinstance(second, (Label, Arrow, MeasurementGuide)):
            return False
        if (isinstance(first, Railing) and isinstance(second, (Wall, Window)) and not isinstance(second, Elevator)
                or isinstance(second, Railing) and isinstance(first, (Wall, Window)) and not isinstance(first, Elevator)):
            return False
        # A separating-axis test checks the actual oriented footprints; mere
        # edge contact is allowed, and rotated rectangles do not falsely collide.
        firstBounds, firstCorners, firstAxes = self.ObjectFootprint(first)
        secondBounds, secondCorners, secondAxes = self.ObjectFootprint(second)
        if not firstBounds.intersects(secondBounds) or not firstCorners or not secondCorners:
            return False
        polygons = (firstCorners, secondCorners)
        for axis in firstAxes + secondAxes:
            projections = [[QtCore.QPointF.dotProduct(vertex, axis) for vertex in polygon] for polygon in polygons]
            if min(max(projections[0]), max(projections[1])) - max(min(projections[0]), min(projections[1])) <= contactTolerance:
                return False
        return True

    def JoinedObjectsOverlap(self, first, second, contactTolerance = 1.0, excludedWalls = ()):
        if not self.CollisionEnabled(first, second):
            return False
        if isinstance(first, (Label, Arrow, MeasurementGuide)) or isinstance(second, (Label, Arrow, MeasurementGuide)):
            return False
        if (isinstance(first, Railing) and isinstance(second, (Wall, Window)) and not isinstance(second, Elevator)
                or isinstance(second, Railing) and isinstance(first, (Wall, Window)) and not isinstance(first, Elevator)):
            return False
        batch = getattr(self, "collisionPassCache", None)
        if batch is not None:
            # Candidate objects are temporary. Retain them for this pass so
            # Python cannot reuse their ids for another snap candidate.
            batch.setdefault("references", {}).update(((id(first), first), (id(second), second)))
        if batch is not None and "results" not in batch:
            diagnostics = getattr(self, "renderDiagnostics", None)
            diagnostics = diagnostics if diagnostics is not None and diagnostics.enabled else None
            started = perf_counter() if diagnostics is not None else None
            # Cached painting, hit testing and footprint-only work need no
            # collider scan. Prepare the defensive value key at the first pair
            # query, preserving direct edits and rigid-translation reuse.
            objects = self.walls + self.windows + self.furnishings
            geometryKey = tuple((id(obj), obj.firstVertex.x(), obj.firstVertex.y(),
                                 obj.secondVertex.x(), obj.secondVertex.y(), obj.width,
                                 getattr(obj, "firstMiter", None), getattr(obj, "secondMiter", None),
                                 (obj.depth, obj.depthOffset) if isinstance(obj, Fireplace) else None) for obj in objects)
            oldKey = getattr(self, "collisionResultKey", None)
            unchanged = oldKey is not None and self.WallTranslation(oldKey, geometryKey) is not None
            if not hasattr(self, "collisionPairKeys"):
                self.collisionPairKeys = {}
                self.collisionPairEpochs = {}
                self.collisionEpoch = 0
                self.collisionResults = {}
            if not unchanged:
                self.collisionEpoch += 1
            sceneIds = {id(obj) for obj in objects}
            if oldKey is not None and {entry[0] for entry in oldKey} != sceneIds:
                self.collisionResults = {key: value for key, value in self.collisionResults.items()
                                         if key[0] in sceneIds and key[1] in sceneIds and not key[3]}
                self.collisionPairKeys = {key: value for key, value in self.collisionPairKeys.items()
                                          if key in self.collisionResults}
                self.collisionPairEpochs = {key: value for key, value in self.collisionPairEpochs.items()
                                            if key in self.collisionResults}
            self.collisionResultKey = geometryKey
            batch.update(results = self.collisionResults, sceneIds = sceneIds, epoch = self.collisionEpoch)
            if diagnostics is not None:
                diagnostics.RecordPhase("collider-key", started)
        excludedKey = frozenset(excludedWalls)
        # Rigid scene movement preserves every pair. Other edits validate only
        # queried pairs against their actual bounds or joined path signatures.
        resultCache = (batch["results"] if batch is not None and id(first) in batch["sceneIds"]
                       and id(second) in batch["sceneIds"] else {})
        resultKey = (min(id(first), id(second)), max(id(first), id(second)), contactTolerance, excludedKey)
        pairKeys = self.collisionPairKeys if batch is not None and resultCache is batch["results"] else {}
        pairEpochs = self.collisionPairEpochs if batch is not None and resultCache is batch["results"] else {}
        epoch = batch["epoch"] if batch is not None else None
        if resultKey in resultCache and pairEpochs.get(resultKey) == epoch:
            return resultCache[resultKey]
        if self.ObjectsOverlap(first, second, contactTolerance = contactTolerance):
            resultCache[resultKey] = True
            pairEpochs[resultKey] = epoch
            pairKeys.pop(resultKey, None)
            return True
        bounds = [self.JoinedObjectBounds(obj, excludedKey) for obj in (first, second)]
        if not bounds[0].intersects(bounds[1]):
            resultCache[resultKey] = False
            pairEpochs[resultKey] = epoch
            pairKeys.pop(resultKey, None)
            return False
        paths = []
        cache = getattr(self, "collisionFootprintCache", {})
        for obj in (first, second):
            pathKey = (id(obj), excludedKey)
            if batch is not None and pathKey in batch.get("paths", {}):
                paths.append(batch["paths"][pathKey])
                continue
            if type(obj) in (Wall, Pillar, Column, Stair, Counter, Railing):
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
                        workspace = workspaces.setdefault(type(obj), FootprintGeometry(self.basePixelsPerMillimeter))
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
                    cache[type(obj)] = (key, ownerPaths)
                paths.append(cache[type(obj)][1].get(id(obj), QtGui.QPainterPath()))
            else:
                path = QtGui.QPainterPath()
                path.addPolygon(QtGui.QPolygonF(self.ObjectCorners(obj)))
                path.closeSubpath()
                paths.append(path)
            if batch is not None:
                batch.setdefault("paths", {})[pathKey] = paths[-1]
        self.collisionFootprintCache = cache
        pathKeys = []
        for obj, path in zip((first, second), paths):
            pathKey = (id(obj), excludedKey)
            signature = batch.get("pathKeys", {}).get(pathKey) if batch is not None else None
            if signature is None:
                signature = tuple((element.x, element.y, element.type)
                                  for index in range(path.elementCount()) for element in (path.elementAt(index),))
                if batch is not None:
                    batch.setdefault("pathKeys", {})[pathKey] = signature
            pathKeys.append((id(obj), signature))
        pairKey = tuple(sorted(pathKeys))
        if pairKeys.get(resultKey) == pairKey and resultKey in resultCache:
            pairEpochs[resultKey] = epoch
            return resultCache[resultKey]
        pairKeys[resultKey] = pairKey
        pairEpochs[resultKey] = epoch
        if not paths[0].boundingRect().intersects(paths[1].boundingRect()):
            resultCache[resultKey] = False
            return False
        overlap = paths[0].intersected(paths[1])
        if overlap.isEmpty():
            resultCache[resultKey] = False
            return False
        for polygon in overlap.toFillPolygons():
            area = abs(sum(polygon[index].x() * polygon[(index + 1) % len(polygon)].y() -
                           polygon[(index + 1) % len(polygon)].x() * polygon[index].y() for index in range(len(polygon)))) / 2
            perimeter = sum(QtCore.QLineF(polygon[index], polygon[(index + 1) % len(polygon)]).length() for index in range(len(polygon)))
            if perimeter > 0 and area / perimeter > contactTolerance / 2:
                resultCache[resultKey] = True
                return True
        resultCache[resultKey] = False
        return False

    def JoinedObjectBounds(self, obj, excludedWalls = ()):
        """Conservative world bounds including arbitrary-length miter joins."""
        batch = getattr(self, "collisionPassCache", None)
        key = (id(obj), frozenset(excludedWalls))
        if batch is not None and key in batch.get("joinedBounds", {}):
            return batch["joinedBounds"][key]
        bounds = self.ObjectFootprint(obj)[0]
        if type(obj) in (Wall, Stair, Counter, Railing):
            category = type(obj)
            members = [wall for wall in self.walls if type(wall) is category and id(wall) not in excludedWalls and wall is not obj]
            for vertex, opposite, miter in ((obj.firstVertex, obj.secondVertex, obj.firstMiter),
                                              (obj.secondVertex, obj.firstVertex, obj.secondMiter)):
                delta = opposite - vertex
                length = math.hypot(delta.x(), delta.y())
                if length < 1e-10:
                    continue
                rays = [(delta / length, obj.width / 2, miter)]
                for other in members:
                    for endpoint, far, otherMiter in ((other.firstVertex, other.secondVertex, other.firstMiter),
                                                       (other.secondVertex, other.firstVertex, other.secondMiter)):
                        if QtCore.QLineF(vertex, endpoint).length() > .02000001:
                            continue
                        direction = far - endpoint
                        distance = math.hypot(direction.x(), direction.y())
                        if distance > 1e-10:
                            rays.append((direction / distance, other.width / 2, otherMiter))
                if len(rays) == 1:
                    continue
                halfWidth = max(ray[1] for ray in rays)
                radius = halfWidth + max(.01, .0001 / self.basePixelsPerMillimeter)
                maxMiter = max(1, *(abs(ray[2]) for ray in rays))
                for firstIndex, (firstDirection, firstWidth, firstMiter) in enumerate(rays):
                    for secondDirection, secondWidth, secondMiter in rays[firstIndex + 1:]:
                        cross = abs(firstDirection.x() * secondDirection.y() - firstDirection.y() * secondDirection.x())
                        if cross >= 1e-6:
                            radius = max(radius, (2 * halfWidth + 2 * halfWidth / cross) * maxMiter)
                # Covers the endpoint grouping tolerance as well as collinear
                # caps and unequal-width T transitions. Never cap long miters.
                radius += .04
                bounds = bounds.united(QtCore.QRectF(vertex.x() - radius, vertex.y() - radius, 2 * radius, 2 * radius))
        if batch is not None:
            batch.setdefault("joinedBounds", {})[key] = bounds
        return bounds

    def ContainedWalls(self, walls = None):
        walls = [wall for wall in (self.walls if walls is None else walls) if not isinstance(wall, (Stair, Arrow, MeasurementGuide, Railing))]
        footprints = [self.ObjectFootprint(wall) for wall in walls]
        cacheKey = tuple((id(wall), wall.footprintCache[0]) for wall in walls)
        if cacheKey == self.containedWallKey:
            return self.containedWallCache
        contained = []
        tolerance = .01
        expandedBounds = [bounds.adjusted(-tolerance, -tolerance, tolerance, tolerance) for bounds, corners, axes in footprints]
        for index, wall in enumerate(walls):
            bounds, corners, axes = footprints[index]
            if not corners:
                continue
            for otherIndex, other in enumerate(walls):
                if index == otherIndex:
                    continue
                otherBounds, otherCorners, otherAxes = footprints[otherIndex]
                if not otherCorners or not expandedBounds[otherIndex].contains(bounds):
                    continue
                containedOnAxes = True
                equalBounds = True
                for axis in otherAxes:
                    projections = [QtCore.QPointF.dotProduct(corner, axis) for corner in corners]
                    otherProjections = [QtCore.QPointF.dotProduct(corner, axis) for corner in otherCorners]
                    low, high = min(projections), max(projections)
                    otherLow, otherHigh = min(otherProjections), max(otherProjections)
                    if low < otherLow - tolerance or high > otherHigh + tolerance:
                        containedOnAxes = False
                        break
                    equalBounds = equalBounds and abs(low - otherLow) <= tolerance and abs(high - otherHigh) <= tolerance
                # Coincident duplicates flag the later wall, leaving one normal wall.
                if containedOnAxes and (not equalBounds or index > otherIndex):
                    contained.append(wall)
                    break
        self.containedWallKey = cacheKey
        self.containedWallCache = contained
        return contained

    def WallTranslation(self, previous, current):
        if not previous or len(previous) != len(current):
            return None
        deltaX = current[0][1] - previous[0][1]
        deltaY = current[0][2] - previous[0][2]
        for old, new in zip(previous, current):
            if old[0] != new[0] or old[5:] != new[5:]:
                return None
            if any(abs(new[index] - old[index] - delta) > 1e-7
                   for index, delta in ((1, deltaX), (2, deltaY), (3, deltaX), (4, deltaY))):
                return None
        return QtCore.QPointF(deltaX, deltaY)


class ReferenceScene:
    def AttachedVertices(self, selectedWall, captureAll = False):
        attachments = []
        self.dragConstraints = []
        if isinstance(selectedWall, (Label, Window)) or isinstance(selectedWall, Furnishing) and type(selectedWall) is not Furnishing:
            return attachments
        wholeObjects = self.selectedVertex is None and (self.connectedObjectsEnabled or captureAll)
        if isinstance(selectedWall, Pillar) and not wholeObjects:
            return attachments
        if type(selectedWall) is Furnishing:
            if not wholeObjects:
                return attachments
            candidates = [obj for obj in self.furnishings if type(obj) is Furnishing]
        else:
            candidates = [obj for obj in self.walls if
                          (type(obj) in (Wall, Pillar, Column) if wholeObjects and type(selectedWall) in (Wall, Pillar, Column)
                           else type(obj) is type(selectedWall))]
        # Work in world coordinates so exact contact is independent of zoom.
        paths = {}
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(.02)
        for obj in candidates if wholeObjects else ():
            corners = self.ObjectCorners(obj)
            path = QtGui.QPainterPath()
            if corners:
                path.moveTo(corners[0])
                for corner in corners[1:]:
                    path.lineTo(corner)
                if len(corners) > 2:
                    path.closeSubpath()
            paths[id(obj)] = path.united(stroker.createStroke(path))
        anchor = (selectedWall.firstVertex if self.selectedVertex == 0 else
                  selectedWall.secondVertex) if self.selectedVertex is not None else None
        direction = selectedWall.secondVertex - selectedWall.firstVertex
        length = math.hypot(direction.x(), direction.y())
        axis = direction / length if length > 1e-10 else QtCore.QPointF()
        for obj in candidates:
            if obj is selectedWall or isinstance(obj, Pillar) or type(obj) is not type(selectedWall):
                continue
            for index, vertex in enumerate((obj.firstVertex, obj.secondVertex)):
                offset = vertex - selectedWall.firstVertex
                along = QtCore.QPointF.dotProduct(offset, axis)
                across = abs(offset.x() * axis.y() - offset.y() * axis.x())
                inside = length > 1e-10 and -.01 <= along <= length + .01 and across <= selectedWall.width / 2 + .01
                if (QtCore.QLineF(vertex, anchor).length() <= .01 if anchor is not None else inside):
                    attachments.append((obj, index, QtCore.QPointF(vertex)))
        if not wholeObjects:
            return attachments
        directAttachments = attachments
        attachments = []
        pending = [selectedWall]
        visited = {id(selectedWall)}
        for parent in pending:
            for obj in candidates:
                if id(obj) in visited:
                    continue
                if type(selectedWall) in (Wall, Pillar, Column, Furnishing):
                    connected = paths[id(parent)].intersects(paths[id(obj)])
                else:
                    connected = any(QtCore.QLineF(first, second).length() <= .01
                                    for first in (parent.firstVertex, parent.secondVertex)
                                    for second in (obj.firstVertex, obj.secondVertex))
                if connected:
                    visited.add(id(obj))
                    pending.append(obj)
                    attachments.extend((obj, index, QtCore.QPointF(vertex))
                                       for index, vertex in enumerate((obj.firstVertex, obj.secondVertex)))
        if captureAll:
            keys = {(id(obj), index) for obj, index, vertex in attachments}
            self.dragObjectAttachmentKeys = keys
            attachments.extend(entry for entry in directAttachments if (id(entry[0]), entry[1]) not in keys)
        return attachments

    def ActiveAttachments(self):
        if self.groupDrag:
            return self.groupMovedVertices
        if not self.connectedEnabled or self.dragVertices is None:
            return []
        if self.selectedVertex is None and self.connectedObjectsEnabled:
            return [entry for entry in self.dragAttachments if (id(entry[0]), entry[1]) in self.dragObjectAttachmentKeys]
        if not self.connectedVerticesEnabled:
            return []
        if self.selectedVertex is not None:
            anchor = self.dragVertices[self.selectedVertex]
            return [entry for entry in self.dragAttachments if QtCore.QLineF(entry[2], anchor).length() <= .01]
        if isinstance(self.selectedWall, Pillar):
            return []
        direction = self.dragVertices[1] - self.dragVertices[0]
        length = math.hypot(direction.x(), direction.y())
        axis = direction / length if length > 1e-10 else QtCore.QPointF()
        direct = []
        for entry in self.dragAttachments:
            obj, index, vertex = entry
            if type(obj) is not type(self.selectedWall):
                continue
            offset = vertex - self.dragVertices[0]
            along = QtCore.QPointF.dotProduct(offset, axis)
            across = abs(offset.x() * axis.y() - offset.y() * axis.x())
            if length > 1e-10 and -.01 <= along <= length + .01 and across <= self.selectedWall.width / 2 + .01:
                direct.append(entry)
        return direct


class ReferencePlacement:
    def FitWallOpenings(self, before = None, validateFurnishings = True, validateScene = True):
        followStretch = self.connectedEnabled and self.connectedObjectsEnabled
        oldWalls = {id(state[0]): state for state in before[0]} if before is not None else {}
        oldCenters = {id(state[0]): state[2] for state in before[3]} if before is not None else {}
        for wall in self.walls:
            openings = sorted((opening for opening in self.windows if opening.parentWall is wall),
                              key = lambda opening: opening.centerFraction)
            if not openings:
                continue
            parentLength = QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
            remainingLength = self.MinimumOpeningLength(wall)
            if parentLength < remainingLength - 0.01:
                return False
            cursor = 0.0
            for opening in openings:
                center = opening.centerFraction * parentLength
                oldWall = oldWalls.get(id(wall))
                if not followStretch and oldWall is not None:
                    oldFirst = QtCore.QPointF(oldWall[1], oldWall[2])
                    oldSecond = QtCore.QPointF(oldWall[3], oldWall[4])
                    oldLength = QtCore.QLineF(oldFirst, oldSecond).length()
                    oldCenter = oldCenters.get(id(opening), opening.centerFraction)
                    if wall.firstVertex == oldFirst:
                        center = oldCenter * oldLength
                    elif wall.secondVertex == oldSecond:
                        center = parentLength - (1 - oldCenter) * oldLength
                    elif abs(parentLength - oldLength) > 0.01:
                        # When both ends deform, carry the center by their mean
                        # translation and project it onto the new wall axis.
                        oldPosition = oldFirst + (oldSecond - oldFirst) * oldCenter
                        translation = (wall.firstVertex - oldFirst + wall.secondVertex - oldSecond) / 2
                        direction = (wall.secondVertex - wall.firstVertex) / parentLength
                        center = QtCore.QPointF.dotProduct(oldPosition + translation - wall.firstVertex, direction)
                desiredStart = center - opening.length / 2
                start = max(cursor, min(parentLength - remainingLength, desiredStart))
                opening.centerFraction = (start + opening.length / 2) / parentLength
                cursor = start + opening.length
                remainingLength -= opening.length
        return self.OpeningsValid(validateFurnishings = validateFurnishings, before = before) if validateScene else True

    def OpeningsOverlap(self, first, second):
        if not self.CollisionEnabled(first, second):
            return False
        if first.parentWall is second.parentWall:
            return min(first.secondFraction, second.secondFraction) - max(first.firstFraction, second.firstFraction) > 1e-8
        return self.JoinedObjectsOverlap(first, second)

    def OpeningFits(self, opening, exclude = None):
        parentLength = QtCore.QLineF(opening.parentWall.firstVertex, opening.parentWall.secondVertex).length()
        if parentLength < 1 or opening.length < 1:
            return False
        halfSpan = opening.length / (2 * parentLength)
        if opening.centerFraction - halfSpan < -1e-8 or opening.centerFraction + halfSpan > 1 + 1e-8:
            return False
        if any(type(wall) in (Wall, Pillar, Column) and wall is not opening.parentWall and
               self.JoinedObjectsOverlap(opening, wall, contactTolerance = 1.0) for wall in self.walls):
            return False
        return not any(other is not exclude and other is not opening and self.OpeningsOverlap(opening, other)
                       for other in self.windows)

