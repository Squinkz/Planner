"""Versioned JSON projects; decoding builds detached objects before scene replacement."""
from planner_app.models import AngleGuide, ObjectControlPoints

from planner_app.models import Elevator
import base64
import math
from pathlib import Path
from xml.etree import ElementTree
from PySide6 import QtCore, QtGui
from .models import Door, SwingingDoor, DoubleDoor, Furnishing, OpenDoorway, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, SlidingDoor, MeasurementGuide, BoundaryLine, DashedLine, SolidLine, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, RoomLabel, Window, NorthArrow, Fireplace
from .graphics.theme import wallMaterials
from .graphics.theme import gridIntensityDefaults
from .preferences import wallPresetWidths, openingDefaultSizes, miscDefaultSizes, measurementDefaults, measurementVisibilityDefaults, stairStepSizeDefaults, railingSpacingDefaults, lineworkDefaults, collisionDefaults
from .units import unitModes, measurementPrecisions
from .models import lineWeightClasses, sizingCountLimit
from .catalog_metadata import FurnishingCategories
from .geometry.reserved_doors import ReservedDoorSupportBounds
from .furnishing_records import ReadEmbeddedFurnishings, WriteEmbeddedFurnishings
from .reference_image import ValidateReferenceImage
from .export_settings import NormalizeExportSettings
from .project_settings import ReadProjectSettings, ReadEditorUi, visibilityNames, snapNames
from .record_validation import ValidateNumber, ValidateCoordinates, ValidateFlags, projectFileLimit
from .model_construction import PlanObjectConstruction, PlanProjectMemberships, PlanProjectOpening, PlanCompoundFallback
from .model_factory import ConstructDetachedObject, ConstructProjectOpening


from .object_schema import openingClasses, openingFields, ReadArrowTipSize



def ReadProjectBytes(path):
    with Path(path).open("rb") as source:
        payload = source.read(projectFileLimit + 1)
    if len(payload) > projectFileLimit:
        raise ValueError("The project file exceeds the 64 MiB limit.")
    return payload


def EncodeObjectRecord(obj, indices, values = None):
    """Shared project/history record schema; snapshots supply saved field values."""
    record = {"type": type(obj).__name__, "id": obj.objectId, "measurementHidden": obj.measurementHidden}
    if hasattr(obj, "originalMaterial"):
        record["originalMaterial"] = obj.originalMaterial
    if getattr(obj, "geometryIssues", ()):
        record["geometryIssues"] = list(obj.geometryIssues)
    if values is not None:
        record.update(values)
        if isinstance(obj, Furnishing) and not isinstance(obj, (Label, NorthArrow)):
            record["definition"] = getattr(obj, "definitionKey", obj.definition["key"])
        if isinstance(obj, Arrow):
            record["tipSizeMode"] = "millimeters"
        return record
    if isinstance(obj, Window):
        record.update(parent = indices[id(obj.parentWall)], center = obj.centerFraction, length = obj.length)
        for name in openingFields[type(obj)]:
            if hasattr(obj, name):
                record[name] = getattr(obj, name)
    else:
        record.update(first = [obj.firstVertex.x(), obj.firstVertex.y()],
                      second = [obj.secondVertex.x(), obj.secondVertex.y()], width = obj.width)
        if isinstance(obj, Label):
            record["text"] = obj.text
            record["intensity"] = obj.intensity
            if isinstance(obj, RoomLabel) and obj.unitsOverride is not None:
                record["unitsOverride"] = obj.unitsOverride
        elif isinstance(obj, NorthArrow):
            record["intensity"] = obj.intensity
        elif isinstance(obj, Furnishing):
            record["definition"] = getattr(obj, "definitionKey", obj.definition["key"])
            record["behindCounters"] = obj.behindCounters
            record["flipHorizontal"] = obj.flipHorizontal
            record["flipVertical"] = obj.flipVertical
        else:
            record.update(material = obj.material, firstMiter = obj.firstMiter, secondMiter = obj.secondMiter)
            if isinstance(obj, AngleGuide):
                record.update(middle = [obj.middleVertex.x(), obj.middleVertex.y()])
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
    return record


def EncodeScene(viewport):
    objects = viewport.walls + viewport.windows + viewport.furnishings + viewport.labels
    indices = {id(obj): index for index, obj in enumerate(objects)}
    records = [EncodeObjectRecord(obj, indices) for obj in objects]
    from .furnishing_parts import FurnishingParts
    from .furnishing_limits import FurnishingExpansionSizes, sceneExpansionLimit
    sizes = FurnishingExpansionSizes(obj.definition for obj in viewport.furnishings if type(obj) is Furnishing)
    if len(objects) + sum(sizes[id(obj.definition)] - 1 for obj in viewport.furnishings if type(obj) is Furnishing) > sceneExpansionLimit:
        raise ValueError("The scene expands to more than 100,000 objects.")

    def EncodeChildren(obj, ancestors):
        if not obj.definition.get("components"):
            return None
        key = obj.definition["key"]
        if key in ancestors or len(ancestors) >= 64:
            raise ValueError("Furnishing components contain circular or excessively nested references.")
        children = []
        for part in FurnishingParts(obj):
            record = EncodeObjectRecord(part, {})
            record.pop("id")
            nested = EncodeChildren(part, ancestors + [key])
            if nested:
                record["children"] = nested
            children.append(record)
        return children

    for obj, record in zip(objects, records):
        if type(obj) is Furnishing:
            children = EncodeChildren(obj, [])
            if children:
                record["children"] = children
    groups = sorted(sorted(indices[id(obj)] for obj in group if id(obj) in indices)
                    for group in viewport.objectGroups)
    hidden = sorted(indices[id(obj)] for obj in viewport.hiddenObjects if id(obj) in indices)
    return {"objects": records, "groups": groups, "hidden": hidden}


