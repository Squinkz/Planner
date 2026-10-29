"""Selection, connected objects, group movement and undo/redo history."""
from planner_app.models import AngleGuide, NorthArrow, ObjectControlPoints, SetControlPoint, DashedLine, Elevator

import math
import time
from planner_app.object_schema import openingFields
from planner_app.geometry.attachments import AttachedVertexIndices, ConnectedAttachments
from planner_app.geometry.editing import TransformPoint, OpeningTransformTarget, ReattachTransformedOpening, RebaseMergedOpening, ChooseWallSplit, OpeningOrientationChanges, PointerRotation
from planner_app.selection_copy import OpeningCopyTargets, RemapCopiedGroups
from planner_app.geometry.selection_edits import MoveObjectRecord, ReflectionObjectRecord, PlanMoveSelection, PlanSelectionReflection
from planner_app.geometry.linear_edits import PlanSubdivision, PlanDissolution
from planner_app.geometry.group_movement import (OpeningTransferLength, PlanOpeningTransfer, ProjectGroupTravel, GroupOpeningLimits,
    BoundGroupTravel, TranslatedOpeningFraction, AttachedConstraintPoint)
from .geometry import CollisionPass
from planner_app.history_edits import SceneEdit, ReferenceImageEdit
from planner_app.furnishing_parts import FurnishingParts, FurnishingCollisionFootprints
from planner_app.furnishing_imports import ResolveFurnishingImports
from planner_app.project_codec import EncodeFurnishingDefinitions
from planner_app.graphics.path_operations import Paths
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import (
    Door, SwingingDoor, DoubleDoor, Furnishing, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, SlidingDoor, MeasurementGuide, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, Window, Fireplace, objectIdCounter,
)


def SnapshotPointMatches(point, x, y):
    pointX, pointY = point.x(), point.y()
    if pointX != x or pointY != y:
        return False
    # Signed zero can affect angle calculations; retain snapshot signs as well.
    return ((x != 0 or math.copysign(1, pointX) == math.copysign(1, x))
            and (y != 0 or math.copysign(1, pointY) == math.copysign(1, y)))


