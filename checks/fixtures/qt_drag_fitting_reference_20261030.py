"""Frozen drag rollback, group setup/update and opening fitting."""
from planner_app.viewport.scene import *
from planner_app.viewport.placement import *
from planner_app.viewport.interaction import *


class ReferenceScene:
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
        self.groupOpeningStates = self.CaptureState()[3]

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
            openingBefore = tuple((state[0], state[1], state[0].centerFraction, *state[3:])
                                  if id(state[0]) in fixedIds else state for state in before[3])
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


class ReferencePlacement:
    def FitWallOpenings(self, before = None, validateFurnishings = True, validateScene = True):
        followStretch = self.connectedEnabled and self.connectedObjectsEnabled
        oldWalls = {id(state[0]): state for state in before[0]} if before is not None else {}
        oldCenters = {id(state[0]): state[2] for state in before[3]} if before is not None else {}
        openingsByParent = {}
        for opening in self.windows:
            openingsByParent.setdefault(id(opening.parentWall), []).append(opening)
        for wall in self.walls:
            siblings = openingsByParent.get(id(wall), ())
            # Reserved halves follow their supporting wall faces, independently
            # of where a shared control point divides the collinear segments.
            parked = {id(opening) for opening in siblings if isinstance(opening, PocketDoor)}
            oldWall = oldWalls.get(id(wall))
            for opening in siblings:
                if id(opening) not in parked:
                    continue
                if oldWall is not None and (wall.firstVertex.x(), wall.firstVertex.y(), wall.secondVertex.x(), wall.secondVertex.y()) != oldWall[1:5]:
                    center = ReservedDoorEditCenter(oldWall[1:3], oldWall[3:5],
                        (wall.firstVertex.x(), wall.firstVertex.y()), (wall.secondVertex.x(), wall.secondVertex.y()),
                        oldCenters.get(id(opening), opening.centerFraction), followStretch)
                    if center is None:
                        return False
                    opening.centerFraction = center
                if not self.OpeningFits(opening):
                    return False
            openings = sorted((opening for opening in siblings if id(opening) not in parked), key = lambda opening: opening.centerFraction)
            if not openings:
                continue
            parentLength = QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
            remainingLength = sum(opening.length for opening in openings) if parked else sum(opening.length for opening in siblings)
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


