"""Portable scene selections on the system clipboard and atomic paste edits."""
from planner_app.models import AngleGuide

from planner_app.models import Elevator

import json
import copy
import math
from PySide6 import QtCore, QtWidgets
from planner_app.models import Door, SwingingDoor, DoubleDoor, Furnishing, OpenDoorway, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, SlidingDoor, MeasurementGuide, BoundaryLine, DashedLine, SolidLine, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, RoomLabel, Window, NorthArrow, Fireplace


clipboardMimeType = "application/x-planner-selection"
from planner_app.object_schema import openingClasses as openingTypes, openingFields, ReadArrowTipSize
from planner_app.furnishing_assets import FurnishingAssetProblems
from planner_app.units import unitModes
from planner_app.models import lineWeightClasses
from planner_app.project_codec import EncodeFurnishingDefinitions, DecodeFurnishingDefinitions, projectFileLimit
from planner_app.selection_records import ValidateSelectionPayload
from planner_app.selection_placement import PlanSelectionPlacement
from planner_app.selection_copy import SelectionCopyObjects, BuildSelectionTransport
from planner_app.record_schema import selectionObjectLimit
from planner_app.model_construction import PlanObjectConstruction, PlanSelectionOpeningFields
from planner_app.model_factory import ConstructDetachedObject
from planner_app.furnishing_imports import ResolveFurnishingImports
from planner_app.geometry.editing import OpeningOrientationChanges
from planner_app.furnishing_limits import FurnishingExpansionSizes, sceneExpansionLimit