def EncodeUsedFurnishings(viewport, includeHistory = True):
    objects = list(viewport.furnishings)
    history = list(getattr(viewport, "undoHistory", ())) + list(getattr(viewport, "redoHistory", ())) if includeHistory else ()
    for edit in history:
        objects.extend(entry[0] for change in edit.changes for entry in change[3:] if entry is not None and change[0] == 5)
    return EncodeFurnishingDefinitions([obj.definition for obj in objects
        if type(obj) is Furnishing and obj.definition.get("isUser", False)])


def EncodeFurnishingDefinitions(definitions, includeBuiltIns = False):
    from .svg_safety import ValidateFurnishingSvg
    return WriteEmbeddedFurnishings(definitions, ValidateFurnishingSvg, includeBuiltIns = includeBuiltIns)


def ResolveProjectColor(value):
    color = QtGui.QColor(value)
    if not color.isValid():
        raise ValueError("Invalid export color.")
    return color.name()


def ValidateProjectSettings(settings, validatedImages = None, collisions = None):
    return ReadProjectSettings(settings, wallMaterials, gridIntensityDefaults, ResolveProjectColor,
                               lambda record: ValidateReferenceImage(record, validatedImages), collisions = collisions)


def ValidatePoint(value):
    return QtCore.QPointF(*ValidateCoordinates(value))


def ValidateEditorUi(ui, recovery = False, tabCount = None, objectsById = None):
    def SelectionLimit(objectId):
        obj = objectsById.get(objectId)
        if obj is None:
            return None
        return len(ObjectControlPoints(obj)), isinstance(obj, MeasurementGuide)

    ReadEditorUi(ui, recovery = recovery, tabCount = tabCount,
                 selectionLimit = SelectionLimit if objectsById is not None else None)


def DecodeFurnishingDefinitions(embedded, definitions):
    from .svg_safety import ValidateFurnishingSvg
    return ReadEmbeddedFurnishings(embedded, definitions, ValidateFurnishingSvg)


