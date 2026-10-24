"""Frozen pre-extraction group drag orchestration and constraints."""

import math

from PySide6 import QtCore, QtGui, QtWidgets

from planner_app.models import *

class ReferenceScene:

    def StartGroupDrag(self):
        self.groupConnectionKey = (self.connectedEnabled, self.connectedVerticesEnabled, self.connectedObjectsEnabled)
        if not self.groupDrag:
            self.groupSourceEntries = list(self.SelectionEntries())
        self.groupDrag = True
        self.groupEntries = list(self.SelectionEntries())
        vertices = {}
        openings = {}
        constraints = []
        wholeWallIds = {id(obj) for obj, index in self.groupEntries if isinstance(obj, Wall) and index is None}
        allWallsSelected = all(id(wall) in wholeWallIds for wall in self.walls)
        wholeOpenings = {id(obj) for obj, index in self.groupEntries if isinstance(obj, Window) and index is None}
        originalIndex = self.selectedVertex
        for obj, index in self.groupEntries:
            if isinstance(obj, Window):
                if index is not None and id(obj) in wholeOpenings:
                    continue
                openings[(id(obj), index)] = (obj, index)
                continue
            for vertexIndex in ((0, 1) if index is None else (index,)):
                vertex = obj.firstVertex if vertexIndex == 0 else obj.secondVertex
                vertices[(id(obj), vertexIndex)] = (obj, vertexIndex, QtCore.QPointF(vertex))
            if (self.connectedEnabled and (not allWallsSelected or type(obj) is Furnishing)
                    and not self.dragCopies and not isinstance(obj, Label)):
                if self.connectedObjectsEnabled and index is None:
                    self.selectedVertex = index
                    attachments = self.AttachedVertices(obj)
                    constraints.extend(self.dragConstraints)
                else:
                    attachments = []
                    if self.connectedVerticesEnabled:
                        self.selectedVertex = index
                        attachments = self.AttachedVertices(obj)
                for attached, vertexIndex, vertex in attachments:
                    vertices.setdefault((id(attached), vertexIndex), (attached, vertexIndex, vertex))
        self.selectedVertex = originalIndex
        self.groupMovedVertices = list(vertices.values())
        self.groupMovedOpenings = list(openings.values())
        self.dragConstraints = constraints
        self.dragAttachments = list(self.groupMovedVertices)
        self.groupOpeningStates = self.CaptureState()[3]

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
        travel = None
        travelBlocked = False
        for opening, index in fixedOpenings:
            direction = opening.parentWall.secondVertex - opening.parentWall.firstVertex
            length = math.hypot(direction.x(), direction.y())
            if length > 1e-10:
                direction /= length
                if travel is not None and abs(travel.x() * direction.y() - travel.y() * direction.x()) > 1e-6:
                    delta = QtCore.QPointF()
                    travelBlocked = True
                    break
                travel = direction
                delta = direction * QtCore.QPointF.dotProduct(delta, direction)
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
        if travel is not None and not travelBlocked:
            minimum, maximum = -float("inf"), float("inf")
            states = {id(state[0]): state for state in self.groupOpeningStates}
            for opening, index in fixedOpenings:
                if index is not None:
                    continue
                parent = opening.parentWall
                direction = parent.secondVertex - parent.firstVertex
                length = math.hypot(direction.x(), direction.y())
                sign = 1 if QtCore.QPointF.dotProduct(direction, travel) >= 0 else -1
                center = states[id(opening)][2] * length
                lower, upper = opening.length / 2 - center, length - opening.length / 2 - center
                for other in self.windows:
                    if other.parentWall is not parent or id(other) in movingIds:
                        continue
                    if self.dragCopies:
                        # Copies can be placed on either side of their sources.
                        # Validate the destination rather than trapping them in
                        # the source opening's initially overlapping interval.
                        continue
                    if other.centerFraction < states[id(opening)][2]:
                        lower = max(lower, other.secondFraction * length + opening.length / 2 - center)
                    else:
                        upper = min(upper, other.firstFraction * length - opening.length / 2 - center)
                if sign < 0:
                    lower, upper = -upper, -lower
                minimum, maximum = max(minimum, lower), min(maximum, upper)
            distance = QtCore.QPointF.dotProduct(delta, travel)
            boundedDelta = travel * (max(minimum, min(maximum, distance)) if minimum <= maximum else 0)
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
                direction = parent.secondVertex - parent.firstVertex
                length = math.hypot(direction.x(), direction.y())
                normal = QtCore.QPointF(-direction.y(), direction.x()) / length if length > 1e-10 else QtCore.QPointF()
                vertex = parent.firstVertex + direction * fraction + normal * normalOffset
                if index == 0:
                    attached.firstVertex = vertex
                else:
                    attached.secondVertex = vertex
        openingStates = {id(state[0]): state for state in self.groupOpeningStates}
        for opening, index in fixedOpenings:
            parent = opening.parentWall
            direction = parent.secondVertex - parent.firstVertex
            lengthSquared = QtCore.QPointF.dotProduct(direction, direction)
            if lengthSquared <= 1e-10:
                continue
            if index is None:
                opening.centerFraction = openingStates[id(opening)][2] + QtCore.QPointF.dotProduct(delta, direction) / lengthSquared
            else:
                vertex = opening.firstVertex if index == 0 else opening.secondVertex
                self.SetOpeningVertex(opening, index, vertex + delta)
        if all(self.OpeningFits(opening) and opening.firstFraction >= 0 and opening.secondFraction <= 1
               for opening, index in fixedOpenings):
            fixedIds = {id(obj) for obj, index in fixedOpenings}
            openingBefore = tuple((state[0], state[1], state[0].centerFraction, *state[3:])
                                  if id(state[0]) in fixedIds else state for state in before[3])
            # Preview painting validates moving furnishings; release validates the
            # entire scene. Repeating that collision pass here changes no geometry.
            self.FitWallOpenings((before[0], before[1], before[2], openingBefore), validateFurnishings = False, validateScene = False)
        self.selectionChanged.emit()
        self.update()