class ClipboardMixin:
    def FurnishingAssetHasErrors(self, key):
        return bool(FurnishingAssetProblems(key, self.furnishingDefinitions, allowNull = False))

    def ObjectsHaveAssetErrors(self, objects):
        return any(
            FurnishingAssetProblems(getattr(obj, "definitionKey", obj.definition["key"]), self.furnishingDefinitions,
                                    obj.definition, allowNull = False)
            for obj in objects if type(obj) is Furnishing)

    def CanCopySelection(self):
        entries = self.SelectionEntries()
        return bool(entries) and not self.ObjectsHaveAssetErrors(obj for obj, index in entries)

    def ShowClipboardError(self, message, isError = True):
        self.clipboardError = message
        self.clipboardErrorIsError = isError
        activity = getattr(self, "activityLog", None)
        if activity is not None:
            activity.Message(message, isError)
        if message:
            self.clipboardErrorTimer.start(5000)
        else:
            self.clipboardErrorTimer.stop()
        self.update()

    def ReadClipboardSelection(self, data = None):
        if data is None:
            mime = QtWidgets.QApplication.clipboard().mimeData()
            if mime is None or not mime.hasFormat(clipboardMimeType):
                return None
            data = bytes(mime.data(clipboardMimeType))
        if len(data) > projectFileLimit:
            return None
        try:
            payload = json.loads(data.decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != 1:
                return None
            portable = DecodeFurnishingDefinitions(payload.get("furnishingDefinitions", {}), self.furnishingDefinitions)
            definitions = {**self.furnishingDefinitions, **portable}
            return ValidateSelectionPayload(payload, definitions, self.warningMaterialBrushes, unitModes, lineWeightClasses)
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError, IndexError):
            return None

    def SelectionCopyRecords(self, objects, selected, wallIndices):
        for obj in objects:
            corners = self.ObjectCorners(obj)
            record = {"type": type(obj).__name__, "selected": id(obj) in selected, "measurementHidden": obj.measurementHidden}
            if isinstance(obj, Window):
                center = (obj.firstVertex + obj.secondVertex) / 2
                record.update(parent = wallIndices.get(id(obj.parentWall)), center = [center.x(), center.y()],
                              fraction = obj.centerFraction, length = obj.length)
                direction = obj.parentWall.secondVertex - obj.parentWall.firstVertex
                wallLength = math.hypot(direction.x(), direction.y())
                record["wallDirection"] = [direction.x() / wallLength, direction.y() / wallLength]
                for attribute in openingFields[type(obj)]:
                    if hasattr(obj, attribute):
                        record[attribute] = getattr(obj, attribute)
            else:
                record.update(first = [obj.firstVertex.x(), obj.firstVertex.y()],
                              second = [obj.secondVertex.x(), obj.secondVertex.y()], width = obj.width)
                if isinstance(obj, Label):
                    record["text"] = obj.text
                    record["intensity"] = obj.intensity
                    if isinstance(obj, RoomLabel):
                        record["unitsOverride"] = obj.unitsOverride
                elif isinstance(obj, NorthArrow):
                    record["intensity"] = obj.intensity
                elif isinstance(obj, Furnishing):
                    record["definition"] = getattr(obj, "definitionKey", obj.definition["key"])
                    record["behindCounters"] = obj.behindCounters
                    record["flipHorizontal"] = obj.flipHorizontal
                    record["flipVertical"] = obj.flipVertical
                else:
                    record.update(firstMiter = obj.firstMiter, secondMiter = obj.secondMiter, material = obj.material)
                    if isinstance(obj, AngleGuide):
                        record["middle"] = [obj.middleVertex.x(), obj.middleVertex.y()]
                    if isinstance(obj, MeasurementGuide):
                        record["textOffset"] = [obj.textOffset.x(), obj.textOffset.y()]
                    if type(obj) is MeasurementGuide and obj.depth != 0:
                        record["depth"] = obj.depth
                    if isinstance(obj, DashedLine):
                        record["weightClass"] = obj.weightClass
                    if isinstance(obj, Arrow):
                        record.update(solidTip = obj.solidTip, tipSize = obj.tipSize, intensity = obj.intensity, tipSizeMode = "millimeters")
                        if obj.directionReversed:
                            record["directionReversed"] = True
                    if isinstance(obj, Railing):
                        record.update(autosize = obj.autosize, manualPostCount = obj.manualPostCount)
                    if isinstance(obj, Stair):
                        record["directionReversed"] = obj.directionReversed
                        record.update(autosize = obj.autosize, manualStepCount = obj.manualStepCount)
            yield record, ((point.x(), point.y()) for point in corners)

    def CopySelection(self):
        self.CancelInteraction()
        if not self.CanCopySelection():
            if self.SelectionEntries():
                self.ShowClipboardError("Cannot copy or cut a selection containing missing or errored furnishings.")
            return False
        selected = {id(obj) for obj, index in self.SelectionEntries()}
        if not selected:
            return False
        objects, wallIndices = SelectionCopyObjects(selected, self.walls,
            ((obj, obj.parentWall) for obj in self.windows), self.furnishings, self.labels)
        if len(objects) > selectionObjectLimit:
            self.ShowClipboardError("Cannot copy or cut more than 10,000 objects at once.")
            return False
        indices = {id(obj): index for index, obj in enumerate(objects)}
        try:
            transport = BuildSelectionTransport(self.SelectionCopyRecords(objects, selected, wallIndices), indices,
                ((id(obj) for obj in group) for group in self.objectGroups))
            portable = EncodeFurnishingDefinitions([obj.definition for obj in objects
                if type(obj) is Furnishing and obj.definition.get("isUser", False)], includeBuiltIns = True)
            if portable:
                transport["furnishingDefinitions"] = portable
            payload = json.dumps(transport, allow_nan = False)
            if self.ReadClipboardSelection(payload.encode("utf-8")) is None:
                raise ValueError("The selection exceeds clipboard limits or contains invalid object data.")
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
            self.ShowClipboardError("Cannot copy or cut this selection: " + str(error))
            return False
        mime = QtCore.QMimeData()
        mime.setData(clipboardMimeType, payload.encode("utf-8"))
        mime.setText(payload)
        QtWidgets.QApplication.clipboard().setMimeData(mime)
        return True

    def CutSelection(self):
        if self.CopySelection():
            self.DeleteSelected()
            return True
        return False

    def PasteSelection(self, position = None, inPlace = False):
        reference = getattr(self, "referenceImage", None)
        if reference is not None and reference.active:
            return False
        if self.exportOverlay.active:
            return False
        payload = self.ReadClipboardSelection()
        if payload is None:
            return False
        self.CancelInteraction()
        if not inPlace and position is None:
            position = self.hoverPosition
            if position is None or not self.DrawingRect().contains(position):
                position = self.DrawingRect().center()
        if not inPlace and not self.DrawingRect().contains(position):
            return False
        # Decode and build detached objects before modifying any scene lists.
        try:
            if payload["version"] != 1 or not payload["objects"] or len(payload["objects"]) > selectionObjectLimit:
                return False
            records = payload["objects"]
            embedded = payload.get("furnishingDefinitions", {})
            imported = {}
            definitions = self.furnishingDefinitions
            if embedded:
                definitions, imported, remapped = ResolveFurnishingImports(embedded, definitions, suffix = "pasted")
                for record in records:
                    if record["type"] == "Furnishing":
                        record["definition"] = remapped.get(record["definition"], record["definition"])
            center = QtCore.QPointF(*payload["center"])
            delta = QtCore.QPointF()
            if not inPlace:
                target = self.SnapPosition(self.ViewportToWorld(position), QtWidgets.QApplication.keyboardModifiers())
                delta = target - center
            created = {}
            # Use Qt's scalar distance primitive to preserve threshold rounding.
            placements = PlanSelectionPlacement(payload, (delta.x(), delta.y()),
                distance = lambda x, y: QtCore.QLineF(0.0, 0.0, x, y).length())
            for index, record, first, second, width in placements:
                plan = PlanObjectConstruction(record, self.warningMaterialBrushes, unitModes, lineWeightClasses,
                    placement = (first, second, width), delta = (delta.x(), delta.y()))
                obj = ConstructDetachedObject(plan, definitions)
                created[index] = obj
        except (ValueError, TypeError, KeyError, OverflowError):
            return False
        try:
            furnishings = [obj for obj in list(self.furnishings) + list(created.values()) if type(obj) is Furnishing]
            sizes = FurnishingExpansionSizes(obj.definition for obj in furnishings)
            count = len(self.walls) + len(self.windows) + len(self.furnishings) + len(self.labels) + len(records)
            if count + sum(sizes[id(obj.definition)] - 1 for obj in furnishings) > sceneExpansionLimit:
                self.ShowClipboardError("Cannot paste: the scene would expand beyond 100,000 objects.")
                return False
        except (ValueError, TypeError, KeyError):
            return False
        before = self.CaptureState()
        originalLists = self.walls, self.windows, self.furnishings, self.labels
        self.walls = self.walls + [obj for obj in created.values() if isinstance(obj, Wall)]
        self.windows = list(self.windows)
        self.furnishings = self.furnishings + [obj for obj in created.values() if isinstance(obj, Furnishing) and not isinstance(obj, Label)]
        self.labels = self.labels + [obj for obj in created.values() if isinstance(obj, Label)]
        valid = True
        try:
            for index, record in enumerate(records):
                if record["type"] not in openingTypes:
                    continue
                objectType = openingTypes[record["type"]]
                if record["parent"] is not None:
                    parent = created[record["parent"]]
                    span = record["length"] / QtCore.QLineF(parent.firstVertex, parent.secondVertex).length()
                    obj = objectType(parent, record["fraction"] - span / 2, record["fraction"] + span / 2)
                else:
                    openingPosition = self.WorldToViewport(QtCore.QPointF(*record["center"]) + delta)
                    modifiers = (QtCore.Qt.KeyboardModifier.AltModifier if self.snapEnabled else
                                 QtCore.Qt.KeyboardModifier.NoModifier) if inPlace else None
                    obj = self.FindWindowPlacement(openingPosition, record["length"], openingType = objectType, modifiers = modifiers)
                    if obj is None or abs(obj.length - record["length"]) > .01:
                        valid = False
                        break
                    if inPlace and QtCore.QLineF((obj.firstVertex + obj.secondVertex) / 2, QtCore.QPointF(*record["center"])).length() > 1e-7:
                        valid = False
                        break
                fields = PlanSelectionOpeningFields(record, type(obj).__name__, obj.parentWall.width)
                for attribute, value in fields.items():
                    setattr(obj, attribute, value)
                direction = record.get("wallDirection")
                if record["parent"] is None and direction is not None:
                    target = obj.parentWall.secondVertex - obj.parentWall.firstVertex
                    reversedAlongWall = direction[0] * target.x() + direction[1] * target.y() < 0
                    fields = {name: getattr(obj, name) for name in openingFields[type(obj)]}
                    for attribute, value in OpeningOrientationChanges(fields, reversedAlongWall).items():
                        setattr(obj, attribute, value)
                created[index] = obj
                self.windows.append(obj)
            for index, obj in created.items():
                record = records[index]
                if type(record.get("measurementHidden", False)) is not bool:
                    raise ValueError("Invalid dimension visibility")
                obj.measurementHidden = record.get("measurementHidden", False)
                if isinstance(obj, Window):
                    parentLength = QtCore.QLineF(obj.parentWall.firstVertex, obj.parentWall.secondVertex).length()
                    halfSpan = obj.length / (2 * parentLength)
                    valid = valid and (isinstance(obj, PocketDoor) or halfSpan <= obj.centerFraction <= 1 - halfSpan) and self.OpeningFits(obj)
                elif isinstance(obj, Counter):
                    valid = valid and self.CounterFits(obj)
                elif isinstance(obj, Stair):
                    valid = valid and self.StairFits(obj)
                elif isinstance(obj, Furnishing):
                    valid = valid and self.FurnishingFits(obj)
                else:
                    valid = valid and self.WallFits(obj) and not any(self.JoinedObjectsOverlap(obj, other, contactTolerance = 1.0)
                                              for other in self.furnishings + [wall for wall in self.walls if isinstance(wall, (Stair, Counter))])
        except (ValueError, TypeError, KeyError, OverflowError):
            valid = False
        self.alignmentGuides = []
        if not valid:
            self.walls, self.windows, self.furnishings, self.labels = originalLists
            self.clipboardMessage.emit("Cannot paste here: objects overlap or an opening has no suitable wall.")
            self.update()
            return False
        if imported:
            self.projectFurnishingDefinitions = {**self.projectFurnishingDefinitions, **imported}
            self.furnishingDefinitions = definitions
            main = self.window()
            main.RefreshFurnishingRenderers()
            main.BuildFurnishTab(refresh = True)
        self.objectGroups.extend(tuple(created[index] for index in group) for group in payload.get("groups", []))
        self.SetSelection([(created[index], None) for index, record in enumerate(records) if record["selected"]])
        self.RecordEdit(before)
        self.setFocus()
        self.update()
        return True
