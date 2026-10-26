"""Mouse/keyboard gestures, drag previews, cancellation and context actions."""
from planner_app.models import AngleGuide, ObjectControlPoints

import math
from time import perf_counter
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import OpenDoorway, Furnishing, MeasurementGuide, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, Window, Fireplace
from planner_app.graphics.cursors import RotationCursor


class InteractionMixin:
    def SelectionTarget(self, position, modifiers = None, hoverHit = None):
        hitObject, hitIndex = self.HitTest(position) if hoverHit is None else hoverHit
        furnishing, handle = self.HitFurnishingHandle(position, hoverHit = (hitObject, hitIndex))
        if handle is not None:
            return furnishing, None, handle
        entries = self.SelectionEntries()
        modifiers = QtWidgets.QApplication.keyboardModifiers() if modifiers is None else modifiers
        shiftHeld = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)
        wholeHitSelected = any(obj is hitObject and index is None for obj, index in entries)
        hitSelected = any(obj is hitObject and (index == hitIndex or index is None) for obj, index in entries)
        extrudeVertex = hitIndex is not None and isinstance(hitObject, (Wall, Window))
        if hitSelected and len(entries) > 1 and not (shiftHeld and extrudeVertex and not wholeHitSelected):
            # A selected body in a multi-selection moves with that selection.
            # Its nearby endpoint must not advertise a separate vertex drag.
            hitIndex = next(index for obj, index in entries if obj is hitObject and (index == hitIndex or index is None))
        return hitObject, hitIndex, None

    def UpdateCanvasCursor(self, hoverHit = None):
        if self.exportOverlay.active:
            self.exportOverlay.UpdateCursor()
            return
        if self.guiDragActive:
            return
        if self.referenceImage is not None and self.referenceImage.active:
            self.referenceImage.UpdateCursor()
            return
        shape = QtCore.Qt.CursorShape.ArrowCursor
        handle = None
        if self.isPanning:
            shape = QtCore.Qt.CursorShape.ClosedHandCursor
        elif self.openingPlacementMode is not None:
            shape = QtCore.Qt.CursorShape.BlankCursor
        elif self.pendingWall is not None or self.mode == "Wall":
            shape = QtCore.Qt.CursorShape.CrossCursor
        elif self.furnishingHandleDrag is not None:
            handle = self.furnishingHandleDrag["handle"]
        elif self.dragStart is not None and self.selectedWall is not None:
            shape = QtCore.Qt.CursorShape.SizeAllCursor
        elif self.boxStart is None and self.hoverPosition is not None and self.DrawingRect().contains(self.hoverPosition):
            hitObject, hitIndex, handle = self.SelectionTarget(self.hoverPosition, hoverHit = hoverHit)
            if handle is None and hitObject is not None:
                shape = QtCore.Qt.CursorShape.SizeAllCursor
        if handle is not None:
            if handle[0] == "rotate":
                cursor = RotationCursor()
                if self.cursor().shape() != cursor.shape() or self.cursor().pixmap().cacheKey() != cursor.pixmap().cacheKey():
                    self.setCursor(cursor)
                return
            if handle[0] == "pivot":
                shape = QtCore.Qt.CursorShape.SizeAllCursor
            else:
                outward = handle[4]
                direction = round(math.degrees(math.atan2(outward.y(), outward.x())) / 45) % 4
                shape = (QtCore.Qt.CursorShape.SizeHorCursor, QtCore.Qt.CursorShape.SizeFDiagCursor,
                         QtCore.Qt.CursorShape.SizeVerCursor, QtCore.Qt.CursorShape.SizeBDiagCursor)[direction]
        if self.cursor().shape() != shape:
            self.setCursor(shape)

    def UpdateMode(self, modifiers):
        self.mode = self.openingPlacementMode or ("Wall" if self.wallDrawButton == QtCore.Qt.MouseButton.RightButton else "Select")
        self.UpdateCanvasCursor()

        self.update()

    def EndPan(self):
        """Finish only the camera gesture, leaving other interaction state intact."""
        self.panFrameTimer.stop()
        self.panFrameDeadline = None
        self.isPanning = False
        self.lastPanPosition = None
        self.UpdateCanvasCursor()
        self.update()

    def RequestPanFrame(self):
        if not self.isPanning:
            return
        if self.exportOverlay.active:
            self.update()
            return
        if not self.panFrameTimer.isActive():
            now = perf_counter()
            if self.panFrameDeadline is None:
                self.panFrameDeadline = now
            self.panFrameTimer.start(max(0, math.ceil((self.panFrameDeadline - now) * 1000)))

    def PaintPanFrame(self):
        if not self.isPanning:
            return
        now = perf_counter()
        deadline = self.panFrameDeadline if self.panFrameDeadline is not None else now
        # Advance to the next future slot. A late frame never queues historical
        # frames or repeatedly restarts a relative timer behind the pointer.
        elapsedSlots = max(0, math.floor((now - deadline) / self.panFrameInterval))
        self.panFrameDeadline = deadline + (elapsedSlots + 1) * self.panFrameInterval
        self.update()

    def StopDragPan(self):
        self.dragPanTimer.stop()
        self.dragPanPosition = None
        self.dragPanButtons = QtCore.Qt.MouseButton.NoButton
        self.dragPanVelocity = QtCore.QPointF()
        self.dragPanLastTime = None
        self.dragPanMimeData = None
        self.dragPanActions = QtCore.Qt.DropAction.IgnoreAction

    def UpdateDragPan(self, position, buttons):
        reference = self.referenceImage
        referenceDrag = (reference is not None and reference.active and reference.drag is not None
                         and reference.drag["moved"])
        calibrationDrag = (reference is not None and reference.active and reference.calibration.active
                           and reference.calibration.draggedPoint is not None)
        drawing = (self.pendingWall is not None and self.wallStartPosition is not None
                   and (position - self.wallStartPosition).manhattanLength() >= QtWidgets.QApplication.startDragDistance())
        transforming = self.dragStart is not None and self.isDragging
        boxSelecting = (self.boxStart is not None and buttons & QtCore.Qt.MouseButton.LeftButton
                        and (position - self.boxStart).manhattanLength() >= QtWidgets.QApplication.startDragDistance())
        placingOpening = self.openingPlacementMode is not None and self.openingPlacementPressed
        placing = (self.guiDragActive and not self.guiDragCancelled and self.dragPanMimeData is not None
                   and any(preview is not None for preview in (self.furnishingPreview, self.windowDropPreview,
                           self.inactiveOpeningPreview, self.counterPreview, self.arrowPreview, self.labelPreview)))
        if (self.exportOverlay.active or self.isPanning or not (referenceDrag or calibrationDrag or drawing or transforming or boxSelecting or placing or placingOpening)
                or not buttons & (QtCore.Qt.MouseButton.LeftButton | QtCore.Qt.MouseButton.RightButton)):
            self.StopDragPan()
            return
        rect = self.DrawingRect()
        band = min(24.0, rect.width() / 4, rect.height() / 4)
        if band <= 0:
            self.StopDragPan()
            return
        velocity = QtCore.QPointF()
        for axis, value, first, last in (("x", position.x(), rect.left(), rect.right()),
                                          ("y", position.y(), rect.top(), rect.bottom())):
            if value < first + band:
                speed = min(1.0, (first + band - value) / band) + max(0.0, first - value) / 96
            elif value > last - band:
                speed = -(min(1.0, (value - last + band) / band) + max(0.0, value - last) / 96)
            else:
                speed = 0.0
            speed = max(-5.0, min(5.0, speed)) * 480
            if axis == "x":
                velocity.setX(speed)
            else:
                velocity.setY(speed)
        if velocity.isNull():
            self.StopDragPan()
            return
        # Edge penetration controls speed; direction must not add a diagonal boost.
        speed = max(abs(velocity.x()), abs(velocity.y()))
        velocity *= speed / math.hypot(velocity.x(), velocity.y())
        self.dragPanPosition = QtCore.QPointF(position)
        self.dragPanButtons = buttons
        self.dragPanVelocity = velocity
        if not self.dragPanTimer.isActive():
            self.dragPanLastTime = perf_counter()
            self.dragPanTimer.start()

    def AdvanceDragPan(self):
        position = self.dragPanPosition
        if position is None:
            self.StopDragPan()
            return
        self.UpdateDragPan(position, self.dragPanButtons)
        if self.dragPanPosition is None:
            return
        now = perf_counter()
        elapsed = min(.05, max(0, now - self.dragPanLastTime))
        self.dragPanLastTime = now
        delta = self.dragPanVelocity * elapsed
        self.panOffset += delta
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        reference = self.referenceImage
        if self.guiDragActive and self.dragPanMimeData is not None:
            event = QtGui.QDragMoveEvent(position.toPoint(), self.dragPanActions, self.dragPanMimeData,
                                         self.dragPanButtons, modifiers)
            self.dragMoveEvent(event)
        elif reference is not None and reference.active and reference.calibration.active:
            calibration = reference.calibration
            calibration.dragStart += delta
            calibration.hover = self.ViewportToWorld(position)
            calibration.UpdatePoint(modifiers)
        elif reference is not None and reference.active and reference.drag is not None:
            reference.drag["mouseStart"] += delta
            reference.UpdateDrag(position, modifiers)
        elif self.boxStart is not None:
            # Keep the box origin on its original world point as the camera moves.
            self.boxStart += delta
            self.boxEnd = QtCore.QPointF(position)
        else:
            # These are screen-space anchors for captured world-space geometry.
            # Carry them with the camera so a stationary pointer keeps dragging.
            if self.dragStart is not None:
                self.dragStart += delta
            if self.furnishingHandleDrag is not None:
                self.furnishingHandleDrag["mouseStart"] += delta
            if self.pendingWall is not None and self.wallStartPosition is not None:
                self.wallStartPosition += delta
            self.UpdateInteraction(position, modifiers)
        self.update()

    def CancelInteraction(self):
        self.StopDragPan()
        handleState = self.furnishingHandleDrag
        self.EndPan()
        self.guideTextDrag = None
        self.vertexAxisFromDragged = False
        self.vertexAxisWheelDelta = 0
        self.axisConstraintOrigin = None
        self.axisConstraintDirection = None
        if self.furnishingHandleDrag is not None and self.furnishingHandleDrag["handle"][0] in ("pivot", "rotate"):
            self.rotationPivot = self.furnishingHandleDrag["previousPivot"]
        self.furnishingHandleDrag = None
        self.pendingFurnishingHandleToggle = None
        if self.openingPlacementMode is not None:
            self.EndOpeningMode()
        self.furnishingPreview = None
        self.windowDropPreview = None
        self.labelPreview = None
        self.counterPreview = None
        self.arrowPreview = None
        self.alignmentGuides = []
        self.doorOrientationLocked = False
        if self.dragWindowState is not None and isinstance(self.selectedWall, Window):
            self.selectedWall.parentWall, self.selectedWall.centerFraction, self.selectedWall.length = self.dragWindowState
        elif self.dragVertices is not None and self.selectedWall is not None:
            self.selectedWall.firstVertex, self.selectedWall.secondVertex = self.dragVertices
        for wall, vertexIndex, originalPosition in self.dragAttachments:
            if vertexIndex == 0:
                wall.firstVertex = QtCore.QPointF(originalPosition)
            else:
                wall.secondVertex = QtCore.QPointF(originalPosition)
        if self.interactionBefore is not None:
            self.RestoreOpeningStates(self.interactionBefore[3])
            if len(self.interactionBefore) > 5:
                self.RestoreFurnishingStates(self.interactionBefore[5])
                self.RestoreLabelStates(self.interactionBefore[8])
            for state in self.interactionBefore[0]:
                if isinstance(state[0], MeasurementGuide):
                    state[0].textOffset = QtCore.QPointF(*state[10][-2:])
                if isinstance(state[0], AngleGuide):
                    state[0].middleVertex = QtCore.QPointF(*state[10][:2])
                if self.groupDrag or isinstance(state[0], Pillar) or handleState is not None and handleState.get("structuralRotation", False):
                    state[0].width = state[5]
                    state[0].firstVertex = QtCore.QPointF(state[1], state[2])
                    state[0].secondVertex = QtCore.QPointF(state[3], state[4])
                if isinstance(state[0], Stair):
                    state[0].directionReversed = state[10]
        if handleState is not None and handleState["copies"]:
            copyIds = {id(obj) for obj in handleState["copies"]}
            self.walls = [obj for obj in self.walls if id(obj) not in copyIds]
            self.windows = [obj for obj in self.windows if id(obj) not in copyIds]
            self.objectGroups = list(self.interactionBefore[6])
            self.SetSelection(handleState["sourceEntries"])
            self.furnishingRotationObject = handleState["sourceRotationObject"]
            self.rotationPivot = handleState["previousPivot"]
        if self.dragCopies:
            if self.interactionBefore is not None:
                self.objectGroups = list(self.interactionBefore[6])
            self.walls = [wall for wall in self.walls if not any(wall is copy for copy in self.dragCopies)]
            self.windows = [opening for opening in self.windows if not any(opening is copy for copy in self.dragCopies)]
            self.furnishings = [obj for obj in self.furnishings if not any(obj is copy for copy in self.dragCopies)]
            self.labels = [obj for obj in self.labels if not any(obj is copy for copy in self.dragCopies)]
            self.selectedWall = self.dragSource
            self.selectedVertex = self.dragSourceVertex
        if self.groupDrag:
            self.SetSelection(self.groupSourceEntries)
        self.dragSource = None
        self.dragSourceVertex = None
        self.dragSourceVertices = None
        self.dragCopies = []
        self.dragSourceAttachments = []
        self.dragSourceConstraints = []
        self.dragAttachments = []
        self.dragConstraints = []
        self.pendingWall = None
        self.pendingShapeWalls = []
        self.rightClickStart = None
        self.wallStartPosition = None
        self.wallDrawButton = None
        self.dragStart = None
        self.dragVertices = None
        self.dragWindowState = None
        self.inactiveOpeningPreview = None
        self.groupOpeningPreviews = []
        self.isDragging = False
        self.interactionBefore = None
        self.boxStart = self.boxEnd = None
        self.boxSelectionRemove = False
        self.pendingShiftSelection = None
        self.groupDrag = False
        self.groupEntries = []
        self.groupMovedVertices = []
        self.groupMovedOpenings = []
        self.UpdateMode(QtWidgets.QApplication.keyboardModifiers())
        self.selectionChanged.emit()
        self.update()

    def UpdateInteraction(self, position, modifiers):
        self.axisConstraintOrigin = None
        self.axisConstraintDirection = None
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

    def wheelEvent(self, event):
        if (self.dragStart is not None and self.isDragging and self.selectedVertex is not None
                and not isinstance(self.selectedWall, Window)
                and (self.controlHeld or event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier)):
            delta = event.angleDelta().y()
            if delta:
                self.vertexAxisWheelDelta += delta
                steps = math.trunc(self.vertexAxisWheelDelta / 120)
                self.vertexAxisWheelDelta -= steps * 120
            else:
                steps = (1 if event.pixelDelta().y() > 0 else -1) if event.pixelDelta().y() else 0
            if steps % 2:
                self.vertexAxisFromDragged = not self.vertexAxisFromDragged
                self.UpdateInteraction(self.lastInteractionPosition or event.position(), event.modifiers())
            event.accept()
            return
        if self.pendingWall is not None and self.wallDrawShape == "circle":
            delta = event.angleDelta().y()
            if delta:
                self.circleWheelDelta += delta
                steps = math.trunc(self.circleWheelDelta / 120)
                self.circleWheelDelta -= steps * 120
            else:
                steps = (1 if event.pixelDelta().y() > 0 else -1) if event.pixelDelta().y() else 0
            if steps:
                self.circleSegments = max(3, self.circleSegments + steps)
                self.UpdateInteraction(event.position(), event.modifiers())
            event.accept()
            return
        if self.openingPlacementMode is not None:
            delta = event.angleDelta().y() or event.pixelDelta().y()
            if delta:
                self.lastInteractionPosition = event.position()
                self.CycleOpeningType(1 if delta < 0 else -1)
            event.accept()
            return
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.pixelDelta().y()
        if delta:
            self.ZoomBy(1.15 if delta > 0 else 1.0 / 1.15, event.position())
        event.accept()

    def BeginWallDraw(self, position, modifiers):
        self.wallDrawButton = QtCore.Qt.MouseButton.RightButton
        self.interactionBefore = self.CaptureState()
        self.wallStartPosition = position
        worldPosition = self.SnapPosition(self.ViewportToWorld(position), modifiers)
        hitWall, vertexIndex = self.HitTest(position)
        width = self.newWallWidth
        miter = 0.0
        if hitWall is not None and vertexIndex is not None:
            vertex = ObjectControlPoints(hitWall)[vertexIndex] if vertexIndex < 3 else hitWall.firstVertex
            worldPosition = QtCore.QPointF(vertex)
            if not isinstance(hitWall, Window):
                miter = hitWall.firstMiter if vertexIndex == 0 else hitWall.secondMiter
        else:
            for wall in self.walls:
                if QtCore.QLineF(worldPosition, wall.firstVertex).length() <= 0.01:
                    miter = wall.firstMiter
                    break
                if QtCore.QLineF(worldPosition, wall.secondVertex).length() <= 0.01:
                    miter = wall.secondMiter
                    break
        self.selectedWall = None
        self.selectedVertex = None
        self.pendingWall = Wall(worldPosition, QtCore.QPointF(worldPosition), width, firstMiter = miter,
                                material = self.newWallMaterial)
        self.wallDrawShape = self.wallShape
        self.circleSegments = 8
        self.circleWheelDelta = 0
        count = 8 if self.wallDrawShape == "circle" else 4 if self.wallDrawShape == "square" else 0
        self.pendingShapeWalls = [Wall(QtCore.QPointF(worldPosition), QtCore.QPointF(worldPosition), width,
                                           material = self.newWallMaterial)
                                  for index in range(count)]
        self.selectionChanged.emit()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.RightButton and self.dragStart is not None:
            self.CancelInteraction()
            event.accept()
            return
        if (event.button() == QtCore.Qt.MouseButton.LeftButton
                and event.buttons() & QtCore.Qt.MouseButton.RightButton
                and (self.rightClickStart is not None or self.pendingWall is not None
                     and self.wallDrawButton == QtCore.Qt.MouseButton.RightButton)):
            self.CancelInteraction()
            event.accept()
            return
        if (event.button() == QtCore.Qt.MouseButton.LeftButton and self.dragStart is None
                and self.openingPlacementMode is None and self.pendingWall is None
                and self.DrawingRect().contains(event.position())):
            self.hoverPosition = event.position()
            furnishing, hitIndex, handle = self.SelectionTarget(event.position(), event.modifiers())
            if handle is not None:
                self.setFocus()
                self.BeginFurnishingHandleDrag(furnishing, handle, event.position())
                event.accept()
                return
        if self.openingPlacementMode is not None and event.button() != QtCore.Qt.MouseButton.MiddleButton:
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                self.openingPlacementPressed = True
                self.UpdateOpeningMode(event.position(), event.modifiers())
            event.accept()
            return
        if (event.button() == QtCore.Qt.MouseButton.RightButton and self.pendingWall is None
                and self.dragStart is None and self.DrawingRect().contains(event.position())):
            self.setFocus()
            self.rightClickStart = QtCore.QPointF(event.position())
            event.accept()
            return
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self.StopDragPan()
            self.isPanning = True
            self.lastPanPosition = event.position()
            refresh = self.screen().refreshRate()
            self.panFrameInterval = 1 / (refresh if math.isfinite(refresh) and refresh > 0 else 60)
            self.panFrameDeadline = perf_counter() + self.panFrameInterval
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            self.update()
            event.accept()
            return
        if (event.button() in (QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.RightButton)
                and self.DrawingRect().contains(event.position())):
            if self.pendingWall is not None or self.dragStart is not None:
                event.accept()
                return
            self.setFocus()
            self.wallDrawButton = event.button() if event.button() == QtCore.Qt.MouseButton.RightButton else None
            self.UpdateMode(event.modifiers())
            self.lastInteractionPosition = event.position()
            if self.mode == "Wall":
                self.BeginWallDraw(event.position(), event.modifiers())
            else:
                entries = self.SelectionEntries()
                hitWall, hitIndex, handle = self.SelectionTarget(event.position(), event.modifiers())
                shiftHeld = bool(event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier)
                controlHeld = bool(event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier)
                modifiedSelection = shiftHeld or controlHeld
                extrudeVertex = hitIndex is not None and isinstance(hitWall, (Wall, Window))
                if modifiedSelection and hitWall is not None:
                    self.pendingShiftSelection = (list(entries), hitWall, hitIndex, controlHeld)
                hitSelected = any(obj is hitWall and (index == hitIndex or index is None) for obj, index in entries)
                self.pendingFurnishingHandleToggle = hitWall if isinstance(hitWall, (Furnishing, Pillar)) and hitSelected and not modifiedSelection else None
                if hitWall is None:
                    self.boxStart = self.boxEnd = event.position()
                    self.boxSelectionBefore = list(entries) if modifiedSelection else []
                    self.boxSelectionRemove = controlHeld
                    if not modifiedSelection:
                        self.SetSelection([])
                    event.accept()
                    return
                wholeHitSelected = any(obj is hitWall and index is None for obj, index in entries)
                if hitSelected and len(entries) > 1 and not (shiftHeld and extrudeVertex and not wholeHitSelected):
                    self.selectedWall, self.selectedVertex = hitWall, hitIndex
                    self.selection = list(entries)
                else:
                    self.SetSelection([(hitWall, hitIndex)], notify = not modifiedSelection)
                if self.selectedWall is not None:
                    self.vertexAxisFromDragged = False
                    self.vertexAxisWheelDelta = 0
                    self.dragSource = self.selectedWall
                    self.dragSourceVertex = self.selectedVertex
                    self.interactionBefore = self.CaptureState()
                    self.dragStart = event.position()
                    self.dragVertices = (QtCore.QPointF(self.selectedWall.firstVertex),
                                         QtCore.QPointF(self.selectedWall.secondVertex))
                    self.dragSourceVertices = tuple(map(QtCore.QPointF, self.dragVertices))
                    if isinstance(self.selectedWall, AngleGuide):
                        self.dragSourceVertices = tuple(map(QtCore.QPointF, ObjectControlPoints(self.selectedWall)))
                    if isinstance(self.selectedWall, Window):
                        window = self.selectedWall
                        self.dragWindowState = (window.parentWall, window.centerFraction, window.length)
                        self.dragAttachments = []
                    else:
                        self.dragAttachments = self.AttachedVertices(self.selectedWall, captureAll = True)
                    self.dragSourceAttachments = list(self.dragAttachments)
                    self.dragSourceConstraints = list(self.dragConstraints)
                    if isinstance(self.selectedWall, MeasurementGuide) and self.selectedVertex == 3:
                        self.guideTextDrag = QtCore.QPointF(self.selectedWall.textOffset)
                    elif len(self.SelectionEntries()) > 1 or isinstance(self.selectedWall, (Furnishing, Label, Pillar, AngleGuide)):
                        self.StartGroupDrag()
                if self.pendingShiftSelection is None:
                    self.selectionChanged.emit()
            if self.pendingShiftSelection is None:
                self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.hoverPosition = event.position()
        if self.isPanning and not event.buttons() & QtCore.Qt.MouseButton.MiddleButton:
            self.EndPan()
            event.accept()
            return
        if self.dragStart is not None or self.pendingWall is not None:
            self.UpdateCanvasCursor()
        if not self.isPanning:
            self.update()
        if self.boxStart is not None:
            self.boxEnd = event.position()
            event.accept()
            return
        if self.isPanning:
            self.panOffset += event.position() - self.lastPanPosition
            self.lastPanPosition = event.position()
            self.RequestPanFrame()
            if self.openingPlacementMode is not None:
                self.UpdateOpeningMode(event.position(), event.modifiers())
            event.accept()
            return
        if self.openingPlacementMode is not None:
            self.UpdateOpeningMode(event.position(), event.modifiers() | QtWidgets.QApplication.keyboardModifiers())
            event.accept()
            return
        if self.rightClickStart is not None or self.pendingWall is not None or self.dragStart is not None:
            self.UpdateInteraction(event.position(), event.modifiers() | QtWidgets.QApplication.keyboardModifiers())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.hoveredAngleGuide = None
        self.hoverPosition = None
        self.UpdateCanvasCursor()
        if self.openingPlacementMode is not None:
            self.windowDropPreview = None
            self.inactiveOpeningPreview = None
            self.doorOrientationLocked = False
            self.alignmentGuides = []
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.RightButton and self.rightClickStart is not None:
            self.UpdateInteraction(event.position(), event.modifiers())
            if self.rightClickStart is not None:
                self.rightClickStart = None
                if self.DrawingRect().contains(event.position()):
                    self.ShowObjectContextMenu(event.position(), event.globalPosition().toPoint())
                event.accept()
                return
        if self.furnishingHandleDrag is not None and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.UpdateInteraction(event.position(), event.modifiers())
            furnishing = self.furnishingHandleDrag["object"]
            before = self.interactionBefore
            members = [state[0] for state in self.furnishingHandleDrag["members"]] or [furnishing]
            movingPivot = self.furnishingHandleDrag["handle"][0] == "pivot"
            fireplace = self.furnishingHandleDrag.get("fireplace")
            if self.furnishingHandleDrag.get("structuralRotation", False) and not movingPivot:
                if not self.furnishingHandleDrag["rotationValid"]:
                    self.CancelInteraction()
                else:
                    for obj, index, vertex in self.furnishingHandleDrag["rotationVertices"]:
                        if isinstance(obj, Wall):
                            self.PropagateMiter(obj, index)
                    self.RecordEdit(before)
            elif fireplace is not None:
                if self.OpeningFits(fireplace):
                    self.RecordEdit(before)
                else:
                    self.RestoreOpeningStates(before[3])
            elif not movingPivot and any(not self.FurnishingFits(obj) for obj in members):
                self.CancelInteraction()
            elif not movingPivot:
                self.RecordEdit(before)
            self.furnishingHandleDrag = None
            self.dragStart = None
            self.interactionBefore = None
            self.isDragging = False
            self.alignmentGuides = []
            self.axisConstraintOrigin = None
            self.axisConstraintDirection = None
            self.UpdateCanvasCursor()
            self.selectionChanged.emit()
            self.update()
            event.accept()
            return
        if self.openingPlacementMode is not None and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.UpdateOpeningMode(event.position(), event.modifiers())
            placement = self.windowDropPreview
            if (self.openingPlacementPressed and isinstance(placement, Window)
                    and self.DrawingRect().contains(event.position()) and self.OpeningFits(placement)):
                self.windowDropPreview = None
                self.doorOrientationLocked = False
                self.PlaceWindow(event.position(), type(placement), event.modifiers(), placement)
            self.openingPlacementPressed = False
            self.UpdateOpeningMode(event.position(), event.modifiers())
            event.accept()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self.boxStart is not None:
            rect = QtCore.QRectF(self.boxStart, event.position()).normalized()
            entries = list(self.boxSelectionBefore)
            dragged = (event.position() - self.boxStart).manhattanLength() >= QtWidgets.QApplication.startDragDistance()
            if dragged:
                enclosedEntries = []
                for obj in self.walls + self.windows + self.furnishings + self.labels:
                    if not self.IsObjectVisible(obj):
                        continue
                    corners = self.ObjectCorners(obj)
                    if corners and all(rect.contains(self.WorldToViewport(corner)) for corner in corners):
                        enclosedEntries.append((obj, None))
                if self.boxSelectionRemove:
                    removedIds = {id(obj) for obj, index in self.ExpandGroupedSelection(enclosedEntries)}
                    entries = [(obj, index) for obj, index in entries if id(obj) not in removedIds]
                else:
                    entries += enclosedEntries
            self.boxStart = self.boxEnd = None
            self.boxSelectionRemove = False
            if dragged:
                self.SetSelection(entries)
            self.update()
            event.accept()
            return
        if event.button() == QtCore.Qt.MouseButton.MiddleButton and self.isPanning:
            self.EndPan()
            self.UpdateMode(event.modifiers())
            event.accept()
            return
        if ((self.pendingWall is not None and event.button() == self.wallDrawButton)
                or (self.pendingWall is None and event.button() == QtCore.Qt.MouseButton.LeftButton)):
            if self.pendingWall is not None:
                self.UpdateInteraction(event.position(), event.modifiers())
                draggedDistance = (event.position() - self.wallStartPosition).manhattanLength()
                newWalls = self.pendingShapeWalls or [self.pendingWall]
                extent = self.pendingWall.secondVertex - self.pendingWall.firstVertex
                if (draggedDistance >= QtWidgets.QApplication.startDragDistance()
                        and (not self.pendingShapeWalls or (abs(extent.x()) >= 1 and abs(extent.y()) >= 1))
                        and all(self.WallFits(wall) for wall in newWalls)):
                    self.walls.extend(newWalls)
                    for wall in newWalls:
                        self.PropagateMiter(wall, 0)
                        self.PropagateMiter(wall, 1)
                self.pendingWall = None
                self.pendingShapeWalls = []
                self.wallStartPosition = None
            elif self.dragStart is not None:
                self.mouseMoveEvent(event)
                self.guideTextDrag = None
                if self.groupDrag and self.groupOpeningPreviews:
                    self.CancelInteraction()
                    event.accept()
                    return
                if self.pendingShiftSelection is not None and not self.isDragging:
                    entries, obj, index, remove = self.pendingShiftSelection
                    clickedEntries = self.ExpandGroupedSelection([(obj, index)])
                    if remove:
                        entries = [(selected, selectedIndex) for selected, selectedIndex in entries
                                   if not any(selected is clicked and (selectedIndex is None or clickedIndex is None
                                                                      or selectedIndex == clickedIndex)
                                              for clicked, clickedIndex in clickedEntries)]
                    else:
                        entries += clickedEntries
                    self.SetSelection(entries, notify = False)
                if self.groupDrag and not self.OpeningsValid(before = self.interactionBefore):
                    self.RestoreState(self.interactionBefore)
                    event.accept()
                    return
                if isinstance(self.selectedWall, Wall) and not self.OpeningsValid(before = self.interactionBefore):
                    self.RestoreState(self.interactionBefore)
                    event.accept()
                    return
                if self.isDragging:
                    for vertexIndex in ((0, 1) if self.selectedVertex is None else (self.selectedVertex,)):
                        self.PropagateMiter(self.selectedWall, vertexIndex)
                    if self.connectedEnabled:
                        for wall, vertexIndex, originalPosition in self.ActiveAttachments():
                            self.PropagateMiter(wall, vertexIndex)
                elif self.pendingFurnishingHandleToggle is not None:
                    furnishing = self.pendingFurnishingHandleToggle
                    selectionBox = self.FurnishingSelectionBox()
                    rotating = (any(obj is self.furnishingRotationObject for obj in selectionBox.selectionMembers)
                                if selectionBox is not None else furnishing is self.furnishingRotationObject)
                    self.furnishingRotationObject = None if rotating else furnishing
                    self.rotationPivot = None
            self.alignmentGuides = []
            if self.dragCopies and not self.OpeningsValid(before = self.interactionBefore):
                self.walls = [wall for wall in self.walls if not any(wall is copy for copy in self.dragCopies)]
                self.windows = [opening for opening in self.windows if not any(opening is copy for copy in self.dragCopies)]
                self.selectedWall = self.dragSource
            self.RecordEdit(self.interactionBefore)
            self.interactionBefore = None
            self.dragStart = None
            self.dragVertices = None
            self.dragWindowState = None
            self.vertexAxisFromDragged = False
            self.vertexAxisWheelDelta = 0
            self.doorOrientationLocked = False
            self.inactiveOpeningPreview = None
            self.groupOpeningPreviews = []
            self.dragAttachments = []
            self.dragConstraints = []
            self.isDragging = False
            self.dragSource = None
            self.dragSourceVertex = None
            self.dragSourceVertices = None
            self.dragCopies = []
            self.groupDrag = False
            self.groupEntries = []
            self.groupMovedVertices = []
            self.groupMovedOpenings = []
            self.pendingShiftSelection = None
            self.pendingFurnishingHandleToggle = None
            self.dragSourceAttachments = []
            self.dragSourceConstraints = []
            self.wallDrawButton = None
            self.UpdateMode(event.modifiers())
            self.selectionChanged.emit()
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def PropagateMiter(self, sourceWall, sourceIndex):
        if isinstance(sourceWall, (Arrow, MeasurementGuide)):
            return
        if isinstance(sourceWall, (Window, Furnishing, Pillar)):
            return
        position = sourceWall.firstVertex if sourceIndex == 0 else sourceWall.secondVertex
        value = sourceWall.firstMiter if sourceIndex == 0 else sourceWall.secondMiter
        for wall in self.walls:
            if (isinstance(wall, (Arrow, MeasurementGuide))
                    or isinstance(wall, Stair) != isinstance(sourceWall, Stair)
                    or isinstance(wall, Railing) != isinstance(sourceWall, Railing)
                    or isinstance(wall, Counter) != isinstance(sourceWall, Counter)):
                continue
            for vertexIndex, vertex in enumerate((wall.firstVertex, wall.secondVertex)):
                if QtCore.QLineF(position, vertex).length() <= 0.01:
                    if vertexIndex == 0:
                        wall.firstMiter = value
                    else:
                        wall.secondMiter = value

    def mouseDoubleClickEvent(self, event):
        if self.openingPlacementMode is not None:
            self.mousePressEvent(event)
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            guide, index, handle = self.SelectionTarget(event.position(), event.modifiers())
            if handle is None and isinstance(guide, MeasurementGuide) and index == 3:
                self.CancelInteraction()
                before = self.CaptureState()
                guide.textOffset = QtCore.QPointF()
                self.RecordEdit(before)
                self.selectionChanged.emit()
                self.update()
                event.accept()
                return
            if handle is not None and handle[0] == "pivot":
                self.CancelInteraction()
                self.rotationPivot = None
                self.UpdateMode(event.modifiers())
                self.selectionChanged.emit()
                event.accept()
                return
        self.UpdateMode(event.modifiers())
        if (event.button() == QtCore.Qt.MouseButton.LeftButton and self.mode == "Select"
                and not event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier
                and self.SelectionTarget(event.position(), event.modifiers())[0] is None):
            self.ResetView()
            event.accept()
            return
        else:
            self.mousePressEvent(event)

    def keyPressEvent(self, event):
        if self.exportOverlay.active:
            # Its overlay handles navigation/modifiers; scene commands stay disabled.
            event.accept()
            return
        if (event.key() in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right, QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down)
                and event.modifiers() in (QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.KeyboardModifier.ShiftModifier)):
            self.NudgeSelection(event.key(), bool(event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier))
            event.accept()
            return
        if (event.key() == QtCore.Qt.Key.Key_V and event.modifiers() ==
                (QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier)):
            self.PasteSelection(inPlace = True)
            event.accept()
            return
        if (event.key() == QtCore.Qt.Key.Key_H
                and event.modifiers() in (QtCore.Qt.KeyboardModifier.NoModifier,
                                          QtCore.Qt.KeyboardModifier.ControlModifier,
                                          QtCore.Qt.KeyboardModifier.AltModifier)):
            if not event.isAutoRepeat():
                command = (self.HideUnselected if event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier else
                           self.UnhideObjects if event.modifiers() == QtCore.Qt.KeyboardModifier.AltModifier else self.HideSelection)
                command()
            event.accept()
            return
        if (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier
                and event.key() == QtCore.Qt.Key.Key_G
                or event.modifiers() == QtCore.Qt.KeyboardModifier.AltModifier and event.key() == QtCore.Qt.Key.Key_G):
            if not event.isAutoRepeat():
                command = self.GroupSelection if event.key() == QtCore.Qt.Key.Key_G and event.modifiers() != QtCore.Qt.KeyboardModifier.AltModifier else self.UngroupSelection
                command()
            event.accept()
            return
        for key, command in ((QtGui.QKeySequence.StandardKey.Cut, self.CutSelection),
                             (QtGui.QKeySequence.StandardKey.Copy, self.CopySelection),
                             (QtGui.QKeySequence.StandardKey.Paste, self.PasteSelection)):
            if event.matches(key):
                command()
                event.accept()
                return
        if (event.key() == QtCore.Qt.Key.Key_A and
                event.modifiers() == (QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier)):
            self.DeselectAll()
            event.accept()
            return
        if event.matches(QtGui.QKeySequence.StandardKey.SelectAll):
            self.SetSelection([(obj, None) for obj in self.walls + self.windows + self.furnishings + self.labels
                               if self.IsObjectVisible(obj)])
            event.accept()
            return
        if event.key() in (QtCore.Qt.Key.Key_Alt, QtCore.Qt.Key.Key_Control, QtCore.Qt.Key.Key_Shift) and self.lastInteractionPosition is not None:
            modifier = {QtCore.Qt.Key.Key_Alt: QtCore.Qt.KeyboardModifier.AltModifier,
                        QtCore.Qt.Key.Key_Control: QtCore.Qt.KeyboardModifier.ControlModifier,
                        QtCore.Qt.Key.Key_Shift: QtCore.Qt.KeyboardModifier.ShiftModifier}[event.key()]
            self.UpdateInteraction(self.lastInteractionPosition, event.modifiers() | modifier)
            event.accept()
            return
        if event.key() == QtCore.Qt.Key.Key_Delete:
            self.DeleteSelected()
            event.accept()
            return
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.CancelInteraction()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() in (QtCore.Qt.Key.Key_Alt, QtCore.Qt.Key.Key_Control, QtCore.Qt.Key.Key_Shift) and self.lastInteractionPosition is not None:
            modifier = {QtCore.Qt.Key.Key_Alt: QtCore.Qt.KeyboardModifier.AltModifier,
                        QtCore.Qt.Key.Key_Control: QtCore.Qt.KeyboardModifier.ControlModifier,
                        QtCore.Qt.Key.Key_Shift: QtCore.Qt.KeyboardModifier.ShiftModifier}[event.key()]
            self.UpdateInteraction(self.lastInteractionPosition, event.modifiers() & ~modifier)
            event.accept()
            return
        super().keyReleaseEvent(event)