class ReferenceInteraction:
    def UpdateInteraction(self, position, modifiers):
        self.axisConstraintOrigin = None
        self.axisConstraintDirection = None
        if self.guiDragActive and self.guiDragKind in ("wall-line", "wall-square", "wall-circle"):
            if self.hoverPosition is not None:
                mime = QtCore.QMimeData()
                mime.setData("application/x-planner-" + self.guiDragKind, self.guiDragKind.encode())
                event = QtGui.QDragMoveEvent(self.hoverPosition.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                            QtCore.Qt.MouseButton.LeftButton, modifiers)
                self.dragMoveEvent(event)
            return
        if self.rightClickStart is not None:
            if (position - self.rightClickStart).manhattanLength() < QtWidgets.QApplication.startDragDistance():
                return
            start = self.rightClickStart
            self.rightClickStart = None
            self.BeginWallDraw(start, modifiers)
            self.UpdateMode(modifiers)
        if self.controlHeld:
            modifiers |= QtCore.Qt.KeyboardModifier.ControlModifier
        if self.openingPlacementMode is not None:
            self.UpdateOpeningMode(position, modifiers)
            return
        self.alignmentGuides = []
        self.hoverPosition = position
        self.lastInteractionPosition = position
        if self.furnishingHandleDrag is not None:
            self.UpdateFurnishingHandleDrag(position, modifiers)
            return
        if getattr(self, "guideTextDrag", None) is not None:
            self.UpdateGuideTextDrag(position)
            return
        if self.groupDrag and self.dragStart is not None:
            self.UpdateGroupDrag(position, modifiers)
            return
        if self.pendingWall is not None:
            if self.wallDrawShape in ("square", "circle"):
                anchor = self.pendingWall.firstVertex
                endpoint = self.SnapPosition(self.ViewportToWorld(position), modifiers)
                delta = endpoint - anchor
                if modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
                    size = max(abs(delta.x()), abs(delta.y()))
                    delta = QtCore.QPointF(math.copysign(size, delta.x()), math.copysign(size, delta.y()))
                    self.alignmentGuides = []
                self.pendingWall.secondVertex = anchor + delta
                first = anchor - delta if modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier else anchor
                second = anchor + delta
                if self.wallDrawShape == "square":
                    corners = (first, QtCore.QPointF(second.x(), first.y()), second,
                               QtCore.QPointF(first.x(), second.y()))
                else:
                    center = (first + second) / 2
                    radiusX = abs(second.x() - first.x()) / 2
                    radiusY = abs(second.y() - first.y()) / 2
                    # Center one horizontal edge on the vertical axis. Even counts also have
                    # its opposing edge; multiples of four align on both axes.
                    phase = math.pi / self.circleSegments - math.pi / 2
                    corners = [center + QtCore.QPointF(math.cos(phase + index * math.tau / self.circleSegments) * radiusX,
                                                       math.sin(phase + index * math.tau / self.circleSegments) * radiusY)
                               for index in range(self.circleSegments)]
                    while len(self.pendingShapeWalls) < self.circleSegments:
                        self.pendingShapeWalls.append(Wall(QtCore.QPointF(anchor), QtCore.QPointF(anchor),
                                                           self.pendingWall.width, material = self.pendingWall.material))
                    del self.pendingShapeWalls[self.circleSegments:]
                for index, wall in enumerate(self.pendingShapeWalls):
                    wall.firstVertex = QtCore.QPointF(corners[index])
                    wall.secondVertex = QtCore.QPointF(corners[(index + 1) % len(corners)])
            else:
                self.pendingWall.secondVertex = self.SnapWallEndpoint(
                    self.ViewportToWorld(position), self.pendingWall.firstVertex, modifiers, wall = self.pendingWall)
            self.update()
        elif self.dragStart is not None:
            delta = position - self.dragStart
            if delta.manhattanLength() >= QtWidgets.QApplication.startDragDistance():
                self.isDragging = True
            if self.isDragging:
                extrude = (isinstance(self.dragSource, Wall) and self.dragSourceVertex is not None
                           and bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier))
                openingPoint = isinstance(self.dragSource, Window) and self.dragSourceVertex is not None
                duplicate = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier) and not openingPoint
                if duplicate != bool(self.dragCopies):
                    # Modifier changes always restart from the captured source,
                    # so releasing Shift turns this gesture into a regular move.
                    source = self.dragSource
                    if isinstance(source, Wall):
                        source.firstVertex, source.secondVertex = map(QtCore.QPointF, self.dragSourceVertices)
                    for attachedWall, vertexIndex, originalPosition in self.dragSourceAttachments:
                        if vertexIndex == 0:
                            attachedWall.firstVertex = QtCore.QPointF(originalPosition)
                        else:
                            attachedWall.secondVertex = QtCore.QPointF(originalPosition)
                    self.RestoreOpeningStates(self.interactionBefore[3])
                    self.inactiveOpeningPreview = None
                    self.doorOrientationLocked = False
                    if duplicate:
                        if isinstance(source, Wall):
                            copy = self.CloneLinearObject(source)
                            if extrude:
                                anchor = QtCore.QPointF(self.dragSourceVertices[self.dragSourceVertex])
                                copy.firstVertex = QtCore.QPointF(anchor)
                                copy.secondVertex = QtCore.QPointF(anchor)
                                self.dragVertices = (QtCore.QPointF(anchor), QtCore.QPointF(anchor))
                                self.selectedVertex = self.dragSourceVertex if isinstance(source, (Arrow, Stair)) else 1
                            children = [] if extrude else [self.CloneOpening(opening, copy) for opening in self.windows if opening.parentWall is source]
                            self.walls.append(copy)
                            self.windows.extend(children)
                            self.dragCopies = [copy] + children
                        else:
                            copy = self.CloneOpening(source, source.parentWall)
                            self.windows.append(copy)
                            self.dragCopies = [copy]
                        self.selectedWall = copy
                        self.dragAttachments = []
                        self.dragConstraints = []
                    else:
                        self.walls = [wall for wall in self.walls if not any(wall is copy for copy in self.dragCopies)]
                        self.windows = [opening for opening in self.windows if not any(opening is copy for copy in self.dragCopies)]
                        self.dragCopies = []
                        self.selectedWall = source
                        self.selectedVertex = self.dragSourceVertex
                        self.dragVertices = tuple(map(QtCore.QPointF, self.dragSourceVertices))
                        self.dragAttachments = self.dragSourceAttachments
                        self.dragConstraints = self.dragSourceConstraints
                if isinstance(self.selectedWall, Window):
                    window = self.selectedWall
                    worldDelta = self.ViewportToWorld(position) - self.ViewportToWorld(self.dragStart)
                    if isinstance(window, Fireplace):
                        original = next(state for state in self.interactionBefore[3] if state[0] is self.dragSource)
                        direction = original[1].secondVertex - original[1].firstVertex
                        direction /= math.hypot(direction.x(), direction.y())
                        normal = QtCore.QPointF(-direction.y(), direction.x())
                        center = (self.dragVertices[0] + self.dragVertices[1]) / 2 + normal * original[6][1] + worldDelta
                        placement = self.FindFireplacePlacement(self.WorldToViewport(center), modifiers, window,
                                                                initialSize = (original[3], original[6][0]))
                        self.inactiveOpeningPreview = (None if placement is not None else
                            self.InactiveOpening(center, Fireplace, window, initialSize = (original[3], original[6][0])))
                        if placement is not None:
                            window.parentWall = placement.parentWall
                            window.centerFraction = placement.centerFraction
                            window.length = placement.length
                            window.depth = placement.depth
                            window.depthOffset = placement.depthOffset
                        self.selectionChanged.emit()
                        self.update()
                        return
                    if self.selectedVertex is None:
                        if not isinstance(window, OpenDoorway) and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier and self.inactiveOpeningPreview is None:
                            self.doorOrientationLocked = True
                            self.OrientDoor(window, position)
                            self.selectionChanged.emit()
                            self.update()
                            return
                        if self.doorOrientationLocked:
                            self.doorOrientationLocked = False
                            self.dragStart = position
                            self.dragVertices = (QtCore.QPointF(window.firstVertex), QtCore.QPointF(window.secondVertex))
                            worldDelta = QtCore.QPointF()
                        center = (self.dragVertices[0] + self.dragVertices[1]) / 2 + worldDelta
                        length = QtCore.QLineF(self.dragVertices[0], self.dragVertices[1]).length()
                        placement = self.FindWindowPlacement(self.WorldToViewport(center), length, window.parentWall,
                                                             type(window), window, modifiers)
                        self.inactiveOpeningPreview = (None if placement is not None else
                                                       self.InactiveOpening(center, type(window), window))
                        if placement is not None:
                            window.parentWall = placement.parentWall
                            window.centerFraction = placement.centerFraction
                            window.length = placement.length
                    else:
                        parent = window.parentWall
                        direction = parent.secondVertex - parent.firstVertex
                        parentLength = QtCore.QLineF(parent.firstVertex, parent.secondVertex).length()
                        target = self.SnapPosition(self.dragVertices[self.selectedVertex] + worldDelta, modifiers,
                                                   parent.firstVertex, direction / parentLength)
                        self.SetOpeningVertex(window, self.selectedVertex, target,
                            fromCenter = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier),
                            initialState = self.dragWindowState[1:])
                    roots = ((window.firstVertex, (window.firstVertex + window.secondVertex) / 2, window.secondVertex)
                             if self.selectedVertex is None else
                             (window.firstVertex if self.selectedVertex == 0 else window.secondVertex,))
                    self.alignmentGuides = [(axis, coordinate) for axis, coordinate in self.alignmentGuides
                                            if any(abs((root.x() if axis == 0 else root.y()) - coordinate) <= 0.01 for root in roots)]
                    self.selectionChanged.emit()
                    self.update()
                    return
                # Restore the captured group before applying the latest delta.
                # Disabling Connected leaves attachments in place.
                movementBefore = self.CaptureState()
                if self.interactionBefore is not None:
                    self.RestoreOpeningStates(self.interactionBefore[3])
                for attachedWall, vertexIndex, originalPosition in self.dragAttachments:
                    if vertexIndex == 0:
                        attachedWall.firstVertex = QtCore.QPointF(originalPosition)
                    else:
                        attachedWall.secondVertex = QtCore.QPointF(originalPosition)
                worldDelta = self.ViewportToWorld(position) - self.ViewportToWorld(self.dragStart)
                anchorIndex = 1 if self.selectedVertex == 1 else 0
                target = self.dragVertices[anchorIndex] + worldDelta
                if self.selectedVertex is None:
                    anchors = list(self.dragVertices)
                    snapTargets = None
                    if (isinstance(self.selectedWall, Wall)
                            and self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier)):
                        originalStair = type(self.selectedWall)(self.dragVertices[0], self.dragVertices[1], self.selectedWall.width)
                        anchors = self.ObjectCorners(originalStair) + list(self.dragVertices) + [(self.dragVertices[0] + self.dragVertices[1]) / 2]
                        snapTargets = self.StairSnapTargets(self.selectedWall) + list(self.SnapVertices())
                    if type(self.selectedWall) is MeasurementGuide:
                        anchors.extend(self.GuideDepthEndpoints(self.selectedWall, self.dragVertices))
                    worldDelta = self.SnapObjectMovement(anchors, worldDelta, modifiers, snapTargets = snapTargets)
                    target = self.dragVertices[anchorIndex] + worldDelta
                else:
                    if isinstance(self.selectedWall, Wall):
                        target = self.SnapStairVertex(target, self.dragVertices[1 - anchorIndex], self.selectedWall, modifiers)
                    else:
                        target = self.SnapWallEndpoint(target, self.dragVertices[1 - anchorIndex], modifiers)
                    minimumLength = self.MinimumOpeningLength(self.selectedWall)
                    opposite = self.dragVertices[1 - anchorIndex]
                    direction = target - opposite
                    distance = math.hypot(direction.x(), direction.y())
                    if distance < minimumLength:
                        if distance < 1e-10:
                            direction = self.dragVertices[anchorIndex] - opposite
                            distance = math.hypot(direction.x(), direction.y())
                        if distance > 1e-10:
                            target = opposite + direction * (minimumLength / distance)
                worldDelta = target - self.dragVertices[anchorIndex]
                # Apply one translation to both wall endpoints, or just the selected vertex.
                if self.selectedVertex != 1:
                    self.selectedWall.firstVertex = self.dragVertices[0] + worldDelta
                if self.selectedVertex != 0:
                    self.selectedWall.secondVertex = self.dragVertices[1] + worldDelta
                if self.connectedEnabled:
                    for attachedWall, vertexIndex, originalPosition in self.ActiveAttachments():
                        if vertexIndex == 0:
                            attachedWall.firstVertex = originalPosition + worldDelta
                        else:
                            attachedWall.secondVertex = originalPosition + worldDelta
                # Keep a collapsed preview until release so validation cancels
                # the entire gesture rather than committing its last valid frame.
                if (not self.FitWallOpenings(self.interactionBefore if self.interactionBefore is not None else movementBefore,
                                            validateFurnishings = False, validateScene = False)
                        and not isinstance(self.selectedWall, Stair)
                        and all(QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() >= 1e-8 for wall in self.walls)):
                    for wall, firstX, firstY, secondX, secondY, width, firstMiter, secondMiter, material, stepCount, directionReversed, measurementHidden in movementBefore[0]:
                        wall.firstVertex = QtCore.QPointF(firstX, firstY)
                        wall.secondVertex = QtCore.QPointF(secondX, secondY)
                    self.RestoreOpeningStates(movementBefore[3])
                endpoints = ((self.selectedWall.firstVertex, self.selectedWall.secondVertex) if self.selectedVertex is None else
                             (self.selectedWall.firstVertex if self.selectedVertex == 0 else self.selectedWall.secondVertex,))
                if isinstance(self.selectedWall, Wall):
                    endpoints = self.ObjectCorners(self.selectedWall) + list(endpoints)
                self.alignmentGuides = [(axis, coordinate) for axis, coordinate in self.alignmentGuides
                                        if any(abs((vertex.x() if axis == 0 else vertex.y()) - coordinate) <= 0.01 for vertex in endpoints)]
                self.selectionChanged.emit()
                self.update()


from planner_app.viewport.widget import DrawingViewport

class ReferenceViewport(ReferenceScene, ReferencePlacement, ReferenceInteraction, DrawingViewport):
    pass