def NativeEditAffine(operation, *values):
    if operation == "reflection":
        center, angle, horizontal = values
        transform = QtGui.QTransform().translate(*center).rotate(angle)
        transform.scale(-1 if horizontal else 1, 1 if horizontal else -1)
        transform.rotate(-angle).translate(-center[0], -center[1])
        return transform.m11(), transform.m12(), transform.m21(), transform.m22(), transform.dx(), transform.dy()
    if operation == "point":
        point, frame = values
        target = QtGui.QTransform(*frame).map(QtCore.QPointF(*point))
        return target.x(), target.y()
    raise ValueError("Unknown edit affine operation")


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
        entries = self.SelectionEntries()
        if all(isinstance(obj, MeasurementGuide) and index == 3 for obj, index in entries):
            before = self.CaptureState()
            for obj, index in entries:
                obj.textOffset += delta
            self.RecordEdit(before)
            self.update()
            return
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
            return "Select an object to transform."
        if not all(math.isfinite(value) for value in (x, y, angle)):
            return "Enter valid movement and angle values."
        if x == 0 and y == 0 and angle % 360 == 0:
            return None
        self.CancelInteraction()
        before = self.CaptureState()
        bounds = self.ObjectFootprint(objects[0])[0]
        for obj in objects[1:]:
            bounds = bounds.united(self.ObjectFootprint(obj)[0])
        sharedOrigin = QtCore.QPointF(self.rotationPivot) if self.rotationPivot is not None else bounds.center()
        models = {id(obj): obj for obj in objects}
        records = [MoveObjectRecord(id(obj), tuple((point.x(), point.y()) for point in ObjectControlPoints(obj)),
            isinstance(obj, Window), 2 if isinstance(obj, AngleGuide) else None) for obj in objects]
        attachments = []
        originalIndex = self.selectedVertex
        try:
            if self.connectedEnabled and (self.connectedObjectsEnabled or self.connectedVerticesEnabled):
                for obj in objects:
                    if isinstance(obj, (Window, Label)) or isinstance(obj, Furnishing) and type(obj) is not Furnishing:
                        continue
                    self.selectedVertex = None
                    for attached, vertexIndex, vertex in self.AttachedVertices(obj):
                        models.setdefault(id(attached), attached)
                        attachments.append((id(obj), id(attached), vertexIndex, (vertex.x(), vertex.y())))
        finally:
            self.selectedVertex = originalIndex
        guides = [(key, len(ObjectControlPoints(obj)), (obj.textOffset.x(), obj.textOffset.y()))
                  for key, obj in models.items() if isinstance(obj, MeasurementGuide)]
        points, openingTargets, offsets = PlanMoveSelection(records, attachments, guides, (x, y), angle,
            (sharedOrigin.x(), sharedOrigin.y()), localOrigins,
            originsMatch = lambda first, second: first == second or QtCore.QPointF(*first) == QtCore.QPointF(*second))
        self.dragConstraints = []
        for key, index, point in points:
            SetControlPoint(models[key], index, QtCore.QPointF(*point))
        for key, offset in offsets:
            models[key].textOffset = QtCore.QPointF(*offset)
        # Stretching a connected neighbor must carry its openings by the same
        # anchor/fraction rules as a canvas drag before validating collisions.
        if not self.FitWallOpenings(before, validateFurnishings = False, validateScene = False):
            self.RestoreState(before)
            return "This move would overlap an object or obstruct an opening."
        for key, target, targetDirection in openingTargets:
            opening = models[key]
            parent = opening.parentWall
            placement = ReattachTransformedOpening(target, targetDirection, (parent.firstVertex.x(), parent.firstVertex.y()),
                                                    (parent.secondVertex.x(), parent.secondVertex.y()))
            if placement is None:
                self.RestoreState(before)
                return "Doors and windows must stay on their wall. Select the wall to move or rotate them together."
            opening.centerFraction, flipped = placement
            fields = {name: getattr(opening, name) for name in ("hingeAtSecond", "swingsOutwards", "panelsFlipped") if hasattr(opening, name)}
            for name, value in OpeningOrientationChanges(fields, flipped).items():
                setattr(opening, name, value)
        if not self.OpeningsValid(before = before):
            self.RestoreState(before)
            return "This move would overlap an object or obstruct an opening."
        for key, index, point in points:
            self.PropagateMiter(models[key], index)
        self.RecordEdit(before)
        self.selectionChanged.emit()
        self.update()
        return None

    def FlipObjects(self, objects, horizontal, value = None):
        objects = list({id(obj): obj for obj in objects}.values())
        if not objects:
            return False
        self.CancelInteraction()
        before = self.CaptureState()
        bounds = QtCore.QRectF(self.ObjectFootprint(objects[0])[0])
        for obj in objects[1:]:
            bounds = bounds.united(self.ObjectFootprint(obj)[0])
        sharedCenter = bounds.center()
        command = "flipHorizontal" if horizontal else "flipVertical"
        models = {id(obj): obj for obj in objects}
        records = []
        for obj in objects:
            kind = "opening" if isinstance(obj, Window) else "artwork" if type(obj) is Furnishing else "text" if isinstance(obj, Label) else "geometry"
            records.append(ReflectionObjectRecord(id(obj), tuple((point.x(), point.y()) for point in ObjectControlPoints(obj)), kind,
                obj.angle if kind in ("artwork", "text") and not self.localTransforms else 0,
                getattr(obj, command) if kind == "artwork" else False,
                (obj.textOffset.x(), obj.textOffset.y()) if isinstance(obj, MeasurementGuide) else None,
                2 if isinstance(obj, AngleGuide) else None,
                obj.length if kind in ("artwork", "text") and not self.localTransforms else None))
        openings = []
        for opening in self.windows:
            if id(opening.parentWall) in models or id(opening) in models:
                models[id(opening)] = opening
                openings.append((id(opening), id(opening.parentWall),
                    (opening.firstVertex.x(), opening.firstVertex.y()), (opening.secondVertex.x(), opening.secondVertex.y())))
        edits, openingTargets = PlanSelectionReflection(records, openings, (sharedCenter.x(), sharedCenter.y()),
            horizontal, self.localTransforms, value, NativeEditAffine)
        for key, kind, geometry, flipped, offset in edits:
            obj = models[key]
            if kind in ("artwork", "text"):
                if kind == "artwork":
                    setattr(obj, command, flipped)
                obj.firstVertex, obj.secondVertex = QtCore.QPointF(*geometry[0]), QtCore.QPointF(*geometry[1])
            else:
                for index, point in enumerate(geometry):
                    SetControlPoint(obj, index, QtCore.QPointF(*point))
                if offset is not None:
                    obj.textOffset = QtCore.QPointF(*offset)
        for key, target, direction in openingTargets:
            opening = models[key]
            parent = opening.parentWall
            placement = ReattachTransformedOpening(target, direction,
                (parent.firstVertex.x(), parent.firstVertex.y()), (parent.secondVertex.x(), parent.secondVertex.y()))
            if placement is None:
                self.RestoreState(before)
                self.clipboardMessage.emit("Doors and windows must stay on their wall. Include the wall in the selection to flip them together.")
                return False
            opening.centerFraction, reversedAlongWall = placement
            fields = {name: getattr(opening, name) for name in ("hingeAtSecond", "swingsOutwards", "panelsFlipped") if hasattr(opening, name)}
            if isinstance(opening, Fireplace):
                fields["depthOffset"] = opening.depthOffset
            for name, value in OpeningOrientationChanges(fields, reversedAlongWall, reflected = True).items():
                setattr(opening, name, value)
        if not self.OpeningsValid(before = before):
            self.RestoreState(before)
            self.clipboardMessage.emit("This flip would overlap an object or obstruct an opening.")
            return False
        self.RecordEdit(before)
        self.selectionChanged.emit()
        self.update()
        return True

    def PrepareWallSelectionRotation(self, state):
        vertices = {}
        originalIndex = self.selectedVertex
        try:
            for obj, index in state["sourceEntries"]:
                if isinstance(obj, Window):
                    continue
                for vertexIndex, vertex in enumerate(ObjectControlPoints(obj)):
                    vertices[(id(obj), vertexIndex)] = (obj, vertexIndex, QtCore.QPointF(vertex))
                if self.connectedEnabled and (self.connectedVerticesEnabled or self.connectedObjectsEnabled):
                    self.selectedVertex = None
                    for attached, vertexIndex, vertex in self.AttachedVertices(obj):
                        vertices.setdefault((id(attached), vertexIndex), (attached, vertexIndex, vertex))
        finally:
            self.selectedVertex = originalIndex
        state["sourceRotationVertices"] = list(vertices.values())
        state["rotationVertices"] = state["sourceRotationVertices"]
        state["sourceGuideOffsets"] = [(obj, QtCore.QPointF(obj.textOffset))
            for obj in {id(obj): obj for obj, index, vertex in vertices.values()}.values()
            if isinstance(obj, MeasurementGuide) and all((id(obj), index) in vertices for index in range(len(ObjectControlPoints(obj))))]
        state["rotationGuideOffsets"] = state["sourceGuideOffsets"]
        movingIds = {key[0] for key in vertices}
        selectedIds = {id(obj) for obj, index in state["sourceEntries"]}
        state["sourceOpeningStates"] = tuple(entry for entry in self.interactionBefore[3]
                                             if id(entry[1]) in movingIds or id(entry[0]) in selectedIds)
        state["rotationOpenings"] = state["sourceOpeningStates"]
        state["rotationValid"] = True

    def UpdateWallSelectionRotation(self, state, position, modifiers):
        # Every frame starts from captured geometry, including connected endpoints
        # and fitted openings. No cumulative transforms or per-frame discovery.
        for obj, index, vertex in state["rotationVertices"]:
            SetControlPoint(obj, index, vertex)
        for obj, offset in state["rotationGuideOffsets"]:
            obj.textOffset = QtCore.QPointF(offset)
        self.RestoreOpeningStates(state["rotationOpenings"])
        duplicate = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier) and not self.ObjectsHaveAssetErrors(
            obj for obj, index in state["sourceEntries"])
        if duplicate != bool(state["copies"]):
            copyIds = {id(obj) for obj in state["copies"]}
            self.walls = [obj for obj in self.walls if id(obj) not in copyIds]
            self.windows = [obj for obj in self.windows if id(obj) not in copyIds]
            self.furnishings = [obj for obj in self.furnishings if id(obj) not in copyIds]
            self.labels = [obj for obj in self.labels if id(obj) not in copyIds]
            self.objectGroups = list(self.interactionBefore[6])
            state["copies"] = []
            if duplicate:
                copies = self.DuplicateSelectionObjects([obj for obj, index in state["sourceEntries"]], self.interactionBefore[6])
                state["copies"] = list(copies.values())
                state["members"] = [(copies[id(obj)], first, second, width, angle)
                                    for obj, first, second, width, angle in state["sourceStates"]]
                state["rotationVertices"] = [(copies[id(obj)], index, vertex)
                                             for obj, index, vertex in state["sourceRotationVertices"] if id(obj) in copies]
                state["rotationGuideOffsets"] = [(copies[id(obj)], offset) for obj, offset in state["sourceGuideOffsets"] if id(obj) in copies]
                copyIds = {id(obj) for obj in state["copies"]}
                state["rotationOpenings"] = tuple(entry for entry in self.CaptureState()[3] if id(entry[0]) in copyIds)
                self.SetSelection([(copies[id(obj)], index) for obj, index in state["sourceEntries"]])
                self.furnishingRotationObject = self.selectedWall
            else:
                state["members"] = list(state["sourceStates"])
                state["rotationVertices"] = state["sourceRotationVertices"]
                state["rotationGuideOffsets"] = state["sourceGuideOffsets"]
                state["rotationOpenings"] = state["sourceOpeningStates"]
                self.SetSelection(state["sourceEntries"])
                self.furnishingRotationObject = state["sourceRotationObject"]
            state["object"].selectionMembers = tuple(entry[0] for entry in state["members"])
        self.rotationPivot = QtCore.QPointF(state["pivot"])
        offset = self.ViewportToWorld(position) - state["pivot"]
        angle, cosine, sine = PointerRotation((offset.x(), offset.y()), state["mouseAngle"],
            snapping = self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier))
        state["object"].angle = angle
        origin = (state["pivot"].x(), state["pivot"].y())
        for obj, index, vertex in state["rotationVertices"]:
            target = QtCore.QPointF(*TransformPoint((vertex.x(), vertex.y()), origin, None, cosine, sine))
            SetControlPoint(obj, index, target)
        for obj, offset in state["rotationGuideOffsets"]:
            obj.textOffset = QtCore.QPointF(*TransformPoint((offset.x(), offset.y()), (0, 0), None, cosine, sine))
        state["rotationValid"] = self.FitWallOpenings(self.interactionBefore, validateFurnishings = False, validateScene = False)
        movedKeys = {(id(obj), index) for obj, index, vertex in state["rotationVertices"]}
        for obj, first, second, width, memberAngle in state["members"]:
            if not isinstance(obj, Window) or all((id(obj.parentWall), index) in movedKeys for index in (0, 1)):
                continue  # Children of rigidly rotated walls already follow their parent.
            target, direction = OpeningTransformTarget((first.x(), first.y()), (second.x(), second.y()), origin, (0, 0), cosine, sine)
            parent = obj.parentWall
            placement = ReattachTransformedOpening(target, direction, (parent.firstVertex.x(), parent.firstVertex.y()),
                                                    (parent.secondVertex.x(), parent.secondVertex.y()))
            if placement is None:
                state["rotationValid"] = False
            else:
                obj.centerFraction, flipped = placement
                fields = {name: getattr(obj, name) for name in ("hingeAtSecond", "swingsOutwards", "panelsFlipped") if hasattr(obj, name)}
                for name, value in OpeningOrientationChanges(fields, flipped).items():
                    setattr(obj, name, value)
        state["rotationValid"] = state["rotationValid"] and self.OpeningsValid(before = self.interactionBefore)

    def AttachedVertices(self, selectedWall, captureAll = False):
        attachments = []
        self.dragConstraints = []
        if isinstance(selectedWall, (Label, Window)) or isinstance(selectedWall, Furnishing) and type(selectedWall) is not Furnishing:
            return attachments
        if isinstance(selectedWall, AngleGuide):
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
        stroker = Paths.PrepareStroke(width = .02)
        for obj in candidates if wholeObjects else ():
            path = QtGui.QPainterPath()
            if type(obj) is Furnishing and obj.definition.get("components"):
                path.setFillRule(QtCore.Qt.FillRule.WindingFill)
                for bounds, corners, axes in FurnishingCollisionFootprints(obj):
                    path.addPolygon(QtGui.QPolygonF([QtCore.QPointF(*point) for point in corners]))
                    path.closeSubpath()
            else:
                corners = self.ObjectCorners(obj)
                if corners:
                    path.moveTo(corners[0])
                    for corner in corners[1:]:
                        path.lineTo(corner)
                    if len(corners) > 2:
                        path.closeSubpath()
            paths[id(obj)] = Paths.Union(path, stroker(path))
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
        contacts = (lambda first, second: Paths.Intersects(paths[first], paths[second])) if type(selectedWall) in (Wall, Pillar, Column, Furnishing, Stair, Counter, Railing) else None
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
        if (isinstance(self.selectedWall, AngleGuide) or isinstance(self.selectedWall, MeasurementGuide) and self.selectedVertex == 3) and not self.groupDrag:
            return []
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
        stepLimits, railingLimits = self.AutoSizingLimits("stairs"), self.AutoSizingLimits("railings")
        for drawingObject in self.walls + self.windows + self.furnishings + self.labels:
            if isinstance(drawingObject, Stair):
                drawingObject.sceneStairs = stairs
                drawingObject.stepSizeBounds = (stepLimits["minimum"], stepLimits["maximum"])
            if isinstance(drawingObject, Railing):
                drawingObject.spacingBounds = tuple(railingLimits[key] for key in ("minimum", "maximum", "target"))

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
        reference = getattr(self, "referenceImage", None)
        if reference is not None and reference.active:
            return
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

    def ReattachOpeningGroup(self, delta, modifiers):
        # Body selections on one stationary parent can transfer as a rigid set.
        # Endpoint edits and mixed wall/object selections keep their constraints.
        entries = self.groupEntries
        if not entries or any(not isinstance(obj, Window) or isinstance(obj, Fireplace) or index is not None
                              for obj, index in entries):
            return False
        source = entries[0][0].parentWall
        if any(obj.parentWall is not source for obj, index in entries):
            return False
        sourceDirection = source.secondVertex - source.firstVertex
        sourceLength = OpeningTransferLength((sourceDirection.x(), sourceDirection.y()), (delta.x(), delta.y()),
                                             self.basePixelsPerMillimeter, self.zoom)
        if sourceLength is None:
            return False
        # Duplication rebuilds selection and may change selectedWall to the last
        # member. Keep the object actually grabbed as the placement anchor.
        anchor = next((obj for (obj, index), (original, originalIndex) in zip(entries, self.groupSourceEntries)
                       if original is self.dragSource), self.selectedWall)
        originalFraction = anchor.centerFraction
        excluded = frozenset(id(obj) for obj, index in entries)
        center = (anchor.firstVertex + anchor.secondVertex) / 2 + delta
        placement = self.FindWindowPlacement(self.WorldToViewport(center), anchor.length, source,
                                              type(anchor), anchor, modifiers, excludeIds = excluded)
        if placement is not None and placement.parentWall is source:
            return False
        if placement is not None:
            parent = placement.parentWall
            direction = parent.secondVertex - parent.firstVertex
            length = math.hypot(direction.x(), direction.y())
            plan = PlanOpeningTransfer(sourceLength, originalFraction, length, placement.centerFraction,
                [(obj.centerFraction, obj.length) for obj, index in entries],
                QtCore.QPointF.dotProduct(direction, sourceDirection) < 0)
            if plan is not None:
                fractions, clipped = plan
                for (obj, index), fraction in zip(entries, fractions):
                    obj.parentWall = parent
                    obj.centerFraction = fraction
                if self.GroupOpeningsFit(entries):
                    if clipped:
                        self.alignmentGuides = []
                        self.snapApplied = False
                    return True
                self.RestoreOpeningStates(self.groupOpeningStates)
        # Keep real attachments in the captured state until the complete set fits.
        # The renderer hides those members and draws each cursor-following ghost
        # with the same artwork and invalid color as a detached single opening.
        self.groupOpeningPreviews = [self.InactiveOpening((obj.firstVertex + obj.secondVertex) / 2 + delta, type(obj), obj)
                                     for obj, index in entries]
        self.inactiveOpeningPreview = self.groupOpeningPreviews[0]
        self.alignmentGuides = []
        self.snapApplied = False
        return True

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

    @CollisionPass
    def GroupOpeningsFit(self, openings):
        # All positions are final for this preview. Share read-only collision
        # preparation here, never across the preceding model assignments or
        # SetOpeningVertex calls, which may move/restore an opening themselves.
        with self.OpeningCandidatePass(len(openings)):
            for opening, index in openings:
                if not (self.OpeningFits(opening) and (isinstance(opening, PocketDoor) or opening.firstFraction >= 0 and opening.secondFraction <= 1)):
                    return False
        return True

    def CaptureOpeningStates(self):
        return tuple((window, window.parentWall, window.centerFraction, window.length,
                      window.hingeAtSecond if isinstance(window, (Door, SwingingDoor, SlidingDoor, PocketDoor, CasementWindow)) else None,
                      window.swingsOutwards if type(window) in (Window, Door, DoubleDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, BarnDoor, BifoldDoor, Fireplace) else
                      window.panelsFlipped if isinstance(window, SlidingDoor) else None,
                      window.sillDepth if isinstance(window, SilledWindow) else (window.depth, window.depthOffset, window.material) if isinstance(window, Fireplace) else None,
                      window.measurementFlipped, window.measurementHidden,
                      (window.windowWell, window.wellDepth, window.wellDashed)) for window in self.windows)

    def CaptureState(self):
        walls = []
        for wall in self.walls:
            sizing = ((wall.autosize, wall.manualPostCount) if isinstance(wall, Railing) else
                      (wall.autosize, wall.manualStepCount) if isinstance(wall, Stair) else None)
            if isinstance(wall, DashedLine):
                details = (wall.weightClass, wall.textOffset.x(), wall.textOffset.y())
            elif isinstance(wall, AngleGuide):
                details = (wall.middleVertex.x(), wall.middleVertex.y(), wall.textOffset.x(), wall.textOffset.y())
            elif isinstance(wall, MeasurementGuide):
                details = ((wall.depth, wall.textOffset.x(), wall.textOffset.y()) if type(wall) is MeasurementGuide else
                           (wall.textOffset.x(), wall.textOffset.y()))
            elif isinstance(wall, Arrow):
                details = (wall.solidTip, wall.tipSize, wall.intensity, wall.directionReversed)
            else:
                details = wall.directionReversed if isinstance(wall, Stair) else None
            walls.append((wall, wall.firstVertex.x(), wall.firstVertex.y(), wall.secondVertex.x(), wall.secondVertex.y(),
                          wall.width, wall.firstMiter, wall.secondMiter, wall.material, sizing, details, wall.measurementHidden))
        walls = tuple(walls)
        windows = SceneEditingMixin.CaptureOpeningStates(self)
        furnishings = tuple((obj, QtCore.QPointF(obj.firstVertex), QtCore.QPointF(obj.secondVertex), obj.width,
                            obj.behindCounters, obj.flipHorizontal, obj.flipVertical,
                            *((obj.intensity,) if isinstance(obj, NorthArrow) else ()), obj.measurementHidden) for obj in self.furnishings)
        return (walls, self.selectedWall, self.selectedVertex, windows, tuple(self.SelectionEntries()), furnishings,
                tuple(self.objectGroups), tuple(self.hiddenObjects),
                tuple((obj, QtCore.QPointF(obj.firstVertex), QtCore.QPointF(obj.secondVertex), obj.width, obj.text, obj.intensity)
                      + ((obj.unitsOverride,) if hasattr(obj, "unitsOverride") else ())
                      + (obj.measurementHidden,) for obj in self.labels))

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
            replacedEdit = None
            now = time.monotonic()
            if (coalesceKey is not None and coalesceKey == getattr(self, "historyCoalesceKey", None)
                    and now - getattr(self, "historyCoalesceTime", 0) <= 1.0 and self.undoHistory
                    and getattr(self, "historyCoalesceRevision", None) == self.sceneRevision):
                original = self.undoHistory[-1].Apply(before, False, validate = True)
                replacedEdit = self.undoHistory.pop()
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
            activity = getattr(self, "activityLog", None)
            if activity is not None:
                activity.SceneEdited(edit, replacedEdit)
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
            if isinstance(wall, MeasurementGuide):
                wall.textOffset = QtCore.QPointF(*directionReversed[-2:])
                if type(wall) is MeasurementGuide:
                    wall.depth = directionReversed[0] if len(directionReversed) > 2 else 0
            if isinstance(wall, DashedLine):
                wall.weightClass = directionReversed[0]
            if isinstance(wall, AngleGuide):
                wall.middleVertex = QtCore.QPointF(*directionReversed[:2])
            if isinstance(wall, Arrow):
                wall.solidTip, wall.tipSize, wall.intensity = directionReversed[:3]
                wall.directionReversed = directionReversed[3] if len(directionReversed) > 3 else False
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
                    and (window.windowWell, window.wellDepth, window.wellDashed) == (openingState[9] if len(openingState) > 9 else (False, 600.0, False))
                    and (not isinstance(window, SilledWindow) or window.sillDepth == sillDepth)
                    and (not isinstance(window, (Door, SwingingDoor, SlidingDoor, PocketDoor, CasementWindow))
                         or window.hingeAtSecond == hingeAtSecond)
                    and (type(window) not in (Window, Door, DoubleDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, BarnDoor, BifoldDoor)
                         or window.swingsOutwards == swingsOutwards)
                    and (not isinstance(window, SlidingDoor) or window.panelsFlipped == swingsOutwards)):
                continue
            window.measurementFlipped = openingState[7] if len(openingState) > 7 else False
            window.measurementHidden = openingState[8] if len(openingState) > 8 else False
            window.windowWell, window.wellDepth, window.wellDashed = openingState[9] if len(openingState) > 9 else (False, 600.0, False)
            window.parentWall = parentWall
            window.centerFraction = centerFraction
            window.length = length
            if isinstance(window, SilledWindow):
                window.sillDepth = sillDepth
            if isinstance(window, Fireplace):
                window.depth, window.depthOffset, window.material = sillDepth
            if isinstance(window, (Door, SwingingDoor, SlidingDoor, PocketDoor, CasementWindow)):
                window.hingeAtSecond = hingeAtSecond
            if type(window) in (Window, Door, DoubleDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, BarnDoor, BifoldDoor, Fireplace):
                window.swingsOutwards = swingsOutwards
            elif isinstance(window, SlidingDoor):
                window.panelsFlipped = swingsOutwards

    def RestoreLabelStates(self, states, restoreList = True):
        if restoreList:
            self.labels = []
        for state in states:
            obj, first, second, width, text, intensity = state[:6]
            measurementHidden = state[-1]
            if hasattr(obj, "unitsOverride"):
                obj.unitsOverride = state[6] if len(state) > 7 else None
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
        for state in states:
            obj, first, second, width, behindCounters, flipHorizontal, flipVertical = state[:7]
            measurementHidden = state[-1]
            if isinstance(obj, NorthArrow):
                obj.intensity = state[7] if len(state) > 8 else 1.0
            if (not SnapshotPointMatches(obj.firstVertex, first.x(), first.y())
                    or not SnapshotPointMatches(obj.secondVertex, second.x(), second.y())
                    or (obj.width, obj.behindCounters, obj.flipHorizontal, obj.flipVertical, obj.measurementHidden)
                    != (width, behindCounters, flipHorizontal, flipVertical, measurementHidden)):
                obj.behindCounters = behindCounters
                obj.flipHorizontal = flipHorizontal
                obj.flipVertical = flipVertical
                obj.measurementHidden = measurementHidden
                obj.firstVertex = QtCore.QPointF(first)
                obj.secondVertex = QtCore.QPointF(second)
                obj.width = width
            if restoreList:
                self.furnishings.append(obj)

    def Undo(self):
        reference = getattr(self, "referenceImage", None)
        if reference is not None and reference.active:
            reference.CancelDrag()
            reference.FinishPropertyDrag(True)
        if self.exportOverlay.active:
            self.window().exportPanel.UndoExport()
            return
        self.historyCoalesceKey = None
        self.CancelInteraction()
        if self.undoHistory:
            edit = self.undoHistory.pop()
            if isinstance(edit, ReferenceImageEdit):
                reference.RestoreHistory(edit, False)
                self.sceneRevision += 1
                self.sceneChanged.emit()
            else:
                self.RestoreState(edit.Apply(self.CaptureState(), False))
            self.redoHistory.append(edit)
            activity = getattr(self, "activityLog", None)
            if activity is not None:
                activity.Travel(edit, False)

    def Redo(self):
        reference = getattr(self, "referenceImage", None)
        if reference is not None and reference.active:
            reference.CancelDrag()
            reference.FinishPropertyDrag(True)
        if self.exportOverlay.active:
            self.window().exportPanel.RedoExport()
            return
        self.historyCoalesceKey = None
        self.CancelInteraction()
        if self.redoHistory:
            edit = self.redoHistory.pop()
            if isinstance(edit, ReferenceImageEdit):
                reference.RestoreHistory(edit, True)
                self.sceneRevision += 1
                self.sceneChanged.emit()
            else:
                self.RestoreState(edit.Apply(self.CaptureState(), True))
            self.undoHistory.append(edit)
            activity = getattr(self, "activityLog", None)
            if activity is not None:
                activity.Travel(edit, True)

    def DissolveWalls(self, vertex, objectType = Wall):
        self.CancelInteraction()
        walls = [wall for wall in self.walls if type(wall) is objectType and any(
            QtCore.QLineF(vertex, endpoint).length() <= .01 for endpoint in (wall.firstVertex, wall.secondVertex))]
        if len(walls) != 2 or objectType in (Pillar, Column, Elevator, AngleGuide):
            return False
        self.EnsureObjectIds()
        source, other = sorted(walls, key = lambda wall: wall.objectId)
        try:
            first, second, firstMiter, secondMiter, direction, length = PlanDissolution((vertex.x(), vertex.y()),
                ((source.firstVertex.x(), source.firstVertex.y()), (source.secondVertex.x(), source.secondVertex.y()), source.firstMiter, source.secondMiter),
                ((other.firstVertex.x(), other.firstVertex.y()), (other.secondVertex.x(), other.secondVertex.y()), other.firstMiter, other.secondMiter))
        except ValueError as error:
            self.clipboardMessage.emit(str(error))
            return False
        merged = self.CloneLinearObject(source)
        merged.firstVertex, merged.secondVertex = QtCore.QPointF(*first), QtCore.QPointF(*second)
        merged.firstMiter, merged.secondMiter = firstMiter, secondMiter
        wallIds = {id(wall) for wall in walls}
        openings = []
        for opening in self.windows:
            if id(opening.parentWall) not in wallIds:
                continue
            center = (opening.firstVertex + opening.secondVertex) / 2
            clone = self.CloneOpening(opening, merged)
            oldDirection = opening.parentWall.secondVertex - opening.parentWall.firstVertex
            fraction, fits, flipped = RebaseMergedOpening((center.x(), center.y()), (oldDirection.x(), oldDirection.y()),
                first, direction, length, clone.length)
            clone.centerFraction = fraction
            if not fits:
                self.clipboardMessage.emit("Cannot dissolve: an opening would not fit the new wall.")
                return False
            fields = {name: getattr(clone, name) for name in ("hingeAtSecond", "swingsOutwards", "panelsFlipped") if hasattr(clone, name)}
            if isinstance(clone, Fireplace):
                fields["depthOffset"] = clone.depthOffset
            for name, value in OpeningOrientationChanges(fields, flipped).items():
                setattr(clone, name, value)
            openings.append((opening, clone))
        candidates = [clone for opening, clone in openings] + [opening for opening in self.windows if id(opening.parentWall) not in wallIds]
        if objectType is Wall and (any(self.OpeningsOverlap(firstOpening, secondOpening) for index, firstOpening in enumerate(candidates)
                for secondOpening in candidates[index + 1:]) or
                any(self.JoinedObjectsOverlap(merged, obj, contactTolerance = 1.0, excludedWalls = wallIds) for obj in
                    self.furnishings + [wall for wall in self.walls if isinstance(wall, (Stair, Counter))])):
            self.clipboardMessage.emit("Cannot dissolve: objects would overlap on the new wall.")
            return False
        if (isinstance(merged, Counter) and not self.CounterFits(merged, excludeIds = wallIds)
                or isinstance(merged, Stair) and not self.StairFits(merged, excludeIds = wallIds)
                or isinstance(merged, Railing) and not self.WallFits(merged, excludeIds = wallIds)):
            self.clipboardMessage.emit("Cannot dissolve: the new object would overlap another object.")
            return False
        before = self.CaptureState()
        for opening, clone in openings:
            opening.parentWall, opening.centerFraction = merged, clone.centerFraction
            if isinstance(opening, Fireplace):
                opening.depth, opening.depthOffset = clone.depth, clone.depthOffset
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
        selectedIds = {id(obj) for obj in objects}
        walls = [wall for wall in self.walls if type(wall) not in (Pillar, Column, Elevator, AngleGuide)
                 and id(wall) in selectedIds]
        if not walls:
            return False
        splitFractions = {}
        for wall in walls:
            if type(wall) is Wall and QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() < 2e-8:
                return False
            direction = wall.secondVertex - wall.firstVertex
            fraction = .5 if type(wall) is not Wall else ChooseWallSplit((wall.firstVertex.x(), wall.firstVertex.y()), (direction.x(), direction.y()),
                (self.NumericCollisionFootprint(other, self.ObjectFootprint(other))
                 for other in self.walls + self.furnishings if other is not wall),
                ((opening.firstFraction, opening.secondFraction) for opening in self.windows if opening.parentWall is wall))
            if fraction is None:
                self.clipboardMessage.emit("Cannot subdivide: no clear wall segment is available.")
                return False
            splitFractions[id(wall)] = fraction
        try:
            plans, openingMoves = PlanSubdivision(
                ((id(wall), (wall.firstVertex.x(), wall.firstVertex.y()), (wall.secondVertex.x(), wall.secondVertex.y()),
                  wall.firstMiter, wall.secondMiter, splitFractions[id(wall)]) for wall in walls),
                ((index, id(opening.parentWall), opening.centerFraction) for index, opening in enumerate(self.windows)))
        except ValueError:
            return False
        before = self.CaptureState()
        replacements = {}
        for wall in walls:
            firstPlan, secondPlan, fraction = plans[id(wall)]
            first, second = self.CloneLinearObject(wall), self.CloneLinearObject(wall)
            first.secondVertex, first.secondMiter = QtCore.QPointF(*firstPlan[1]), firstPlan[3]
            second.firstVertex, second.firstMiter = QtCore.QPointF(*secondPlan[0]), secondPlan[2]
            replacements[id(wall)] = (first, second)
        for index, parent, half, fraction in openingMoves:
            opening = self.windows[index]
            opening.parentWall = replacements[parent][half]
            opening.centerFraction = fraction
        self.walls = [part for wall in self.walls for part in replacements.get(id(wall), (wall,))]
        self.objectGroups = [tuple(part for obj in group for part in replacements.get(id(obj), (obj,)))
                             for group in self.objectGroups]
        self.hiddenObjects = [part for obj in self.hiddenObjects for part in replacements.get(id(obj), (obj,))]
        self.hiddenObjectIds = {id(obj) for obj in self.hiddenObjects}
        self.SetSelection([(part, index) for wall in walls
                           for part, index in zip(replacements[id(wall)], (1, 0))])
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

    def CloneLinearObject(self, source):
        clone = type(source)(QtCore.QPointF(source.firstVertex), QtCore.QPointF(source.secondVertex), source.width,
                             source.firstMiter, source.secondMiter, source.material)
        clone.measurementHidden = source.measurementHidden
        if isinstance(source, MeasurementGuide):
            clone.textOffset = QtCore.QPointF(source.textOffset)
            if type(source) is MeasurementGuide:
                clone.depth = source.depth
        if isinstance(source, DashedLine):
            clone.weightClass = source.weightClass
        if isinstance(source, AngleGuide):
            clone.middleVertex = QtCore.QPointF(source.middleVertex)
        if isinstance(source, Arrow):
            clone.solidTip, clone.tipSize, clone.intensity = source.solidTip, source.tipSize, source.intensity
            clone.directionReversed = source.directionReversed
        if isinstance(source, Railing):
            clone.autosize, clone.manualPostCount = source.autosize, source.manualPostCount
            clone.spacingBounds = source.spacingBounds
        if isinstance(source, Stair):
            clone.directionReversed = source.directionReversed
            clone.autosize, clone.manualStepCount = source.autosize, source.manualStepCount
            clone.stepSizeBounds = source.stepSizeBounds
        return clone

    def DuplicateSelectionObjects(self, objects, groups):
        if self.ObjectsHaveAssetErrors(objects):
            return {}
        copies = {}
        selectedIds = {id(obj) for obj in objects}
        # Selection order can differ from paint order. Clone each source list in
        # its existing order so copied furnishings retain their relative stack.
        for obj in self.walls + self.furnishings + self.labels:
            if id(obj) not in selectedIds:
                continue
            if isinstance(obj, (Label, Furnishing)):
                copy = obj.Clone()
                (self.labels if isinstance(obj, Label) else self.furnishings).append(copy)
            elif isinstance(obj, Wall):
                copy = self.CloneLinearObject(obj)
                self.walls.append(copy)
            else:
                continue  # Openings are copied after their parents.
            copies[id(obj)] = copy
        for opening, parent in OpeningCopyTargets(((opening, opening.parentWall) for opening in list(self.windows)), copies, selectedIds):
            copy = self.CloneOpening(opening, parent)
            copies[id(opening)] = copy
            self.windows.append(copy)
        self.objectGroups.extend(RemapCopiedGroups(groups, copies))
        return copies

    def DecomposeFurnishings(self, objects):
        self.CancelInteraction()
        selectedIds = {id(obj) for obj in objects if type(obj) is Furnishing}
        replacements = {}
        definitions = self.furnishingDefinitions
        imported = {}
        parentDefinitions = {}
        for parent in self.furnishings:
            components = parent.definition.get("components")
            if id(parent) not in selectedIds or not components:
                continue
            try:
                portable = EncodeFurnishingDefinitions([parent.definition], includeBuiltIns = True)
                definitions, additions, remapped = ResolveFurnishingImports(portable, definitions, suffix = "decomposed")
                imported.update(additions)
                definition = definitions[remapped.get(parent.definition["key"], parent.definition["key"])]
                candidate = Furnishing(definition)
                candidate.firstVertex, candidate.secondVertex = QtCore.QPointF(parent.firstVertex), QtCore.QPointF(parent.secondVertex)
                candidate.width = parent.width
                candidate.flipHorizontal, candidate.flipVertical = parent.flipHorizontal, parent.flipVertical
                candidate.behindCounters, candidate.measurementHidden = parent.behindCounters, parent.measurementHidden
                parts = FurnishingParts(candidate)
                for part in parts:
                    if part.definition["key"] != "null":
                        part.definition = definitions[part.definitionKey]
                replacements[id(parent)] = parts
                parentDefinitions[id(parent)] = definition
            except (OSError, ValueError, KeyError, TypeError) as error:
                self.clipboardMessage.emit("Cannot decompose furnishing: " + str(error))
                return False
        if not replacements:
            return False
        before = self.CaptureState()
        # History retains the original models. Their equivalent, canonical
        # definitions must also remain resolvable after undo and save/reopen.
        for parent in self.furnishings:
            if id(parent) in parentDefinitions:
                parent.definition = parentDefinitions[id(parent)]
                parent.definitionKey = parent.definition["key"]
        if imported:
            self.projectFurnishingDefinitions = {**self.projectFurnishingDefinitions, **imported}
            self.furnishingDefinitions = definitions
            main = self.window()
            main.RefreshFurnishingRenderers()
            main.BuildFurnishTab(refresh = True)
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
