"""Selection, connected objects, group movement and undo/redo history."""

import math
import time
from planner_app.object_schema import openingFields
from planner_app.geometry.attachments import AttachedVertexIndices, ConnectedAttachments
from planner_app.geometry.editing import TransformPoint, OpeningTransformTarget, ReattachTransformedOpening, RebaseMergedOpening, ChooseWallSplit
from planner_app.geometry.group_movement import (ProjectGroupTravel, GroupOpeningLimits,
    BoundGroupTravel, TranslatedOpeningFraction, AttachedConstraintPoint)
from .geometry import CollisionPass
from planner_app.history_edits import SceneEdit
from planner_app.furnishing_parts import FurnishingParts
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import (
    Door, Furnishing, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, SlidingDoor, MeasurementGuide, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, Window, Fireplace, objectIdCounter,
)


def SnapshotPointMatches(point, x, y):
    pointX, pointY = point.x(), point.y()
    if pointX != x or pointY != y:
        return False
    # Signed zero can affect angle calculations; retain snapshot signs as well.
    return ((x != 0 or math.copysign(1, pointX) == math.copysign(1, x))
            and (y != 0 or math.copysign(1, pointY) == math.copysign(1, y)))


class SceneEditingMixin:
    def NudgeSelection(self, key, duplicate = False):
        if (self.exportOverlay.active or not self.SelectionEntries() or self.dragStart is not None
                or self.pendingWall is not None or self.openingPlacementMode is not None or self.guiDragActive):
            return
        step = self.GridSteps()[1]
        delta = {QtCore.Qt.Key.Key_Left: QtCore.QPointF(-step, 0),
                 QtCore.Qt.Key.Key_Right: QtCore.QPointF(step, 0),
                 QtCore.Qt.Key.Key_Up: QtCore.QPointF(0, step),
                 QtCore.Qt.Key.Key_Down: QtCore.QPointF(0, -step)}[key]
        pivot = QtCore.QPointF(self.rotationPivot) if self.rotationPivot is not None else None
        rotationObject = self.furnishingRotationObject
        snapEnabled, controlHeld = self.snapEnabled, self.controlHeld
        try:
            # Reuse drag duplication, connected-object movement and validation,
            # without resnapping the requested displacement to a nearby object.
            self.snapEnabled, self.controlHeld = False, False
            self.interactionBefore = self.CaptureState()
            self.dragStart = self.DrawingRect().center()
            self.isDragging = True
            self.StartGroupDrag()
            position = self.WorldToViewport(self.ViewportToWorld(self.dragStart) + delta)
            modifiers = QtCore.Qt.KeyboardModifier.ShiftModifier if duplicate else QtCore.Qt.KeyboardModifier.NoModifier
            self.UpdateGroupDrag(position, modifiers)
            copies = list(self.dragCopies)
            event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonRelease, position,
                                     QtCore.QPointF(self.mapToGlobal(position.toPoint())),
                                     QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.NoButton, modifiers)
            self.mouseReleaseEvent(event)
            if pivot is not None:
                self.rotationPivot = pivot
            if duplicate and copies and any(obj is self.selectedWall for obj in copies) and rotationObject is not None:
                self.furnishingRotationObject = self.selectedWall
        finally:
            self.snapEnabled, self.controlHeld = snapEnabled, controlHeld

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
        radians = math.radians(angle % 360)
        cosine, sine = math.cos(radians), math.sin(radians)
        vertices = {}
        openingTargets = []
        for obj in objects:
            origin = (obj.firstVertex + obj.secondVertex) / 2 if localOrigins else sharedOrigin
            if isinstance(obj, Window):
                target, targetDirection = OpeningTransformTarget((obj.firstVertex.x(), obj.firstVertex.y()),
                    (obj.secondVertex.x(), obj.secondVertex.y()), (origin.x(), origin.y()), (x, y), cosine, sine)
                openingTargets.append((obj, target, targetDirection))
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
            target = QtCore.QPointF(*TransformPoint((vertex.x(), vertex.y()), (origin.x(), origin.y()), (x, y), cosine, sine))
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
            placement = ReattachTransformedOpening(target, targetDirection, (parent.firstVertex.x(), parent.firstVertex.y()),
                                                    (parent.secondVertex.x(), parent.secondVertex.y()))
            if placement is None:
                self.RestoreState(before)
                return "Doors and windows must stay on their wall. Select the wall to move or rotate them together."
            opening.centerFraction, flipped = placement
            if flipped:
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
        first, second = selectedWall.firstVertex, selectedWall.secondVertex
        vertices = [(obj, index, vertex) for obj in candidates
                    if obj is not selectedWall and not isinstance(obj, Pillar) and type(obj) is type(selectedWall)
                    for index, vertex in enumerate((obj.firstVertex, obj.secondVertex))]
        indices = AttachedVertexIndices((first.x(), first.y()), (second.x(), second.y()), selectedWall.width,
            [(vertex.x(), vertex.y()) for obj, index, vertex in vertices],
            (anchor.x(), anchor.y()) if anchor is not None else None)
        attachments = [(vertices[index][0], vertices[index][1], QtCore.QPointF(vertices[index][2])) for index in indices]
        if not wholeObjects:
            return attachments
        directAttachments = attachments
        contacts = (lambda first, second: paths[first].intersects(paths[second])) if type(selectedWall) in (Wall, Pillar, Column, Furnishing) else None
        candidateData = [(id(obj), (obj.firstVertex.x(), obj.firstVertex.y()),
                          (obj.secondVertex.x(), obj.secondVertex.y())) for obj in candidates]
        connected = ConnectedAttachments((id(selectedWall), (first.x(), first.y()), (second.x(), second.y())),
                                         candidateData, contacts)
        objectsById = {id(obj): obj for obj in candidates}
        attachments = [(objectsById[key], index, QtCore.QPointF(vertex)) for key in connected
                       for index, vertex in enumerate((objectsById[key].firstVertex, objectsById[key].secondVertex))]
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
        if self.selectedVertex is None and isinstance(self.selectedWall, Pillar):
            return []
        entries = (self.dragAttachments if self.selectedVertex is not None else
                   [entry for entry in self.dragAttachments if type(entry[0]) is type(self.selectedWall)])
        first, second = self.dragVertices
        anchor = self.dragVertices[self.selectedVertex] if self.selectedVertex is not None else None
        indices = AttachedVertexIndices((first.x(), first.y()), (second.x(), second.y()), self.selectedWall.width,
            [(vertex.x(), vertex.y()) for obj, index, vertex in entries],
            (anchor.x(), anchor.y()) if anchor is not None else None)
        return [entries[index] for index in indices]

    def EnsureObjectIds(self, capturedState = None):
        # Committed objects, including deletions, need IDs. Placement previews do not.
        objects = self.walls + self.windows + self.furnishings + self.labels
        if capturedState is not None:
            objects = objects + [entry[0] for category in (0, 3, 5, 8) for entry in capturedState[category]]
        pending = {id(obj): obj for obj in objects if obj.objectId is None}
        if pending:
            usedIds = {obj.objectId for obj in objects if obj.objectId is not None}
            # Loaded IDs can be ahead of the process counter. Retired objects
            # must keep their IDs reserved until they leave both history stacks.
            usedIds.update(entry[0].objectId for edit in self.undoHistory + self.redoHistory
                           for change in edit.changes for entry in change[3:] if entry is not None)
            for drawingObject in pending.values():
                objectId = next(objectIdCounter)
                while objectId in usedIds:
                    objectId = next(objectIdCounter)
                drawingObject.objectId = objectId
                usedIds.add(objectId)
        stairs = [wall for wall in self.walls if isinstance(wall, Stair)]
        for drawingObject in self.walls + self.windows + self.furnishings + self.labels:
            if isinstance(drawingObject, Stair):
                drawingObject.sceneStairs = stairs
                drawingObject.stepSizeBounds = (self.stairStepSizes["minimum"] * 10, self.stairStepSizes["maximum"] * 10)
            if isinstance(drawingObject, Railing):
                drawingObject.spacingBounds = tuple(self.railingSpacings[key] * 10 for key in ("minimum", "maximum", "target"))

    def SelectionEntries(self):
        if self.selectedWall is None:
            return []
        changes = self.renderChanges
        membershipKey = (changes.topology, changes.visibility)
        cached = getattr(self, "selectionMembership", None)
        if cached is None or cached[0] != membershipKey:
            sceneIds = {id(obj) for obj in self.walls + self.windows + self.furnishings + self.labels} - self.hiddenObjectIds
            self.selectionMembership = (membershipKey, sceneIds)
        else:
            sceneIds = cached[1]
        entries = [(obj, index) for obj, index in self.selection if id(obj) in sceneIds]
        if self.selectedWall is None or id(self.selectedWall) not in sceneIds:
            return []
        if any(obj is self.selectedWall and index == self.selectedVertex for obj, index in entries):
            return entries
        return [(self.selectedWall, self.selectedVertex)]

    def SetSelection(self, entries, notify = True):
        if self.exportOverlay.active:
            entries = []
        previousSelection = {(id(obj), index) for obj, index in self.selection}
        unique = {}
        for obj, index in self.ExpandGroupedSelection(entries):
            unique[(id(obj), index)] = (obj, index)
        self.selection = list(unique.values())
        self.selectedWall, self.selectedVertex = self.selection[-1] if self.selection else (None, None)
        if previousSelection != set(unique):
            self.rotationPivot = None
        if not any(obj is self.furnishingRotationObject for obj, index in self.selection):
            self.furnishingRotationObject = None
        if notify:
            self.selectionChanged.emit()
            self.update()

    def DeselectAll(self):
        self.CancelInteraction()
        self.SetSelection([])

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
            obj = state[0]
            # QPointF equality is fuzzy; restoration must compare exact coordinates.
            if not SnapshotPointMatches(obj.firstVertex, state[1], state[2]):
                obj.firstVertex = QtCore.QPointF(state[1], state[2])
            if not SnapshotPointMatches(obj.secondVertex, state[3], state[4]):
                obj.secondVertex = QtCore.QPointF(state[3], state[4])
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

    @CollisionPass
    def GroupOpeningsFit(self, openings):
        # All positions are final for this preview. Share read-only collision
        # preparation here, never across the preceding model assignments or
        # SetOpeningVertex calls, which may move/restore an opening themselves.
        with self.OpeningCandidatePass(len(openings)):
            for opening, index in openings:
                if not (self.OpeningFits(opening) and opening.firstFraction >= 0 and opening.secondFraction <= 1):
                    return False
        return True

    def CaptureState(self):
        walls = tuple((wall, wall.firstVertex.x(), wall.firstVertex.y(),
                       wall.secondVertex.x(), wall.secondVertex.y(), wall.width,
                       wall.firstMiter, wall.secondMiter, wall.material,
                       (wall.autosize, wall.manualPostCount) if isinstance(wall, Railing) else (wall.autosize, wall.manualStepCount) if isinstance(wall, Stair) else None,
                       (wall.solidTip, wall.tipSize, wall.intensity) if isinstance(wall, Arrow) else wall.directionReversed if isinstance(wall, Stair) else None,
                       wall.measurementHidden) for wall in self.walls)
        windows = tuple((window, window.parentWall, window.centerFraction, window.length,
                         window.hingeAtSecond if isinstance(window, (Door, SlidingDoor, PocketDoor, CasementWindow)) else None,
                         window.swingsOutwards if type(window) in (Window, Door, SilledWindow, CasementWindow, BarnDoor, BifoldDoor, Fireplace) else
                         window.panelsFlipped if isinstance(window, SlidingDoor) else None,
                         window.sillDepth if isinstance(window, SilledWindow) else (window.depth, window.depthOffset, window.material) if isinstance(window, Fireplace) else None,
                         window.measurementFlipped, window.measurementHidden) for window in self.windows)
        furnishings = tuple((obj, QtCore.QPointF(obj.firstVertex), QtCore.QPointF(obj.secondVertex), obj.width,
                            obj.behindCounters, obj.measurementHidden) for obj in self.furnishings)
        return (walls, self.selectedWall, self.selectedVertex, windows, tuple(self.SelectionEntries()), furnishings,
                tuple(self.objectGroups), tuple(self.hiddenObjects),
                tuple((obj, QtCore.QPointF(obj.firstVertex), QtCore.QPointF(obj.secondVertex), obj.width, obj.text, obj.intensity, obj.measurementHidden) for obj in self.labels))

    def RecordEdit(self, before, coalesceKey = None):
        self.EnsureObjectIds(before)
        self.PruneObjectGroups()
        for stair in self.walls:
            if isinstance(stair, Stair) and not stair.autosize:
                stair.manualStepCount = stair.stepCount
        sceneIds = {id(obj) for obj in self.walls + self.windows + self.furnishings + self.labels}
        if before is not None:
            for entry in before[0]:
                if isinstance(entry[0], Stair) and id(entry[0]) not in sceneIds:
                    # Detached stairs must not retain the rest of their old scene.
                    # Restoring them rebuilds these layout links in EnsureObjectIds.
                    entry[0].sceneStairs = []
        self.hiddenObjects = [obj for obj in self.hiddenObjects if id(obj) in sceneIds]
        self.hiddenObjectIds = {id(obj) for obj in self.hiddenObjects}
        after = self.CaptureState()
        edit = SceneEdit.Between(before, after) if before is not None else None
        if edit is not None:
            now = time.monotonic()
            if (coalesceKey is not None and coalesceKey == getattr(self, "historyCoalesceKey", None)
                    and now - getattr(self, "historyCoalesceTime", 0) <= 1.0 and self.undoHistory
                    and getattr(self, "historyCoalesceRevision", None) == self.sceneRevision):
                original = self.undoHistory[-1].Apply(before, False, validate = True)
                self.undoHistory.pop()
                edit = SceneEdit.Between(original, after)
            if edit is not None:
                self.undoHistory.append(edit)
            self.historyCoalesceKey, self.historyCoalesceTime = coalesceKey, now
            self.redoHistory.clear()
            # Strict count and retained-payload bounds. An oversized single edit
            # cannot retain an unbounded scene through deleted model references.
            totalBytes = sum(item.byteSize for item in self.undoHistory)
            while self.undoHistory and (len(self.undoHistory) > self.historyLimit or totalBytes > self.historyByteBudget):
                totalBytes -= self.undoHistory.pop(0).byteSize
            self.sceneRevision += 1
            self.historyCoalesceRevision = self.sceneRevision
            self.sceneChanged.emit()

    def RestoreState(self, state):
        self.CancelInteraction()
        previousStairs = [obj for obj in self.walls if isinstance(obj, Stair)]
        walls, self.selectedWall, self.selectedVertex, windows = state[:4]
        self.selection = list(state[4]) if len(state) > 4 else []
        self.objectGroups = list(state[6]) if len(state) > 6 else []
        self.hiddenObjects = list(state[7]) if len(state) > 7 else []
        self.hiddenObjectIds = {id(obj) for obj in self.hiddenObjects}
        self.walls = []
        for wall, firstX, firstY, secondX, secondY, width, firstMiter, secondMiter, material, stepCount, directionReversed, measurementHidden in walls:
            wall.measurementHidden = measurementHidden
            wall.firstVertex = QtCore.QPointF(firstX, firstY)
            wall.secondVertex = QtCore.QPointF(secondX, secondY)
            wall.width = width
            wall.firstMiter = firstMiter
            wall.secondMiter = secondMiter
            wall.material = material
            if isinstance(wall, Arrow):
                wall.solidTip, wall.tipSize, wall.intensity = directionReversed
            if isinstance(wall, Railing):
                wall.autosize, wall.manualPostCount = stepCount
            if isinstance(wall, Stair):
                wall.directionReversed = directionReversed
                if isinstance(stepCount, tuple):
                    wall.autosize, wall.manualStepCount = stepCount
            self.walls.append(wall)
        self.RestoreFurnishingStates(state[5] if len(state) > 5 else ())
        self.RestoreLabelStates(state[8] if len(state) > 8 else ())
        self.windows = []
        self.RestoreOpeningStates(windows)
        for openingState in windows:
            self.windows.append(openingState[0])
        if self.exportOverlay.active:
            self.SetSelection([], notify = False)
        restoredIds = {id(obj) for obj in self.walls}
        for stair in previousStairs:
            if id(stair) not in restoredIds:
                stair.sceneStairs = []
        self.EnsureObjectIds()
        self.sceneRevision += 1
        self.sceneChanged.emit()
        self.selectionChanged.emit()
        self.update()

    def RestoreOpeningStates(self, windows):
        for openingState in windows:
            window, parentWall, centerFraction, length, hingeAtSecond, swingsOutwards, sillDepth = openingState[:7]
            # Fireplace setters also normalize stored depth/offset against the
            # restored parent. Always run those, even when visible values match.
            if (not isinstance(window, Fireplace) and window.parentWall is parentWall
                    and centerFraction != 0 and window.centerFraction == centerFraction and window.length == length
                    and window.measurementFlipped == (openingState[7] if len(openingState) > 7 else False)
                    and window.measurementHidden == (openingState[8] if len(openingState) > 8 else False)
                    and (not isinstance(window, SilledWindow) or window.sillDepth == sillDepth)
                    and (not isinstance(window, (Door, SlidingDoor, PocketDoor, CasementWindow))
                         or window.hingeAtSecond == hingeAtSecond)
                    and (type(window) not in (Window, Door, SilledWindow, CasementWindow, BarnDoor, BifoldDoor)
                         or window.swingsOutwards == swingsOutwards)
                    and (not isinstance(window, SlidingDoor) or window.panelsFlipped == swingsOutwards)):
                continue
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
            if (not SnapshotPointMatches(obj.firstVertex, first.x(), first.y())
                    or not SnapshotPointMatches(obj.secondVertex, second.x(), second.y())
                    or (obj.width, obj.text, obj.intensity, obj.measurementHidden) != (width, text, intensity, measurementHidden)):
                obj.measurementHidden = measurementHidden
                obj.firstVertex, obj.secondVertex = QtCore.QPointF(first), QtCore.QPointF(second)
                obj.width, obj.text = width, text
                obj.intensity = intensity
            if restoreList:
                self.labels.append(obj)

    def RestoreFurnishingStates(self, states, restoreList = True):
        if restoreList:
            self.furnishings = []
        for obj, first, second, width, behindCounters, measurementHidden in states:
            if (not SnapshotPointMatches(obj.firstVertex, first.x(), first.y())
                    or not SnapshotPointMatches(obj.secondVertex, second.x(), second.y())
                    or (obj.width, obj.behindCounters, obj.measurementHidden) != (width, behindCounters, measurementHidden)):
                obj.behindCounters = behindCounters
                obj.measurementHidden = measurementHidden
                obj.firstVertex = QtCore.QPointF(first)
                obj.secondVertex = QtCore.QPointF(second)
                obj.width = width
            if restoreList:
                self.furnishings.append(obj)

    def Undo(self):
        if self.exportOverlay.active:
            self.window().exportPanel.UndoExport()
            return
        self.historyCoalesceKey = None
        self.CancelInteraction()
        if self.undoHistory:
            edit = self.undoHistory.pop()
            self.RestoreState(edit.Apply(self.CaptureState(), False))
            self.redoHistory.append(edit)

    def Redo(self):
        if self.exportOverlay.active:
            self.window().exportPanel.RedoExport()
            return
        self.historyCoalesceKey = None
        self.CancelInteraction()
        if self.redoHistory:
            edit = self.redoHistory.pop()
            self.RestoreState(edit.Apply(self.CaptureState(), True))
            self.undoHistory.append(edit)

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
            oldDirection = opening.parentWall.secondVertex - opening.parentWall.firstVertex
            fraction, fits, flipped = RebaseMergedOpening((center.x(), center.y()), (oldDirection.x(), oldDirection.y()),
                (first.x(), first.y()), (direction.x(), direction.y()), length, clone.length)
            clone.centerFraction = fraction
            if not fits:
                self.clipboardMessage.emit("Cannot dissolve: an opening would not fit the new wall.")
                return False
            if flipped:
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
            direction = wall.secondVertex - wall.firstVertex
            fraction = ChooseWallSplit((wall.firstVertex.x(), wall.firstVertex.y()), (direction.x(), direction.y()),
                (self.NumericCollisionFootprint(other, self.ObjectFootprint(other))
                 for other in self.walls + self.furnishings if other is not wall),
                ((opening.firstFraction, opening.secondFraction) for opening in self.windows if opening.parentWall is wall))
            if fraction is None:
                self.clipboardMessage.emit("Cannot subdivide: no clear wall segment is available.")
                return False
            splitFractions[id(wall)] = fraction
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

    def DeleteSelected(self):
        self.CancelInteraction()
        if self.selectedWall is not None:
            before = self.CaptureState()
            removed = {id(wall) for wall, index in self.SelectionEntries()}
            self.furnishings = [obj for obj in self.furnishings if id(obj) not in removed]
            self.labels = [obj for obj in self.labels if id(obj) not in removed]
            self.walls = [wall for wall in self.walls if id(wall) not in removed]
            self.windows = [window for window in self.windows
                            if id(window) not in removed and id(window.parentWall) not in removed]
            self.selectedWall = None
            self.selectedVertex = None
            self.selection = []
            self.RecordEdit(before)
            self.selectionChanged.emit()
            self.update()

    def CloneOpening(self, source, parent):
        opening = type(source)(parent, source.firstFraction, source.secondFraction)
        opening.centerFraction = source.centerFraction
        opening.length = source.length
        for name in openingFields[type(source)]:
            setattr(opening, name, getattr(source, name))
        opening.measurementHidden = source.measurementHidden
        opening.geometryIssues = getattr(source, "geometryIssues", ())
        return opening

    def DecomposeFurnishings(self, objects):
        self.CancelInteraction()
        before = self.CaptureState()
        selectedIds = {id(obj) for obj in objects if type(obj) is Furnishing}
        replacements = {}
        for parent in self.furnishings:
            components = parent.definition.get("components")
            if id(parent) not in selectedIds or not components:
                continue
            replacements[id(parent)] = FurnishingParts(parent)
        if not replacements:
            return False
        self.furnishings = [part for obj in self.furnishings for part in replacements.get(id(obj), (obj,))]
        self.objectGroups = [tuple(part for obj in group for part in replacements.get(id(obj), (obj,)))
                             for group in self.objectGroups]
        self.hiddenObjects = [part for obj in self.hiddenObjects for part in replacements.get(id(obj), (obj,))]
        self.hiddenObjectIds = {id(obj) for obj in self.hiddenObjects}
        self.SetSelection([(part, None) for obj in objects for part in replacements.get(id(obj), (obj,))])
        self.RecordEdit(before)
        self.selectionChanged.emit()
        self.update()
        return True

    def MoveFurnishingLayer(self, furnishing, toFront):
        objects = furnishing if isinstance(furnishing, list) else [furnishing]
        objectIds = {id(obj) for obj in objects}
        moved = [obj for obj in self.furnishings if id(obj) in objectIds]
        if not moved:
            return
        before = self.CaptureState()
        remaining = [obj for obj in self.furnishings if id(obj) not in objectIds]
        for obj in moved:
            obj.behindCounters = not toFront
        self.furnishings = remaining + moved if toFront else moved + remaining
        self.RecordEdit(before)
        self.update()
