"""Frozen group-drag baseline before dirty-object restoration."""
from planner_app.viewport.scene import *
from planner_app.viewport.scene import SceneEditingMixin as CurrentSceneEditingMixin
from planner_app.viewport.widget import DrawingViewport


class ReferenceSceneEditingMixin(CurrentSceneEditingMixin):
    def StartGroupDrag(self):
        self.groupConnectionKey = (self.connectedEnabled, self.connectedVerticesEnabled, self.connectedObjectsEnabled)
        if not self.groupDrag:
            self.groupSourceEntries = list(self.SelectionEntries())
        self.groupDrag = True
        self.groupEntries = list(self.SelectionEntries())
        self.groupGuideDepthAnchors = [point for obj, index in self.groupEntries if index is None and type(obj) is MeasurementGuide
                                      for point in self.GuideDepthEndpoints(obj)]
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
            indices = range(len(ObjectControlPoints(obj))) if index is None or isinstance(obj, MeasurementGuide) and index == 3 or isinstance(obj, AngleGuide) and index == 2 else (index,)
            for vertexIndex in indices:
                vertex = ObjectControlPoints(obj)[vertexIndex]
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
        self.groupOpeningStates = self.CaptureOpeningStates()

    def UpdateGroupDrag(self, position, modifiers):
        if self.controlHeld:
            modifiers |= QtCore.Qt.KeyboardModifier.ControlModifier
        if (position - self.dragStart).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
            self.isDragging = True
        if not self.isDragging:
            return
        self.groupOpeningPreviews = []
        self.inactiveOpeningPreview = None
        movementBefore = None
        if any(type(obj) is Wall for obj, index in self.groupEntries) and any(isinstance(opening, PocketDoor) for opening in self.windows):
            movedPoints = {(id(obj), index): (obj, index, QtCore.QPointF(ObjectControlPoints(obj)[index]))
                           for obj, index, original in self.groupMovedVertices}
            for obj, index, parent, fraction, normalOffset in self.dragConstraints:
                movedPoints.setdefault((id(obj), index), (obj, index, QtCore.QPointF(ObjectControlPoints(obj)[index])))
            movementBefore = tuple(movedPoints.values()), self.CaptureOpeningStates()
        before = self.interactionBefore
        for state in before[0]:
            obj = state[0]
            # QPointF equality is fuzzy; restoration must compare exact coordinates.
            if isinstance(obj, MeasurementGuide):
                obj.textOffset = QtCore.QPointF(*state[10][-2:])
            if isinstance(obj, AngleGuide):
                obj.middleVertex = QtCore.QPointF(*state[10][:2])
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
            modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier) and not self.ObjectsHaveAssetErrors(
                obj for obj, index in self.groupSourceEntries)
        if duplicate != bool(self.dragCopies):
            movementBefore = None  # A changed copy selection has no previous frame to restore.
            self.walls = [obj for obj in self.walls if not any(obj is copy for copy in self.dragCopies)]
            self.windows = [obj for obj in self.windows if not any(obj is copy for copy in self.dragCopies)]
            self.furnishings = [obj for obj in self.furnishings if not any(obj is copy for copy in self.dragCopies)]
            self.labels = [obj for obj in self.labels if not any(obj is copy for copy in self.dragCopies)]
            self.dragCopies = []
            self.objectGroups = list(before[6])
            if duplicate:
                copies = self.DuplicateSelectionObjects([obj for obj, index in self.groupSourceEntries], before[6])
                self.dragCopies = list(copies.values())
                self.SetSelection([(copies[id(obj)], index) for obj, index in self.groupSourceEntries])
            else:
                self.SetSelection(self.groupSourceEntries)
            self.StartGroupDrag()
        self.RestoreOpeningStates(self.groupOpeningStates)
        delta = self.ViewportToWorld(position) - self.ViewportToWorld(self.dragStart)
        if self.ReattachOpeningGroup(delta, modifiers):
            self.selectionChanged.emit()
            self.update()
            return
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
                targets.extend(ObjectControlPoints(obj))
                targets.extend(self.GuideDepthEndpoints(obj))
            anchors = [vertex for obj, index, vertex in self.groupMovedVertices if not isinstance(obj, AngleGuide)]
            if any(isinstance(obj, Furnishing) for obj, index in self.groupEntries) or all(isinstance(obj, Wall) and index is None for obj, index in self.groupEntries):
                targets = self.StairSnapTargets() + list(self.SnapVertices())
                anchors = [anchor for obj, index in self.groupEntries if not isinstance(obj, AngleGuide)
                           for anchor in self.ObjectCorners(obj) + [(obj.firstVertex + obj.secondVertex) / 2]]
                anchors.extend(vertex for obj, index, vertex in self.groupMovedVertices
                               if isinstance(obj, Wall) and not isinstance(obj, (Pillar, AngleGuide)))
            for opening, index in fixedOpenings:
                anchors.extend(((opening.firstVertex, opening.secondVertex, (opening.firstVertex + opening.secondVertex) / 2)
                                if index is None else (opening.firstVertex if index == 0 else opening.secondVertex,)))
            anchors.extend(self.groupGuideDepthAnchors)
        for obj, index in self.groupEntries:
            if isinstance(obj, AngleGuide):
                anchors.append(ObjectControlPoints(obj)[2 if index is None or index == 3 else index])
        if len(self.groupEntries) == 1 and isinstance(self.groupEntries[0][0], AngleGuide):
            obj, index = self.groupEntries[0]
            targets = self.StairSnapTargets(obj) + list(self.SnapVertices())
        if not travelBlocked:
            if (isinstance(self.selectedWall, AngleGuide) and self.selectedVertex in (0, 1)
                    and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier):
                original = ObjectControlPoints(self.selectedWall)[self.selectedVertex]
                target = self.SnapStairVertex(original + delta, self.selectedWall.middleVertex, self.selectedWall, modifiers)
                delta = target - original
            elif (self.selectedVertex is not None and not isinstance(self.selectedWall, (Window, AngleGuide))
                    and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier):
                vertices = self.dragSourceVertices or self.dragVertices
                original = vertices[self.selectedVertex]
                target = self.SnapStairVertex(original + delta, vertices[1 - self.selectedVertex], self.selectedWall, modifiers)
                delta = target - original
            else:
                delta = self.SnapObjectMovement(anchors, delta, modifiers, snapTargets = targets, travelDirection = travel)
                if isinstance(self.selectedWall, AngleGuide) and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
                    self.axisConstraintOrigin = QtCore.QPointF(self.selectedWall.middleVertex)
                    self.axisConstraintDirection = None
        openingStates = {id(state[0]): state for state in self.groupOpeningStates} if fixedOpenings else {}
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
                  openingStates[id(opening)][2], opening.length, index, self.OpeningTravelBounds(opening)) for opening, index in fixedOpenings),
                stationary, bool(self.dragCopies))
            boundedDelta = QtCore.QPointF(*BoundGroupTravel((delta.x(), delta.y()), numericTravel, *limits))
            if QtCore.QLineF(delta, boundedDelta).length() > .01:
                self.alignmentGuides = []
                self.snapApplied = False
            delta = boundedDelta
        for obj, index, vertex in self.groupMovedVertices:
            SetControlPoint(obj, index, vertex + delta)
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
        fitValid = not fixedOpenings or self.GroupOpeningsFit(fixedOpenings)
        if fitValid:
            fixedIds = {id(obj) for obj, index in fixedOpenings}
            openingBefore = (tuple((state[0], state[1], state[0].centerFraction, *state[3:])
                                  if id(state[0]) in fixedIds else state for state in before[3])
                             if fixedIds else before[3])
            # Preview painting validates moving furnishings; release validates the
            # entire scene. Repeating that collision pass here changes no geometry.
            fitValid = self.FitWallOpenings((before[0], before[1], before[2], openingBefore), validateFurnishings = False, validateScene = False)
        if not fitValid and movementBefore is not None:
            points, openings = movementBefore
            for obj, index, point in points:
                SetControlPoint(obj, index, point)
            self.RestoreOpeningStates(openings)
            self.alignmentGuides = []
            self.snapApplied = False
        self.selectionChanged.emit()
        self.update()


class ReferenceViewport(ReferenceSceneEditingMixin, DrawingViewport):
    pass
