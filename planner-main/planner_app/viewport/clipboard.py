"""Portable scene selections on the system clipboard and atomic paste edits."""
from planner_app.models import AngleGuide

from planner_app.models import Elevator

import json
import math
from PySide6 import QtCore, QtWidgets
from planner_app.models import Door, Furnishing, OpenDoorway, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, SlidingDoor, MeasurementGuide, BoundaryLine, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, Window, NorthArrow, Fireplace


clipboardMimeType = "application/x-planner-selection"
from planner_app.object_schema import openingClasses as openingTypes, openingFields, ReadArrowTipSize
from planner_app.furnishing_assets import FurnishingAssetProblems


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

    def ShowClipboardError(self, message):
        self.clipboardError = message
        if message:
            self.clipboardErrorTimer.start(5000)
        else:
            self.clipboardErrorTimer.stop()
        self.update()

    def ReadClipboardSelection(self):
        mime = QtWidgets.QApplication.clipboard().mimeData()
        if mime is None or not mime.hasFormat(clipboardMimeType):
            return None
        try:
            payload = json.loads(bytes(mime.data(clipboardMimeType)).decode("utf-8"))
            if payload["version"] != 1:
                return None
            records = payload["objects"]
            if not isinstance(records, list) or not 1 <= len(records) <= 10000:
                return None
            groups = payload.get("groups", [])
            grouped = set()
            if not isinstance(groups, list):
                return None
            for group in groups:
                if not isinstance(group, list) or len(group) < 2 or any(type(index) is not int or not 0 <= index < len(records) for index in group) or len(set(group)) != len(group) or grouped.intersection(group):
                    return None
                grouped.update(group)
            points = [payload["center"]]
            checkedAssets = set()
            for record in records:
                if not isinstance(record["selected"], bool):
                    return None
                objectType = record["type"]
                if objectType in openingTypes:
                    points.append(record["center"])
                    if not math.isfinite(record["length"]) or record["length"] < 1 or not math.isfinite(record["fraction"]):
                        return None
                    parent = record["parent"]
                    if parent is not None and (type(parent) is not int or not 0 <= parent < len(records)
                                               or records[parent]["type"] != "Wall"):
                        return None
                    if objectType == "CasementWindow":
                        record.setdefault("hingeAtSecond", False)
                    record.setdefault("measurementFlipped", False)
                    if type(record["measurementFlipped"]) is not bool:
                        return None
                    flags = tuple(name for name in openingFields[openingTypes[objectType]]
                                  if name not in ("measurementFlipped", "sillDepth", "depth", "depthOffset", "material"))
                    if any(not isinstance(record[flag], bool) for flag in flags):
                        return None
                    if objectType == "SilledWindow" and (not math.isfinite(record["sillDepth"]) or record["sillDepth"] < 0):
                        return None
                    if objectType == "Fireplace" and any(type(record[name]) not in (float, int) or not math.isfinite(record[name])
                                                          for name in ("depth", "depthOffset")):
                        return None
                    if objectType == "Fireplace" and record.get("material") not in self.warningMaterialBrushes:
                        return None
                elif objectType in ("Wall", "Pillar", "Column", "Elevator", "Stair", "Counter", "Railing", "Furnishing", "Label", "NorthArrow", "Arrow", "MeasurementGuide", "BoundaryLine", "AngleGuide"):
                    points.extend((record["first"], record["second"]))
                    if not math.isfinite(record["width"]) or record["width"] < (0 if objectType in ("MeasurementGuide", "BoundaryLine", "AngleGuide") else 1e-8 if objectType == "Label" else 1):
                        return None
                    if objectType in ("MeasurementGuide", "BoundaryLine", "AngleGuide") and record["width"] != 0:
                        return None
                    if objectType in ("MeasurementGuide", "BoundaryLine", "AngleGuide"):
                        points.append(record.get("textOffset", [0, 0]))
                    if objectType == "AngleGuide":
                        points.append(record["middle"])
                    if objectType == "Label":
                        if not isinstance(record["text"], str) or len(record["text"]) > 100000:
                            return None
                        intensity = record.get("intensity", 1.0)
                        if type(intensity) not in (int, float) or not math.isfinite(intensity) or not 0 <= intensity <= 1:
                            return None
                    elif objectType == "Furnishing":
                        if not isinstance(record["definition"], str):
                            return None
                        key = record["definition"]
                        if key not in checkedAssets:
                            if self.FurnishingAssetHasErrors(key):
                                return None
                            checkedAssets.add(key)
                    elif objectType == "NorthArrow":
                        intensity = record.get("intensity", 1.0)
                        if type(intensity) not in (int, float) or not math.isfinite(intensity) or not 0 <= intensity <= 1:
                            return None
                    elif (record["material"] not in self.warningMaterialBrushes
                          or not all(math.isfinite(record[field]) for field in ("firstMiter", "secondMiter"))):
                        return None
                    if objectType == "Arrow":
                        if type(record["solidTip"]) is not bool:
                            return None
                        ReadArrowTipSize(record, record["width"])
                        intensity = record["intensity"]
                        if type(intensity) not in (int, float) or not math.isfinite(intensity) or not 0 <= intensity <= 1:
                            return None
                    if objectType == "Railing" and (type(record.get("autosize", True)) is not bool or
                            type(record.get("manualPostCount", 2)) is not int or not 2 <= record.get("manualPostCount", 2) <= 100000):
                        return None
                    if objectType == "Stair" and not isinstance(record["directionReversed"], bool):
                        return None
                    if objectType == "Stair" and (type(record.get("autosize", True)) is not bool or
                            type(record.get("manualStepCount", 1)) is not int or not 1 <= record.get("manualStepCount", 1) <= 100000):
                        return None
                else:
                    return None
            if not all(isinstance(point, list) and len(point) == 2 and all(math.isfinite(value) for value in point) for point in points):
                return None
            for record in records:
                if record["type"] not in openingTypes:
                    if record["type"] != "AngleGuide" and QtCore.QLineF(QtCore.QPointF(*record["first"]), QtCore.QPointF(*record["second"])).length() < 1:
                        return None
                elif record["parent"] is not None:
                    parent = records[record["parent"]]
                    length = QtCore.QLineF(QtCore.QPointF(*parent["first"]), QtCore.QPointF(*parent["second"])).length()
                    if length < record["length"] or not 0 <= record["fraction"] <= 1:
                        return None
            return payload if any(record["selected"] for record in records) else None
        except (ValueError, TypeError, KeyError, OverflowError):
            return None

    def CopySelection(self):
        self.CancelInteraction()
        if not self.CanCopySelection():
            if self.SelectionEntries():
                self.ShowClipboardError("Cannot copy or cut a selection containing missing or errored furnishings.")
            return False
        selected = {id(obj) for obj, index in self.SelectionEntries()}
        if not selected:
            return False
        walls = [obj for obj in self.walls if id(obj) in selected]
        wallIndices = {id(obj): index for index, obj in enumerate(walls)}
        objects = walls + [obj for obj in self.windows if id(obj) in selected or id(obj.parentWall) in wallIndices]
        objects += [obj for obj in self.furnishings if id(obj) in selected]
        objects += [obj for obj in self.labels if id(obj) in selected]
        records = []
        corners = []
        for obj in objects:
            corners.extend(self.ObjectCorners(obj))
            record = {"type": type(obj).__name__, "selected": id(obj) in selected, "measurementHidden": obj.measurementHidden}
            if isinstance(obj, Window):
                center = (obj.firstVertex + obj.secondVertex) / 2
                record.update(parent = wallIndices.get(id(obj.parentWall)), center = [center.x(), center.y()],
                              fraction = obj.centerFraction, length = obj.length)
                for attribute in openingFields[type(obj)]:
                    if hasattr(obj, attribute):
                        record[attribute] = getattr(obj, attribute)
            else:
                record.update(first = [obj.firstVertex.x(), obj.firstVertex.y()],
                              second = [obj.secondVertex.x(), obj.secondVertex.y()], width = obj.width)
                if isinstance(obj, Label):
                    record["text"] = obj.text
                    record["intensity"] = obj.intensity
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
                    if isinstance(obj, Arrow):
                        record.update(solidTip = obj.solidTip, tipSize = obj.tipSize, intensity = obj.intensity, tipSizeMode = "millimeters")
                    if isinstance(obj, Railing):
                        record.update(autosize = obj.autosize, manualPostCount = obj.manualPostCount)
                    if isinstance(obj, Stair):
                        record["directionReversed"] = obj.directionReversed
                        record.update(autosize = obj.autosize, manualStepCount = obj.manualStepCount)
            records.append(record)
        center = [(min(point.x() for point in corners) + max(point.x() for point in corners)) / 2,
                  (min(point.y() for point in corners) + max(point.y() for point in corners)) / 2]
        indices = {id(obj): index for index, obj in enumerate(objects)}
        groups = [[indices[id(obj)] for obj in group if id(obj) in indices] for group in self.objectGroups]
        payload = json.dumps({"version": 1, "center": center, "objects": records,
                              "groups": [group for group in groups if len(group) >= 2]}, allow_nan = False)
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
            if payload["version"] != 1 or not payload["objects"] or len(payload["objects"]) > 10000:
                return False
            records = payload["objects"]
            center = QtCore.QPointF(*payload["center"])
            delta = QtCore.QPointF()
            if not inPlace:
                target = self.SnapPosition(self.ViewportToWorld(position), QtWidgets.QApplication.keyboardModifiers())
                delta = target - center
            if not all(math.isfinite(value) for value in (delta.x(), delta.y())):
                return False
            created = {}
            for index, record in enumerate(records):
                if not isinstance(record["selected"], bool):
                    return False
                objectType = record["type"]
                if objectType in openingTypes:
                    continue
                first = QtCore.QPointF(*record["first"]) + delta
                second = QtCore.QPointF(*record["second"]) + delta
                width = record["width"]
                if not all(math.isfinite(value) for value in (first.x(), first.y(), second.x(), second.y(), width)):
                    return False
                minimumSize = 1e-8 if objectType == "Label" else 1
                if width < (0 if objectType in ("MeasurementGuide", "BoundaryLine", "AngleGuide") else minimumSize) or objectType != "AngleGuide" and QtCore.QLineF(first, second).length() < minimumSize:
                    return False
                if objectType == "Label":
                    obj = Label(text = record["text"], intensity = record.get("intensity", 1.0))
                    obj.firstVertex, obj.secondVertex, obj.width = first, second, width
                elif objectType == "NorthArrow":
                    obj = NorthArrow()
                    obj.intensity = record.get("intensity", 1.0)
                    obj.firstVertex, obj.secondVertex, obj.width = first, second, width
                elif objectType == "Furnishing":
                    definition = self.furnishingDefinitions.get(record["definition"], self.furnishingDefinitions["null"])
                    obj = Furnishing(definition)
                    if type(record.get("behindCounters", False)) is not bool:
                        return False
                    obj.behindCounters = record.get("behindCounters", False)
                    for field in ("flipHorizontal", "flipVertical"):
                        if type(record.get(field, False)) is not bool:
                            return False
                        setattr(obj, field, record.get(field, False))
                    obj.definitionKey = record["definition"]
                    obj.firstVertex, obj.secondVertex, obj.width = first, second, width
                elif objectType in ("Wall", "Pillar", "Column", "Elevator", "Stair", "Counter", "Railing", "Arrow", "MeasurementGuide", "BoundaryLine", "AngleGuide"):
                    if not all(math.isfinite(record[field]) for field in ("firstMiter", "secondMiter")):
                        return False
                    material = record["material"]
                    if material not in self.warningMaterialBrushes:
                        return False
                    obj = {"Wall": Wall, "Pillar": Pillar, "Column": Column, "Elevator": Elevator, "Stair": Stair, "Counter": Counter, "Railing": Railing, "Arrow": Arrow, "MeasurementGuide": MeasurementGuide, "BoundaryLine": BoundaryLine, "AngleGuide": AngleGuide}[objectType](first, second, width,
                          record["firstMiter"], record["secondMiter"], material)
                    if isinstance(obj, MeasurementGuide):
                        obj.textOffset = QtCore.QPointF(*record.get("textOffset", [0, 0]))
                    if isinstance(obj, AngleGuide):
                        obj.middleVertex = QtCore.QPointF(*record["middle"]) + delta
                    if isinstance(obj, Railing):
                        obj.autosize, obj.manualPostCount = record.get("autosize", True), record.get("manualPostCount", 2)
                    if isinstance(obj, Arrow):
                        obj.solidTip, obj.tipSize, obj.intensity = record["solidTip"], ReadArrowTipSize(record, width), record["intensity"]
                    if isinstance(obj, Stair):
                        obj.directionReversed = bool(record["directionReversed"])
                        obj.autosize, obj.manualStepCount = record.get("autosize", True), record.get("manualStepCount", 1)
                else:
                    return False
                created[index] = obj
            for record in records:
                if record["type"] in openingTypes:
                    if not math.isfinite(record["length"]) or record["length"] < 1:
                        return False
                    if not math.isfinite(record["fraction"]) or not all(math.isfinite(value) for value in record["center"]):
                        return False
                    parentIndex = record["parent"]
                    if parentIndex is not None and (parentIndex not in created or type(created[parentIndex]) is not Wall):
                        return False
        except (ValueError, TypeError, KeyError, OverflowError):
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
                for attribute in openingFields[type(obj)]:
                    if hasattr(obj, attribute):
                        value = record[attribute]
                        if attribute == "sillDepth" and (not math.isfinite(value) or value < 0):
                            raise ValueError("Invalid sill depth")
                        if attribute == "depth" and (not math.isfinite(value) or value < obj.parentWall.width):
                            raise ValueError("Invalid fireplace depth")
                        if attribute == "depthOffset" and (not math.isfinite(value) or abs(value) > (obj.depth - obj.parentWall.width) / 2 + 1e-8):
                            raise ValueError("Invalid fireplace depth offset")
                        setattr(obj, attribute, value if attribute in ("sillDepth", "depth", "depthOffset", "material") else bool(value))
                created[index] = obj
                self.windows.append(obj)
            for index, obj in created.items():
                record = records[index]
                if type(record.get("measurementHidden", False)) is not bool:
                    raise ValueError("Invalid measurement visibility")
                obj.measurementHidden = record.get("measurementHidden", False)
                if isinstance(obj, Window):
                    parentLength = QtCore.QLineF(obj.parentWall.firstVertex, obj.parentWall.secondVertex).length()
                    halfSpan = obj.length / (2 * parentLength)
                    valid = valid and halfSpan <= obj.centerFraction <= 1 - halfSpan and self.OpeningFits(obj)
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
        self.objectGroups.extend(tuple(created[index] for index in group) for group in payload.get("groups", []))
        self.SetSelection([(created[index], None) for index, record in enumerate(records) if record["selected"]])
        self.RecordEdit(before)
        self.setFocus()
        self.update()
        return True
