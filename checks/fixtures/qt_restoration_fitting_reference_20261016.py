from planner_app.viewport.geometry import CollisionPass
import math
from PySide6 import QtCore, QtWidgets
from planner_app.geometry.attachments import FitOpeningCenters
from planner_app.geometry.group_movement import (ProjectGroupTravel, GroupOpeningLimits, BoundGroupTravel, TranslatedOpeningFraction, AttachedConstraintPoint)
from planner_app.models import *

class ReferenceRestorationFitting:
    def UpdateGroupDrag(self, position, modifiers):
        if self.controlHeld:
            modifiers |= QtCore.Qt.KeyboardModifier.ControlModifier
        if (position - self.dragStart).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
            self.isDragging = True
        if not self.isDragging:
            return
        before = self.interactionBefore
        for state in before[0]:
            state[0].firstVertex = QtCore.QPointF(state[1], state[2])
            state[0].secondVertex = QtCore.QPointF(state[3], state[4])
        self.RestoreOpeningStates(before[3])
        self.RestoreFurnishingStates(before[5], restoreList = False)
        self.RestoreLabelStates(before[8], restoreList = False)
        connectionKey = (self.connectedEnabled, self.connectedVerticesEnabled, self.connectedObjectsEnabled)
        if not self.dragCopies and connectionKey != self.groupConnectionKey:
            self.StartGroupDrag()
        duplicate = all(index is None for obj, index in self.groupSourceEntries) and bool(
            modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)
        if duplicate != bool(self.dragCopies):
            self.walls = [obj for obj in self.walls if not any(obj is copy for copy in self.dragCopies)]
            self.windows = [obj for obj in self.windows if not any(obj is copy for copy in self.dragCopies)]
            self.furnishings = [obj for obj in self.furnishings if not any(obj is copy for copy in self.dragCopies)]
            self.labels = [obj for obj in self.labels if not any(obj is copy for copy in self.dragCopies)]
            self.dragCopies = []
            self.objectGroups = list(before[6])
            if duplicate:
                copies = {}
                for obj, index in self.groupSourceEntries:
                    if isinstance(obj, Label):
                        copy = obj.Clone()
                        copies[id(obj)] = copy
                        self.labels.append(copy)
                        self.dragCopies.append(copy)
                    elif isinstance(obj, Furnishing):
                        copy = obj.Clone()
                        copies[id(obj)] = copy
                        self.furnishings.append(copy)
                        self.dragCopies.append(copy)
                    elif isinstance(obj, Wall):
                        copy = type(obj)(QtCore.QPointF(obj.firstVertex), QtCore.QPointF(obj.secondVertex), obj.width,
                                         obj.firstMiter, obj.secondMiter, obj.material)
                        copy.measurementHidden = obj.measurementHidden
                        if isinstance(obj, Arrow):
                            copy.solidTip, copy.tipSize, copy.intensity = obj.solidTip, obj.tipSize, obj.intensity
                        if isinstance(obj, Railing):
                            copy.autosize, copy.manualPostCount = obj.autosize, obj.manualPostCount
                            copy.spacingBounds = obj.spacingBounds
                        if isinstance(obj, Stair):
                            copy.directionReversed = obj.directionReversed
                            copy.autosize, copy.manualStepCount = obj.autosize, obj.manualStepCount
                        copies[id(obj)] = copy
                        self.walls.append(copy)
                        self.dragCopies.append(copy)
                for opening in list(self.windows):
                    if id(opening.parentWall) in copies or any(obj is opening for obj, index in self.groupSourceEntries):
                        copy = self.CloneOpening(opening, copies.get(id(opening.parentWall), opening.parentWall))
                        copies[id(opening)] = copy
                        self.windows.append(copy)
                        self.dragCopies.append(copy)
                for group in before[6]:
                    members = tuple(copies[id(obj)] for obj in group if id(obj) in copies)
                    if len(members) >= 2:
                        self.objectGroups.append(members)
                self.SetSelection([(copies[id(obj)], index) for obj, index in self.groupSourceEntries])
            else:
                self.SetSelection(self.groupSourceEntries)
            self.StartGroupDrag()
        self.RestoreOpeningStates(self.groupOpeningStates)
        delta = self.ViewportToWorld(position) - self.ViewportToWorld(self.dragStart)
        movingIds = {id(obj) for obj, index, vertex in self.groupMovedVertices}
        movingIds.update(id(obj) for obj, index in self.groupMovedOpenings)
        fixedOpenings = [(obj, index) for obj, index in self.groupMovedOpenings if id(obj.parentWall) not in movingIds]
        # Openings on fixed walls constrain the common group translation to
        # their wall axis. Nonparallel fixed parents have no shared travel axis.
        parentGeometry = {}
        for opening, index in fixedOpenings:
            parent = opening.parentWall
            if id(parent) not in parentGeometry:
                direction = parent.secondVertex - parent.firstVertex
                parentGeometry[id(parent)] = ((direction.x(), direction.y()), math.hypot(direction.x(), direction.y()))
        numericDelta, numericTravel, travelBlocked = ProjectGroupTravel((delta.x(), delta.y()),
            (parentGeometry[id(opening.parentWall)][0] for opening, index in fixedOpenings))
        delta = QtCore.QPointF(*numericDelta)
        travel = QtCore.QPointF(*numericTravel) if numericTravel is not None else None
        targets, anchors = [], []
        if self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            for obj in self.walls + self.windows + self.furnishings + self.labels:
                if not self.IsObjectVisible(obj) or id(obj) in movingIds or isinstance(obj, Window) and id(obj.parentWall) in movingIds:
                    continue
                targets.extend((obj.firstVertex, obj.secondVertex))
            anchors = [vertex for obj, index, vertex in self.groupMovedVertices]
            if any(isinstance(obj, Furnishing) for obj, index in self.groupEntries) or all(isinstance(obj, Wall) and index is None for obj, index in self.groupEntries):
                targets = self.StairSnapTargets() + list(self.SnapVertices())
                anchors = [anchor for obj, index in self.groupEntries
                           for anchor in self.ObjectCorners(obj) + [(obj.firstVertex + obj.secondVertex) / 2]]
                anchors.extend(vertex for obj, index, vertex in self.groupMovedVertices
                               if isinstance(obj, Wall) and not isinstance(obj, Pillar))
            for opening, index in fixedOpenings:
                anchors.extend(((opening.firstVertex, opening.secondVertex, (opening.firstVertex + opening.secondVertex) / 2)
                                if index is None else (opening.firstVertex if index == 0 else opening.secondVertex,)))
        if not travelBlocked:
            if (self.selectedVertex is not None and not isinstance(self.selectedWall, Window)
                    and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier):
                vertices = self.dragSourceVertices or self.dragVertices
                original = vertices[self.selectedVertex]
                target = self.SnapStairVertex(original + delta, vertices[1 - self.selectedVertex], self.selectedWall, modifiers)
                delta = target - original
            else:
                delta = self.SnapObjectMovement(anchors, delta, modifiers, snapTargets = targets, travelDirection = travel)
        openingStates = {id(state[0]): state for state in self.groupOpeningStates}
        if travel is not None and not travelBlocked:
            # Prepare stationary neighbours once, retaining their scene order.
            # Copies intentionally ignore these intervals until final validation.
            stationary = {}
            if not self.dragCopies:
                for other in self.windows:
                    parentId = id(other.parentWall)
                    if parentId in parentGeometry and id(other) not in movingIds:
                        stationary.setdefault(parentId, []).append((other.centerFraction, other.firstFraction, other.secondFraction))
            limits = GroupOpeningLimits(numericTravel,
                ((id(opening.parentWall), *parentGeometry[id(opening.parentWall)],
                  openingStates[id(opening)][2], opening.length, index) for opening, index in fixedOpenings),
                stationary, bool(self.dragCopies))
            boundedDelta = QtCore.QPointF(*BoundGroupTravel((delta.x(), delta.y()), numericTravel, *limits))
            if QtCore.QLineF(delta, boundedDelta).length() > .01:
                self.alignmentGuides = []
                self.snapApplied = False
            delta = boundedDelta
        for obj, index, vertex in self.groupMovedVertices:
            if index == 0:
                obj.firstVertex = vertex + delta
            else:
                obj.secondVertex = vertex + delta
        selectedKeys = {(id(obj), vertexIndex) for obj, index in self.groupEntries
                        for vertexIndex in ((0, 1) if index is None else (index,))}
        for iteration in range(len(self.dragConstraints) + 1):
            for attached, index, parent, fraction, normalOffset in self.dragConstraints:
                if (id(attached), index) in selectedKeys:
                    continue
                first, second = parent.firstVertex, parent.secondVertex
                vertex = QtCore.QPointF(*AttachedConstraintPoint((first.x(), first.y()), (second.x(), second.y()),
                                                                fraction, normalOffset))
                if index == 0:
                    attached.firstVertex = vertex
                else:
                    attached.secondVertex = vertex
        for opening, index in fixedOpenings:
            parent = opening.parentWall
            direction = parent.secondVertex - parent.firstVertex
            lengthSquared = QtCore.QPointF.dotProduct(direction, direction)
            if lengthSquared <= 1e-10:
                continue
            if index is None:
                opening.centerFraction = TranslatedOpeningFraction(openingStates[id(opening)][2],
                    (delta.x(), delta.y()), (direction.x(), direction.y()))
            else:
                vertex = opening.firstVertex if index == 0 else opening.secondVertex
                self.SetOpeningVertex(opening, index, vertex + delta)
        if not fixedOpenings or self.GroupOpeningsFit(fixedOpenings):
            fixedIds = {id(obj) for obj, index in fixedOpenings}
            openingBefore = tuple((state[0], state[1], state[0].centerFraction, *state[3:])
                                  if id(state[0]) in fixedIds else state for state in before[3])
            # Preview painting validates moving furnishings; release validates the
            # entire scene. Repeating that collision pass here changes no geometry.
            self.FitWallOpenings((before[0], before[1], before[2], openingBefore), validateFurnishings = False, validateScene = False)
        self.selectionChanged.emit()
        self.update()


    def RestoreOpeningStates(self, windows):
        for openingState in windows:
            window, parentWall, centerFraction, length, hingeAtSecond, swingsOutwards, sillDepth = openingState[:7]
            window.measurementFlipped = openingState[7] if len(openingState) > 7 else False
            window.measurementHidden = openingState[8] if len(openingState) > 8 else False
            window.parentWall = parentWall
            window.centerFraction = centerFraction
            window.length = length
            if isinstance(window, SilledWindow):
                window.sillDepth = sillDepth
            if isinstance(window, Fireplace):
                window.depth, window.depthOffset, window.material = sillDepth
            if isinstance(window, (Door, SlidingDoor, PocketDoor, CasementWindow)):
                window.hingeAtSecond = hingeAtSecond
            if type(window) in (Window, Door, SilledWindow, CasementWindow, BarnDoor, BifoldDoor, Fireplace):
                window.swingsOutwards = swingsOutwards
            elif isinstance(window, SlidingDoor):
                window.panelsFlipped = swingsOutwards


    def RestoreLabelStates(self, states, restoreList = True):
        if restoreList:
            self.labels = []
        for obj, first, second, width, text, intensity, measurementHidden in states:
            obj.measurementHidden = measurementHidden
            obj.firstVertex, obj.secondVertex = QtCore.QPointF(first), QtCore.QPointF(second)
            obj.width, obj.text = width, text
            obj.intensity = intensity
            if restoreList:
                self.labels.append(obj)


    def RestoreFurnishingStates(self, states, restoreList = True):
        if restoreList:
            self.furnishings = []
        for obj, first, second, width, behindCounters, measurementHidden, flipHorizontal, flipVertical in states:
            obj.behindCounters = behindCounters
            obj.flipHorizontal, obj.flipVertical = flipHorizontal, flipVertical
            obj.measurementHidden = measurementHidden
            obj.firstVertex = QtCore.QPointF(first)
            obj.secondVertex = QtCore.QPointF(second)
            obj.width = width
            if restoreList:
                self.furnishings.append(obj)


    def MinimumOpeningLength(self, wall):
        lengths = [opening.length for opening in self.windows if opening.parentWall is wall]
        return sum(lengths)


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
        for wall in walls:
            length = QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
            minimumLength = self.MinimumOpeningLength(wall)
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

