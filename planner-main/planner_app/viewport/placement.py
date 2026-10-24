"""Placement previews, opening fitting, collision validation and sidebar drops."""
from planner_app.models import AngleGuide

from planner_app.models import Elevator

import math
from contextlib import contextmanager
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import OpenDoorway, Door, Furnishing, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, SlidingDoor, MeasurementGuide, BoundaryLine, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, Window, NorthArrow, Fireplace
from .geometry import CollisionPass
from planner_app.geometry.opening_placement import (ProjectOpening, OpeningGap,
    BlockedOpeningIntervals, OpeningPlacementSpan, CenteredOpeningSpan)
from planner_app.geometry.opening_collisions import OpeningCollisionIndex
from planner_app.geometry.attachments import FitOpeningCenters, OpeningWithinWall, OpeningIntervalsOverlap
from planner_app.placement_sizing import NominalPlacementSize, FurnishingPlacementSize


class PlacementMixin:
    def ArchitecturalPlacementFits(self, obj):
        if isinstance(obj, Window):
            return self.OpeningFits(obj)
        if isinstance(obj, Stair):
            return self.StairFits(obj)
        if isinstance(obj, Counter):
            return self.CounterFits(obj)
        return self.WallFits(obj)

    def AutoSizingLimits(self, kind):
        values = self.stairStepSizes if kind == "stairs" else self.railingSpacings
        unitsMode = self.autoSizingUnitsMode or self.unitsMode
        overrides = self.imperialAutoSizes.get(kind, {}) if unitsMode in ("Feet and Inches", "Inches") else {}
        return {key: overrides.get(key, NominalPlacementSize(value * 10, unitsMode)) for key, value in values.items()}

    def DefaultPlacementSize(self, key):
        if self.unitsMode in ("Feet and Inches", "Inches") and str(key) in self.imperialDefaultSizes:
            return self.imperialDefaultSizes[str(key)]
        value = (self.wallPresetWidths[key] if isinstance(key, int) else
                 self.miscDefaultSizes[key] if key in self.miscDefaultSizes else self.openingDefaultSizes[key])
        return NominalPlacementSize(value * 10, self.unitsMode)

    def FindFireplacePlacement(self, position, modifiers, source = None, initialSize = None):
        worldPosition = self.ViewportToWorld(position)
        width = initialSize[0] if initialSize is not None else source.width if source is not None else self.DefaultPlacementSize("Fireplace")
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
        offsetTargets = ([-limit, limit] if self.cornerSnapEnabled else []) + ([0.0] if self.midpointSnapEnabled else [])
        if offsetTargets and self.alignmentSnapEnabled and self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            target = min(offsetTargets, key = lambda target: abs(target - offset))
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

    def FindArrowPlacement(self, position, modifiers, objectClass = Arrow):
        center = self.ViewportToWorld(position)
        if objectClass is AngleGuide:
            center = self.SnapPosition(center, modifiers, snapTargets = self.StairSnapTargets())
            return AngleGuide(center + QtCore.QPointF(900, 0), center + QtCore.QPointF(0, 900), middleVertex = center)
        if objectClass in (Pillar, Column, Elevator):
            size = self.DefaultPlacementSize(objectClass.__name__)
            arrow = objectClass(center - QtCore.QPointF(0, size / 2), center + QtCore.QPointF(0, size / 2),
                           width = size, material = self.newWallMaterial)
        else:
            halfLength = NominalPlacementSize(1000, self.unitsMode) / 2 if objectClass is Railing else 500
            arrow = objectClass(center - QtCore.QPointF(halfLength, 0), center + QtCore.QPointF(halfLength, 0))
            if objectClass is Railing:
                arrow.width = self.DefaultPlacementSize("Railing")
        delta = self.SnapObjectMovement(self.ObjectCorners(arrow) + [center] if isinstance(arrow, Pillar) else [arrow.firstVertex, arrow.secondVertex, center], QtCore.QPointF(), modifiers,
                                       snapTargets = self.StairSnapTargets())
        if isinstance(arrow, Railing):
            limits = self.AutoSizingLimits("railings")
            arrow.spacingBounds = tuple(limits[key] for key in ("minimum", "maximum", "target"))
        arrow.firstVertex += delta
        arrow.secondVertex += delta
        return arrow

    def FindCounterPlacement(self, position, modifiers):
        center = self.ViewportToWorld(position)
        halfLength = NominalPlacementSize(1000, self.unitsMode) / 2
        counter = Counter(center - QtCore.QPointF(halfLength, 0), center + QtCore.QPointF(halfLength, 0),
                          width = self.DefaultPlacementSize("Counter"))
        anchors = self.ObjectCorners(counter) + [center]
        delta = self.SnapObjectMovement(anchors, QtCore.QPointF(), modifiers,
                                       snapTargets = self.StairSnapTargets())
        counter.firstVertex += delta
        counter.secondVertex += delta
        return counter

    def CounterFits(self, counter):
        if counter.width < 1 or QtCore.QLineF(counter.firstVertex, counter.secondVertex).length() < 1:
            return False
        blockers = [wall for wall in self.walls if not isinstance(wall, Counter)]
        return not any(self.JoinedObjectsOverlap(counter, obj, contactTolerance = 1.0) for obj in blockers)

    def WallFits(self, wall, blockers = None):
        if isinstance(wall, AngleGuide):
            return True
        if isinstance(wall, (Arrow, MeasurementGuide)):
            return QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() >= 1
        if wall.width < 1 or QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() < 1:
            return False
        if isinstance(wall, Elevator):
            blockers = [obj for obj in self.walls + self.windows + self.furnishings if obj is not wall]
        if blockers is None:
            blockers = (self.furnishings + [obj for obj in self.walls if isinstance(obj, (Counter, Railing, Stair, Elevator))]
                        + [opening for opening in self.windows if opening.parentWall is not wall])
        return not any(self.JoinedObjectsOverlap(wall, obj, contactTolerance = 1.0) for obj in blockers)

    def FurnishingFits(self, furnishing):
        if isinstance(furnishing, Pillar):
            return self.WallFits(furnishing)
        if isinstance(furnishing, (Label, NorthArrow)):
            return True
        return (furnishing.width >= 1 and furnishing.length >= 1
                and not any(self.JoinedObjectsOverlap(furnishing, other, contactTolerance = 1.0)
                            for other in self.walls if not isinstance(other, Counter)))

    def FindFurnishingPlacement(self, position, definition, modifiers):
        center = self.ViewportToWorld(position)
        furnishing = Furnishing(definition, center)
        furnishing.width, length = FurnishingPlacementSize(definition, self.unitsMode)
        furnishing.firstVertex = center - QtCore.QPointF(0, length / 2)
        furnishing.secondVertex = center + QtCore.QPointF(0, length / 2)
        anchors = self.ObjectCorners(furnishing) + [center]
        delta = self.SnapObjectMovement(anchors, QtCore.QPointF(), modifiers,
                                       snapTargets = self.StairSnapTargets())
        furnishing.firstVertex += delta
        furnishing.secondVertex += delta
        return furnishing

    def OpeningsOverlap(self, first, second):
        if not self.CollisionEnabled(first, second):
            return False
        if first.parentWall is second.parentWall:
            return OpeningIntervalsOverlap(first.firstFraction, first.secondFraction,
                                           second.firstFraction, second.secondFraction)
        return self.JoinedObjectsOverlap(first, second)

    @contextmanager
    def OpeningCandidatePass(self, count):
        # This scope is used only around read-only opening validation. Restore
        # the previous entry even on early failure; no index may escape into
        # endpoint edits or the fitting/model assignments that follow.
        batch = getattr(self, "collisionPassCache", None)
        if batch is None:
            yield
            return
        previous = batch.pop("openingCandidates", None)
        try:
            if count >= 4 and len(self.walls) + len(self.windows) >= 32:
                parent = self.windows[0].parentWall if self.windows else None
                hasSpatialPairs = (any(type(wall) in (Wall, Pillar, Column) and wall is not parent for wall in self.walls)
                                   or any(opening.parentWall is not parent for opening in self.windows))
                # With only sibling openings and their parent, every interval
                # must still be checked; an index cannot remove any candidates.
                if hasSpatialPairs:
                    # Keep the first opening on the normal fast-failure path.
                    batch["openingCandidates"] = {"primed": False, "prepared": None}
            yield
        finally:
            batch.pop("openingCandidates", None)
            if previous is not None:
                batch["openingCandidates"] = previous

    def BuildOpeningCollisionIndex(self):
        walls = [wall for wall in self.walls if type(wall) in (Wall, Pillar, Column)]
        openings = list(self.windows)
        wallBounds, openingBounds = [], []
        for wall in walls:
            bounds = self.JoinedObjectBounds(wall)
            wallBounds.append((bounds.left(), bounds.top(), bounds.right(), bounds.bottom()))
        for opening in openings:
            bounds = self.JoinedObjectBounds(opening)
            openingBounds.append((id(opening.parentWall), (bounds.left(), bounds.top(), bounds.right(), bounds.bottom())))
        return OpeningCollisionIndex(wallBounds, openingBounds), walls, openings

    @CollisionPass
    def OpeningFits(self, opening, exclude = None, excludeIds = frozenset()):
        parentLength = QtCore.QLineF(opening.parentWall.firstVertex, opening.parentWall.secondVertex).length()
        if not OpeningWithinWall(parentLength, opening.length, opening.centerFraction):
            return False
        walls, openings = self.walls, self.windows
        batch = getattr(self, "collisionPassCache", None)
        scope = (batch or {}).get("openingCandidates")
        prepared = None
        if scope is not None:
            if not scope["primed"]:
                scope["primed"] = True
            else:
                prepared = scope["prepared"]
                if prepared is None:
                    prepared = self.BuildOpeningCollisionIndex()
                    scope["prepared"] = prepared
        if prepared is not None:
            candidateIndex, indexedWalls, indexedOpenings = prepared
            bounds = self.JoinedObjectBounds(opening)
            wallIndices, openingIndices = candidateIndex.Query(
                (bounds.left(), bounds.top(), bounds.right(), bounds.bottom()), id(opening.parentWall))
            walls = (indexedWalls[index] for index in wallIndices)
            openings = (indexedOpenings[index] for index in openingIndices)
        if any(type(wall) in (Wall, Pillar, Column) and wall is not opening.parentWall and
               self.JoinedObjectsOverlap(opening, wall, contactTolerance = 1.0) for wall in walls):
            return False
        return not any(other is not exclude and other is not opening and (not excludeIds or id(other) not in excludeIds)
                       and self.OpeningsOverlap(opening, other)
                       for other in openings)

    @CollisionPass
    def OpeningsValid(self, validateFurnishings = True, before = None):
        changed = None
        if before is not None:
            oldWalls = {id(state[0]): state[1:8] for state in before[0]}
            oldOpenings = {id(state[0]): state[1:4] for state in before[3]}
            oldFurnishings = {id(state[0]): state[1:4] for state in before[5]} if len(before) > 5 else {}
            changed = {id(wall) for wall in self.walls if oldWalls.get(id(wall)) != (
                wall.firstVertex.x(), wall.firstVertex.y(), wall.secondVertex.x(), wall.secondVertex.y(),
                wall.width, wall.firstMiter, wall.secondMiter)}
            changed.update(id(opening) for opening in self.windows if oldOpenings.get(id(opening)) != (
                opening.parentWall, opening.centerFraction, opening.length))
            changed.update(id(obj) for obj in self.furnishings if oldFurnishings.get(id(obj)) != (
                obj.firstVertex, obj.secondVertex, obj.width))
        walls = self.walls if changed is None else [wall for wall in self.walls if id(wall) in changed]
        furnishings = self.furnishings if changed is None else [obj for obj in self.furnishings if id(obj) in changed]
        # Keep source order within each parent: sum() and fitting must see the
        # same lengths, including duplicate entries, as the original scene scan.
        openingLengths = None
        if len(walls) > 1:
            openingLengths = {}
            for opening in self.windows:
                openingLengths.setdefault(id(opening.parentWall), []).append(opening.length)
        for wall in walls:
            if isinstance(wall, AngleGuide):
                continue
            length = QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
            minimumLength = (self.MinimumOpeningLength(wall) if openingLengths is None
                             else sum(openingLengths.get(id(wall), ())))
            if length < 1e-8 or length < minimumLength - 0.01:
                return False
        count = len(self.windows) if changed is None else sum(
            id(opening) in changed or id(opening.parentWall) in changed for opening in self.windows)
        with self.OpeningCandidatePass(count):
            for index, opening in enumerate(self.windows):
                if changed is not None and id(opening) not in changed and id(opening.parentWall) not in changed:
                    continue
                if not self.OpeningFits(opening):
                    return False
                scope = (getattr(self, "collisionPassCache", None) or {}).get("openingCandidates")
                prepared = scope["prepared"] if scope is not None else None
                if prepared is not None:
                    candidateIndex, indexedWalls, indexedOpenings = prepared
                    bounds = self.JoinedObjectBounds(opening)
                    wallIndices, openingIndices = candidateIndex.Query(
                        (bounds.left(), bounds.top(), bounds.right(), bounds.bottom()), id(opening.parentWall))
                    others = (indexedOpenings[otherIndex] for otherIndex in openingIndices if otherIndex > index)
                else:
                    others = self.windows[index + 1:]
                if any(self.OpeningsOverlap(opening, other) for other in others):
                    return False
        return (all(self.StairFits(wall) for wall in walls if isinstance(wall, Stair))
                and all(self.CounterFits(wall) for wall in walls if isinstance(wall, Counter))
                and all(self.WallFits(wall) for wall in walls if isinstance(wall, Pillar)
                        or changed is not None and type(wall) is Wall)
                and (not validateFurnishings or all(self.FurnishingFits(obj) for obj in furnishings)))

    def StairFits(self, stair, exclude = None):
        if stair.width < 1 or QtCore.QLineF(stair.firstVertex, stair.secondVertex).length() < 1:
            return False
        for other in self.walls + self.windows + self.furnishings + self.labels:
            # Snapped faces can differ by sub-millimeter amounts after endpoint
            # rotation and screen/world conversion. Treat that as edge contact.
            if isinstance(other, Stair) or other is exclude or not self.JoinedObjectsOverlap(stair, other, contactTolerance = 1.0):
                continue
            return False
        return True

    def FindStairPlacement(self, position, source = None, modifiers = None):
        center = self.ViewportToWorld(position)
        direction = source.secondVertex - source.firstVertex if source is not None else QtCore.QPointF(NominalPlacementSize(1000, self.unitsMode), 0)
        stair = Stair(center - direction / 2, center + direction / 2,
                      source.width if source is not None else self.DefaultPlacementSize("Stair"),
                      directionReversed = source.directionReversed if source is not None else False)
        if source is not None:
            stair.autosize, stair.manualStepCount = source.autosize, source.manualStepCount
        limits = self.AutoSizingLimits("stairs")
        stair.stepSizeBounds = (limits["minimum"], limits["maximum"])
        placements = [(float("inf"), QtCore.QPointF(), [])]
        snapTargets = self.StairSnapTargets(source)
        for anchor in self.ObjectCorners(stair) + [center]:
            snapped = self.SnapPosition(anchor, modifiers or QtCore.Qt.KeyboardModifier.NoModifier, snapTargets = snapTargets)
            if self.snapApplied:
                correction = snapped - anchor
                placements.append((QtCore.QLineF(self.WorldToViewport(anchor), self.WorldToViewport(snapped)).length(),
                                   correction, list(self.alignmentGuides)))
        first, second = QtCore.QPointF(stair.firstVertex), QtCore.QPointF(stair.secondVertex)
        for distance, correction, guides in sorted(placements, key = lambda candidate: candidate[0]):
            stair.firstVertex, stair.secondVertex = first + correction, second + correction
            if self.StairFits(stair, source):
                self.alignmentGuides = guides
                return stair
        self.alignmentGuides = []
        return None

    def PlaceStair(self, position, modifiers = None, placement = None):
        stair = placement if placement is not None else self.FindStairPlacement(position, modifiers = modifiers)
        if stair is None or not self.DrawingRect().contains(position) or not self.StairFits(stair):
            return None
        before = self.CaptureState()
        self.walls.append(stair)
        self.selectedWall, self.selectedVertex = stair, None
        self.RecordEdit(before)
        self.selectionChanged.emit()
        self.setFocus()
        self.update()
        return stair

    def MinimumOpeningLength(self, wall):
        lengths = [opening.length for opening in self.windows if opening.parentWall is wall]
        return sum(lengths)

    def FitWallOpenings(self, before = None, validateFurnishings = True, validateScene = True):
        followStretch = self.connectedEnabled and self.connectedObjectsEnabled
        oldWalls = {id(state[0]): state for state in before[0]} if before is not None else {}
        oldCenters = {id(state[0]): state[2] for state in before[3]} if before is not None else {}
        openingsByParent = {}
        for opening in self.windows:
            openingsByParent.setdefault(id(opening.parentWall), []).append(opening)
        for wall in self.walls:
            siblings = openingsByParent.get(id(wall), ())
            openings = sorted(siblings, key = lambda opening: opening.centerFraction)
            if not openings:
                continue
            parentLength = QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
            remainingLength = sum(opening.length for opening in siblings)
            oldWall = oldWalls.get(id(wall))
            previous, fixedEnd = None, 0
            if not followStretch and oldWall is not None:
                oldFirst, oldSecond = QtCore.QPointF(oldWall[1], oldWall[2]), QtCore.QPointF(oldWall[3], oldWall[4])
                previous = ((oldFirst.x(), oldFirst.y()), (oldSecond.x(), oldSecond.y()),
                            QtCore.QLineF(oldFirst, oldSecond).length())
                fixedEnd = 1 if wall.firstVertex == oldFirst else 2 if wall.secondVertex == oldSecond else 0
            centers = FitOpeningCenters((wall.firstVertex.x(), wall.firstVertex.y()),
                (wall.secondVertex.x(), wall.secondVertex.y()), parentLength,
                [(index, opening.centerFraction, opening.length, oldCenters.get(id(opening), opening.centerFraction))
                 for index, opening in enumerate(openings)], remainingLength, previous, fixedEnd)
            if centers is None:
                return False
            for index, center in centers:
                openings[index].centerFraction = center
        return self.OpeningsValid(validateFurnishings = validateFurnishings, before = before) if validateScene else True

    def SetOpeningVertex(self, opening, vertexIndex, position, fromCenter = False, initialState = None):
        originalState = (opening.centerFraction, opening.length)
        if initialState is not None:
            opening.centerFraction, opening.length = initialState
        original = (opening.firstFraction, opening.secondFraction)
        if fromCenter:
            parent = opening.parentWall
            gapStart, gapEnd = OpeningGap(opening.centerFraction,
                ((other.firstFraction, other.secondFraction) for other in self.windows
                 if other is not opening and other.parentWall is parent))
            first, second = parent.firstVertex, parent.secondVertex
            fractions = CenteredOpeningSpan((first.x(), first.y()), (second.x(), second.y()),
                (position.x(), position.y()), vertexIndex, opening.centerFraction, gapStart, gapEnd)
            if fractions is None:
                opening.centerFraction, opening.length = originalState
                return
            opening.SetFractions(*fractions)
        else:
            opening.SetVertex(vertexIndex, position)
            for other in self.windows:
                if other is opening or other.parentWall is not opening.parentWall:
                    continue
                if vertexIndex == 0 and other.secondFraction <= original[0] + 1e-8:
                    opening.firstFraction = max(opening.firstFraction, other.secondFraction)
                elif vertexIndex == 1 and other.firstFraction >= original[1] - 1e-8:
                    opening.secondFraction = min(opening.secondFraction, other.firstFraction)
        if not self.OpeningFits(opening):
            opening.centerFraction, opening.length = originalState

    def FindWindowPlacement(self, position, length = None, preferredWall = None, openingType = Window, exclude = None, modifiers = None,
                            excludeIds = frozenset()):
        if length is None:
            length = self.DefaultPlacementSize(openingType.__name__) * (2 if openingType in (SlidingDoor, PocketDoor, BarnDoor) else 1)
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
            from .geometry import FootprintGeometry
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
        prepared = getattr(self, "openingPlacementPolygons", None)
        if prepared is None or prepared[0] is not self.openingFootprints:
            prepared = (self.openingFootprints, [(owner, polygon.boundingRect(), tuple((point.x(), point.y()) for point in polygon))
                                               for owner, polygon in self.openingFootprints])
            self.openingPlacementPolygons = prepared
        preparedPolygons = prepared[1]
        numericSnapTargets = None
        walls = ([preferredWall] + [wall for wall in reversed(self.walls) if wall is not preferredWall]
                 if preferredWall is not None else reversed(self.walls))
        for wall in walls:
            if type(wall) is not Wall or not self.IsObjectVisible(wall):
                continue
            projection = ProjectOpening((wall.firstVertex.x(), wall.firstVertex.y()),
                (wall.secondVertex.x(), wall.secondVertex.y()), (worldPosition.x(), worldPosition.y()))
            if projection is None:
                continue
            numericDirection, lengthSquared, fraction, numericProjected = projection
            direction, projected = QtCore.QPointF(*numericDirection), QtCore.QPointF(*numericProjected)
            distance = QtCore.QLineF(position, self.WorldToViewport(projected)).length()
            reach = wall.width * self.basePixelsPerMillimeter * self.zoom / 2 + 24
            if distance <= reach and distance < nearestDistance:
                parentLength = math.sqrt(lengthSquared)
                gapStart, gapEnd = OpeningGap(fraction,
                    ((other.firstFraction, other.secondFraction) for other in self.windows
                     if other is not exclude and other.parentWall is wall and (not excludeIds or id(other) not in excludeIds)))
                if (gapEnd - gapStart) * parentLength < 1.0:
                    continue
                parentCorners = self.ObjectCorners(wall)
                parentBounds = QtGui.QPolygonF(parentCorners).boundingRect()
                blocked = BlockedOpeningIntervals([(point.x(), point.y()) for point in parentCorners],
                    (wall.firstVertex.x(), wall.firstVertex.y()), numericDirection, lengthSquared,
                    (polygon for owner, bounds, polygon in preparedPolygons if owner is not wall and parentBounds.intersects(bounds)))
                gapStart, gapEnd = OpeningGap(fraction, blocked, gapStart, gapEnd)
                if (gapEnd - gapStart) * parentLength < 1.0:
                    continue
                span, minimumCenter, maximumCenter, center = OpeningPlacementSpan(length, parentLength, fraction, gapStart, gapEnd)
                midpoint = wall.firstVertex + direction * center
                anchors = (midpoint, midpoint - direction * (span / 2), midpoint + direction * (span / 2))
                # A raw placement is a fallback, not a zero-distance snap target.
                placements = [(3, float("inf"), openingType(wall, center - span / 2, center + span / 2), [])]
                if openingType is not Fireplace and numericSnapTargets is None:
                    # The scene and drag exclusions stay fixed throughout this
                    # query; share one target snapshot across all three anchors.
                    numericSnapTargets = []
                    if self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
                        numericSnapTargets = self.NumericSnapTargets()
                        if self.midpointSnapEnabled:
                            numericSnapTargets.extend((vertex.x(), vertex.y(), True) for vertex in self.SnapMidpoints())
                for anchor in (() if openingType is Fireplace else anchors):
                    snapped = self.SnapPosition(anchor, modifiers, wall.firstVertex, direction / parentLength,
                                                preparedTargets = [], numericTargets = numericSnapTargets)
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
                    fits = (self.OpeningFits(candidate, exclude, excludeIds) if excludeIds else self.OpeningFits(candidate, exclude))
                    if fits:
                        nearest = candidate
                        nearestGuides = guides
                        nearestDistance = distance
                        break
        self.alignmentGuides = nearestGuides
        return nearest

    def InactiveOpening(self, center, openingType, source = None, initialSize = None):
        length = (source.length if source is not None else self.DefaultPlacementSize("Fireplace") if openingType is Fireplace else
                  self.DefaultPlacementSize(openingType.__name__) * (2 if openingType in (SlidingDoor, PocketDoor, BarnDoor) else 1))
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

    def PlaceWindow(self, position, openingType = Window, modifiers = None, placement = None):
        window = placement if placement is not None else self.FindWindowPlacement(position, openingType = openingType, modifiers = modifiers)
        if window is None or not self.DrawingRect().contains(position):
            return None
        before = self.CaptureState()
        self.windows.append(window)
        self.selectedWall = window
        self.selectedVertex = None
        self.RecordEdit(before)
        self.selectionChanged.emit()
        self.setFocus()
        self.update()
        return window

    def UpdateOpeningPreview(self, position, openingType, modifiers):
        if not self.DrawingRect().contains(position):
            self.windowDropPreview = None
            self.inactiveOpeningPreview = None
            self.doorOrientationLocked = False
            self.alignmentGuides = []
        elif (openingType in (Window, Door, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow)
              and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier
              and isinstance(self.windowDropPreview, openingType)):
            self.doorOrientationLocked = True
            self.alignmentGuides = []
            self.OrientDoor(self.windowDropPreview, position)
        else:
            self.doorOrientationLocked = False
            self.windowDropPreview = self.FindWindowPlacement(position, openingType = openingType, modifiers = modifiers)
            self.inactiveOpeningPreview = (None if self.windowDropPreview is not None else
                                           self.InactiveOpening(self.ViewportToWorld(position), openingType))
        self.update()

    def CancelGuiDrag(self):
        self.guiDragCancelled = True
        QtGui.QDrag.cancel()
        self.CancelInteraction()

    def dragEnterEvent(self, event):
        if self.exportOverlay.active:
            event.ignore()
            return
        if event.mimeData().hasFormat("application/x-planner-fireplace"):
            if self.exportOverlay.active or self.guiDragCancelled:
                event.ignore()
                return
            event.acceptProposedAction()
            return
        if self.guiDragCancelled:
            event.ignore()
            return
        if any(event.mimeData().hasFormat("application/x-planner-" + kind) for kind in ("arrow", "measurement-guide", "boundary-line", "angle-guide", "railing", "pillar", "column", "elevator")):
            event.acceptProposedAction()
            return
        if event.mimeData().hasFormat("application/x-planner-counter"):
            event.acceptProposedAction()
            return
        if event.mimeData().hasFormat("application/x-planner-north-arrow"):
            event.acceptProposedAction()
            return
        if event.mimeData().hasFormat("application/x-planner-label"):
            event.acceptProposedAction()
            return
        if event.mimeData().hasFormat("application/x-planner-furnishing"):
            key = bytes(event.mimeData().data("application/x-planner-furnishing")).decode()
            if key in self.furnishingDefinitions:
                event.acceptProposedAction()
                return
        if any(event.mimeData().hasFormat(f"application/x-planner-{kind}") for kind in ("window", "silled-window", "casement-window", "door", "sliding-door", "pocket-door", "barn-door", "bifold-door", "open-doorway", "stair")):
            event.setDropAction(QtCore.Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self.exportOverlay.active:
            event.ignore()
            return
        if self.guiDragActive and event.buttons() & QtCore.Qt.MouseButton.RightButton:
            self.CancelGuiDrag()
        if self.guiDragCancelled:
            event.ignore()
            return
        if any(event.mimeData().hasFormat("application/x-planner-" + kind) for kind in ("arrow", "measurement-guide", "boundary-line", "angle-guide", "railing", "pillar", "column", "elevator")):
            self.hoverPosition = event.position()
            if self.DrawingRect().contains(event.position()):
                self.arrowPreview = self.FindArrowPlacement(event.position(), event.modifiers(),
                    Elevator if event.mimeData().hasFormat("application/x-planner-elevator") else
                    Column if event.mimeData().hasFormat("application/x-planner-column") else
                    Pillar if event.mimeData().hasFormat("application/x-planner-pillar") else
                    Railing if event.mimeData().hasFormat("application/x-planner-railing") else
                    AngleGuide if event.mimeData().hasFormat("application/x-planner-angle-guide") else
                    BoundaryLine if event.mimeData().hasFormat("application/x-planner-boundary-line") else
                    MeasurementGuide if event.mimeData().hasFormat("application/x-planner-measurement-guide") else Arrow)
                event.acceptProposedAction()
            else:
                self.arrowPreview = None
                self.alignmentGuides = []
                event.ignore()
            self.update()
            return
        if event.mimeData().hasFormat("application/x-planner-counter"):
            self.hoverPosition = event.position()
            if self.DrawingRect().contains(event.position()):
                self.counterPreview = self.FindCounterPlacement(event.position(), event.modifiers())
                event.acceptProposedAction()
            else:
                self.counterPreview = None
                self.arrowPreview = None
                event.ignore()
            self.update()
            return
        if event.mimeData().hasFormat("application/x-planner-fireplace"):
            self.hoverPosition = event.position()
            self.windowDropPreview = (self.FindFireplacePlacement(event.position(), event.modifiers())
                                      if self.DrawingRect().contains(event.position()) else None)
            self.inactiveOpeningPreview = (self.InactiveOpening(self.ViewportToWorld(event.position()), Fireplace)
                if self.windowDropPreview is None and self.DrawingRect().contains(event.position()) else None)
            if self.DrawingRect().contains(event.position()) and not self.exportOverlay.active:
                event.setDropAction(QtCore.Qt.DropAction.CopyAction)
                event.accept()
            else:
                event.ignore()
            self.update()
            return
        if event.mimeData().hasFormat("application/x-planner-north-arrow"):
            self.hoverPosition = event.position()
            if self.DrawingRect().contains(event.position()):
                center = self.SnapPosition(self.ViewportToWorld(event.position()), event.modifiers())
                self.furnishingPreview = NorthArrow(center)
                event.acceptProposedAction()
            else:
                self.furnishingPreview = None
                event.ignore()
            self.update()
            return
        if event.mimeData().hasFormat("application/x-planner-label"):
            self.hoverPosition = event.position()
            if self.DrawingRect().contains(event.position()):
                origin = self.SnapPosition(self.ViewportToWorld(event.position()), event.modifiers())
                self.labelPreview = Label(origin)
                event.acceptProposedAction()
            else:
                self.labelPreview = None
                event.ignore()
            self.update()
            return
        if event.mimeData().hasFormat("application/x-planner-furnishing"):
            key = bytes(event.mimeData().data("application/x-planner-furnishing")).decode()
            if key in self.furnishingDefinitions and self.DrawingRect().contains(event.position()):
                self.furnishingPreview = self.FindFurnishingPlacement(event.position(), self.furnishingDefinitions[key], event.modifiers())
                event.acceptProposedAction()
            else:
                self.furnishingPreview = None
                event.ignore()
            self.update()
            return
        self.hoverPosition = event.position()
        if event.mimeData().hasFormat("application/x-planner-stair"):
            if not self.DrawingRect().contains(event.position()):
                self.windowDropPreview = None
                self.inactiveOpeningPreview = None
                event.ignore()
            else:
                self.doorOrientationLocked = False
                self.windowDropPreview = self.FindStairPlacement(event.position(), modifiers = event.modifiers())
                center = self.ViewportToWorld(event.position())
                halfLength = NominalPlacementSize(1000, self.unitsMode) / 2
                self.inactiveOpeningPreview = (None if self.windowDropPreview is not None else
                                               Stair(center - QtCore.QPointF(halfLength, 0), center + QtCore.QPointF(halfLength, 0),
                                                     width = self.DefaultPlacementSize("Stair")))
                event.setDropAction(QtCore.Qt.DropAction.CopyAction)
                event.accept()
            self.update()
            return
        openingType = (OpenDoorway if event.mimeData().hasFormat("application/x-planner-open-doorway") else
                       BifoldDoor if event.mimeData().hasFormat("application/x-planner-bifold-door") else
                       BarnDoor if event.mimeData().hasFormat("application/x-planner-barn-door") else
                       PocketDoor if event.mimeData().hasFormat("application/x-planner-pocket-door") else
                       SlidingDoor if event.mimeData().hasFormat("application/x-planner-sliding-door") else
                       Door if event.mimeData().hasFormat("application/x-planner-door") else
                       SilledWindow if event.mimeData().hasFormat("application/x-planner-silled-window") else
                       CasementWindow if event.mimeData().hasFormat("application/x-planner-casement-window") else Window)
        if (any(event.mimeData().hasFormat(f"application/x-planner-{kind}") for kind in ("window", "silled-window", "casement-window", "door", "sliding-door", "pocket-door", "barn-door", "bifold-door", "open-doorway"))
                and self.DrawingRect().contains(event.position())):
            self.UpdateOpeningPreview(event.position(), openingType, event.modifiers())
            event.setDropAction(QtCore.Qt.DropAction.CopyAction)
            event.accept()
        else:
            self.windowDropPreview = None
            self.inactiveOpeningPreview = None
            event.ignore()
        self.update()

    def dragLeaveEvent(self, event):
        self.counterPreview = None
        self.arrowPreview = None
        self.labelPreview = None
        self.furnishingPreview = None
        self.doorOrientationLocked = False
        self.alignmentGuides = []
        self.hoverPosition = None
        self.windowDropPreview = None
        self.inactiveOpeningPreview = None
        self.update()
        event.accept()

    def dropEvent(self, event):
        if self.exportOverlay.active:
            event.ignore()
            return
        if event.mimeData().hasFormat("application/x-planner-fireplace"):
            if self.exportOverlay.active or self.guiDragCancelled:
                event.ignore()
                return
            self.windowDropPreview = None
            obj = (self.FindFireplacePlacement(event.position(), event.modifiers())
                   if self.DrawingRect().contains(event.position()) else None)
            self.inactiveOpeningPreview = None
            if obj is not None:
                before = self.CaptureState()
                self.windows.append(obj)
                self.SetSelection([(obj, None)])
                self.RecordEdit(before)
                self.setFocus()
                event.acceptProposedAction()
            else:
                event.ignore()
            self.alignmentGuides = []
            self.update()
            return
        if self.guiDragCancelled:
            event.ignore()
            return
        if any(event.mimeData().hasFormat("application/x-planner-" + kind) for kind in ("arrow", "measurement-guide", "boundary-line", "angle-guide", "railing", "pillar", "column", "elevator")):
            self.arrowPreview = None
            if self.DrawingRect().contains(event.position()):
                before = self.CaptureState()
                arrow = self.FindArrowPlacement(event.position(), event.modifiers(),
                    Elevator if event.mimeData().hasFormat("application/x-planner-elevator") else
                    Column if event.mimeData().hasFormat("application/x-planner-column") else
                    Pillar if event.mimeData().hasFormat("application/x-planner-pillar") else
                    Railing if event.mimeData().hasFormat("application/x-planner-railing") else
                    AngleGuide if event.mimeData().hasFormat("application/x-planner-angle-guide") else
                    BoundaryLine if event.mimeData().hasFormat("application/x-planner-boundary-line") else
                    MeasurementGuide if event.mimeData().hasFormat("application/x-planner-measurement-guide") else Arrow)
                if isinstance(arrow, (Railing, Pillar)) and not self.WallFits(arrow):
                    self.alignmentGuides = []
                    self.update()
                    event.ignore()
                    return
                self.walls.append(arrow)
                self.SetSelection([(arrow, None)])
                self.RecordEdit(before)
                self.setFocus()
                event.acceptProposedAction()
            else:
                event.ignore()
            self.alignmentGuides = []
            self.update()
            return
        if event.mimeData().hasFormat("application/x-planner-counter"):
            self.counterPreview = None
            self.arrowPreview = None
            if self.DrawingRect().contains(event.position()):
                counter = self.FindCounterPlacement(event.position(), event.modifiers())
                if self.CounterFits(counter):
                    before = self.CaptureState()
                    self.walls.append(counter)
                    self.PropagateMiter(counter, 0)
                    self.PropagateMiter(counter, 1)
                    self.SetSelection([(counter, None)])
                    self.RecordEdit(before)
                    self.setFocus()
                    event.acceptProposedAction()
                else:
                    event.ignore()
            else:
                event.ignore()
            self.alignmentGuides = []
            self.update()
            return
        if event.mimeData().hasFormat("application/x-planner-north-arrow"):
            self.furnishingPreview = None
            if self.DrawingRect().contains(event.position()):
                before = self.CaptureState()
                center = self.SnapPosition(self.ViewportToWorld(event.position()), event.modifiers())
                obj = NorthArrow(center)
                self.furnishings.append(obj)
                self.SetSelection([(obj, None)])
                self.RecordEdit(before)
                self.setFocus()
                event.acceptProposedAction()
            else:
                event.ignore()
            self.alignmentGuides = []
            self.update()
            return
        if event.mimeData().hasFormat("application/x-planner-label"):
            self.labelPreview = None
            if self.DrawingRect().contains(event.position()):
                before = self.CaptureState()
                origin = self.SnapPosition(self.ViewportToWorld(event.position()), event.modifiers())
                label = Label(origin)
                self.labels.append(label)
                self.SetSelection([(label, None)])
                self.RecordEdit(before)
                self.setFocus()
                event.acceptProposedAction()
            else:
                event.ignore()
            self.alignmentGuides = []
            self.update()
            return
        if event.mimeData().hasFormat("application/x-planner-furnishing"):
            key = bytes(event.mimeData().data("application/x-planner-furnishing")).decode()
            self.furnishingPreview = None
            if key in self.furnishingDefinitions and self.DrawingRect().contains(event.position()):
                obj = self.FindFurnishingPlacement(event.position(), self.furnishingDefinitions[key], event.modifiers())
                if self.FurnishingFits(obj):
                    before = self.CaptureState()
                    self.furnishings.append(obj)
                    self.SetSelection([(obj, None)])
                    self.RecordEdit(before)
                    self.setFocus()
                    event.acceptProposedAction()
                else:
                    event.ignore()
            else:
                event.ignore()
            self.alignmentGuides = []
            self.update()
            return
        if event.mimeData().hasFormat("application/x-planner-stair"):
            self.windowDropPreview = None
            self.inactiveOpeningPreview = None
            self.doorOrientationLocked = False
            if self.PlaceStair(event.position(), event.modifiers()) is not None:
                event.setDropAction(QtCore.Qt.DropAction.CopyAction)
                event.accept()
            else:
                event.ignore()
            self.alignmentGuides = []
            self.update()
            return
        placement = self.windowDropPreview if self.doorOrientationLocked else None
        if isinstance(placement, Window):
            self.OrientDoor(placement, event.position())
        self.doorOrientationLocked = False
        self.windowDropPreview = None
        self.inactiveOpeningPreview = None
        openingType = (OpenDoorway if event.mimeData().hasFormat("application/x-planner-open-doorway") else
                       BifoldDoor if event.mimeData().hasFormat("application/x-planner-bifold-door") else
                       BarnDoor if event.mimeData().hasFormat("application/x-planner-barn-door") else
                       PocketDoor if event.mimeData().hasFormat("application/x-planner-pocket-door") else
                       SlidingDoor if event.mimeData().hasFormat("application/x-planner-sliding-door") else
                       Door if event.mimeData().hasFormat("application/x-planner-door") else
                       SilledWindow if event.mimeData().hasFormat("application/x-planner-silled-window") else
                       CasementWindow if event.mimeData().hasFormat("application/x-planner-casement-window") else Window)
        if (any(event.mimeData().hasFormat(f"application/x-planner-{kind}") for kind in ("window", "silled-window", "casement-window", "door", "sliding-door", "pocket-door", "barn-door", "bifold-door", "open-doorway"))
                and self.PlaceWindow(event.position(), openingType, event.modifiers(), placement) is not None):
            event.setDropAction(QtCore.Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()
        self.alignmentGuides = []
        self.update()