def DecodeProject(data, definitions, validatePlacement = True, validatedImages = None):
    if not isinstance(data, dict) or data.get("format") != "Planner Project" or type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("This is not a supported Planner project.")
    if not isinstance(data.get("settings"), dict) or not isinstance(data.get("scene"), dict):
        raise ValueError("The project contains invalid settings or scene data.")
    projectDefinitions = DecodeFurnishingDefinitions(data.get("furnishingDefinitions", {}), definitions)
    definitions = {**definitions, **projectDefinitions}
    collisions = ValidateFlags(data["settings"].get("collisionSettings", collisionDefaults), tuple(collisionDefaults))
    scene = data["scene"]
    records = scene["objects"]
    if not isinstance(records, list) or len(records) > 100000:
        raise ValueError("The project contains too many objects or an invalid object list.")
    created = {}
    walls, windows, furnishings, labels = [], [], [], []
    categories = {"walls": walls, "furnishings": furnishings, "labels": labels}
    nativeDistance = lambda x, y: QtCore.QLineF(0.0, 0.0, x, y).length()
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("type"), str):
            raise ValueError("The project contains an invalid object record.")
        kind = record["type"]
        if kind in openingClasses:
            continue
        plan = PlanObjectConstruction(record, wallMaterials, unitModes, lineWeightClasses, distance = nativeDistance)
        obj = ConstructDetachedObject(plan, definitions)
        categories[plan.category].append(obj)
        created[index] = obj
    from .furnishing_limits import FurnishingExpansionSizes, sceneExpansionLimit
    sizes = FurnishingExpansionSizes(obj.definition for obj in furnishings if type(obj) is Furnishing)
    if len(records) + sum(sizes[id(obj.definition)] - 1 for obj in furnishings if type(obj) is Furnishing) > sceneExpansionLimit:
        raise ValueError("The scene expands to more than 100,000 objects.")
    parkingBounds = {}
    for index, record in enumerate(records):
        kind = record["type"]
        if kind not in openingClasses:
            continue
        parentIndex = record["parent"]
        if type(parentIndex) is not int or parentIndex not in created or type(created[parentIndex]) is not Wall:
            raise ValueError("A door or window has no valid parent wall.")
        parent = created[parentIndex]
        bounds = (0, 1)
        if kind in ("BarnDoor", "PocketDoor"):
            if parentIndex not in parkingBounds:
                parkingBounds[parentIndex] = ReservedDoorSupportBounds((parent.firstVertex.x(), parent.firstVertex.y()),
                    (parent.secondVertex.x(), parent.secondVertex.y()),
                    (((wall.firstVertex.x(), wall.firstVertex.y()), (wall.secondVertex.x(), wall.secondVertex.y()))
                     for wall in walls if type(wall) is Wall))
            bounds = parkingBounds[parentIndex]
        plan = PlanProjectOpening(record, QtCore.QLineF(parent.firstVertex, parent.secondVertex).length(),
                                  parent.width, parent.material, wallMaterials, validatePlacement = validatePlacement, parkingBounds = bounds)
        obj = ConstructProjectOpening(plan, parent)
        windows.append(obj)
        created[index] = obj
    if validatePlacement:
        parentIntervals = {}
        for opening in windows:
            if "opening_overlap" not in opening.geometryIssues:
                parentIntervals.setdefault(id(opening.parentWall), []).append((opening.firstFraction, opening.secondFraction))
        for intervals in parentIntervals.values():
            previousEnd = -math.inf
            for low, high in sorted(intervals):
                if min(high, previousEnd) - low > 1e-8:
                    raise ValueError("Doors or windows overlap on their parent wall.")
                previousEnd = max(previousEnd, high)
    from .viewport.geometry import FootprintGeometry
    geometry = FootprintGeometry(1.0)
    geometry.collisionSettings = collisions
    if validatePlacement and windows:
        from .geometry.spatial_index import BoundsIndex
        wallIndex = BoundsIndex(2000)
        for wall in walls:
            if type(wall) is Wall:
                bounds = geometry.ObjectFootprint(wall)[0]
                wallIndex.Insert((bounds.left(), bounds.top(), bounds.right(), bounds.bottom()), wall)
        for opening in windows:
            if "opening_obstruction" in getattr(opening, "geometryIssues", ()):
                continue
            bounds = geometry.ObjectFootprint(opening)[0].adjusted(-1, -1, 1, 1)
            candidates = wallIndex.Query((bounds.left(), bounds.top(), bounds.right(), bounds.bottom()))
            if any(geometry.OpeningWallObstructs(opening, wall, walls = walls, joined = False) for wall in candidates):
                raise ValueError("A door or window is obstructed by another wall.")
    assignments, groupIndices, hiddenIndices, objectIds = PlanProjectMemberships(records, created.keys(), scene)
    for index, objectId in assignments:
        created[index].objectId = objectId
    groups = [tuple(created[index] for index in group) for group in groupIndices]
    hiddenObjects = [created[index] for index in hiddenIndices]
    replacements = {}
    expandedCount = len(created)
    nextObjectId = max(objectIds, default = 0) + 1

    for index, obj in created.items():
        record = records[index]
        if type(obj) is Furnishing and obj.definitionKey not in definitions and "children" in record:
            plans, expandedCount, nextObjectId = PlanCompoundFallback(record, definitions, expandedCount, nextObjectId,
                                                                      distance = nativeDistance)
            replacements[id(obj)] = [ConstructDetachedObject(plan, definitions) for plan in plans]
    if replacements:
        furnishings = [part for obj in furnishings for part in replacements.get(id(obj), (obj,))]
        groups = [tuple(part for obj in group for part in replacements.get(id(obj), (obj,))) for group in groups]
        hiddenObjects = [part for obj in hiddenObjects for part in replacements.get(id(obj), (obj,))]
    settings = data["settings"]
    flags = ValidateProjectSettings(settings, validatedImages, collisions)
    view = data.get("view", {"zoom": 1, "pan": [0, 0]})
    view = {"zoom": ValidateNumber(view["zoom"], minimum = 1e-6, maximum = 1e6), "pan": ValidatePoint(view["pan"])}
    ui = data.get("ui")
    if ui is not None:
        ValidateEditorUi(ui)
    flags["editorUi"] = ui
    flags["embeddedFurnishings"] = projectDefinitions
    if "history" in data and not replacements:
        from .project_history import DecodeHistory
        # Undo may retain an obstructed scene that was subsequently repaired.
        # Historical geometry must remain editable without rejecting the current project.
        from types import SimpleNamespace
        current = SimpleNamespace(walls = walls, windows = windows, furnishings = furnishings, labels = labels,
                                  objectGroups = groups, hiddenObjects = hiddenObjects,
                                  selectedWall = None, selectedVertex = None, SelectionEntries = lambda: [])
        try:
            flags["history"] = DecodeHistory(data["history"], settings, definitions, current)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
            # Optional undo data must never prevent a valid project from opening.
            flags["history"] = {"undo": [], "redo": []}
    from .activity_records import DecodeActivityLog
    flags["activityLog"] = DecodeActivityLog(data.get("activityLog"))
    return walls, windows, furnishings, groups, hiddenObjects, flags, view, labels
