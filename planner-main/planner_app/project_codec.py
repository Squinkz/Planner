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
from .models import lineWeightClasses
from .catalog import FurnishingCategories
from .reference_image import ValidateReferenceImage


from .object_schema import openingClasses, openingFields, ReadArrowTipSize
visibilityNames = ("World", "Walls", "Doors", "Windows", "Fireplaces", "Elevators", "Stairs", "Counters", "Railings", "Furnishings", "Labels", "Arrows", "Measurement guides", "Boundary lines", "Dashed lines", "Solid lines", "North arrows")
snapNames = ("grid", "vertices", "corners", "midpoints", "alignment")
projectFileLimit = 64 * 1024 * 1024


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
    embedded = {}
    pending = [(definition["key"], definition) for definition in definitions]
    while pending:
        key, definition = pending.pop()
        if key in embedded:
            continue
        graphic = definition.get("graphicData") or Path(definition["imagePath"]).read_bytes()
        from .svg_safety import ValidateFurnishingSvg
        ValidateFurnishingSvg(graphic)
        categories = definition.get("categories", [definition["category"]])
        embedded[key] = {"name": definition["name"], "category": categories if len(categories) > 1 else categories[0],
                         "keywords": list(definition.get("keywords", [])),
                         "width": definition["width"], "length": definition["length"],
                         "svg": bytes(graphic).decode("utf-8-sig")}
        if definition.get("components"):
            embedded[key]["compoundCenter"] = list(definition["compoundCenter"])
            embedded[key]["components"] = []
            for component in definition["components"]:
                child = component["definition"]
                embedded[key]["components"].append({"definition": component.get("definitionKey", child["key"]),
                    **{field: component[field] for field in ("x", "y", "angle", "width", "length", "zIndex")},
                    **{field: component.get(field, False) for field in ("flipHorizontal", "flipVertical")},
                    **({"fixedSize": True} if component.get("fixedSize", False) else {})})
                if includeBuiltIns or child.get("isUser", False):
                    pending.append((child["key"], child))
    return embedded


def ValidateNumber(value, minimum = -1e12, maximum = 1e12):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("The project contains an invalid numeric value.")
    return float(value)


def ValidatePoint(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("The project contains an invalid position.")
    return QtCore.QPointF(ValidateNumber(value[0]), ValidateNumber(value[1]))


def ValidateFlags(values, names):
    if not isinstance(values, dict) or any(type(values.get(name)) is not bool for name in names):
        raise ValueError("The project contains invalid option settings.")
    return {name: values[name] for name in names}


def ValidateEditorUi(ui, recovery = False, tabCount = None, objectsById = None):
    if not isinstance(ui, dict):
        raise ValueError("Invalid panel state.")
    # Window placement belongs only to app recovery. Ignore legacy project fields.
    if recovery:
        if not isinstance(ui.get("geometry"), str) or len(ui["geometry"]) > 10000:
            raise ValueError("Invalid window state.")
        base64.b64decode(ui["geometry"], validate = True)
        if "maximized" in ui and type(ui["maximized"]) is not bool:
            raise ValueError("Invalid maximized state.")
        if "size" in ui and (not isinstance(ui["size"], list) or len(ui["size"]) != 2 or
                             any(type(size) is not int or not 200 <= size <= 100000 for size in ui["size"])):
            raise ValueError("Invalid window size.")
    for name in ("mainSplitter", "propertiesSplitter"):
        if (not isinstance(ui.get(name), list) or len(ui[name]) != 2 or
                any(type(size) is not int or not 0 <= size <= 100000 for size in ui[name])):
            raise ValueError("Invalid panel sizes.")
    if type(ui.get("propertiesCollapsed", False if recovery else None)) is not bool:
        raise ValueError("Invalid properties panel state.")
    height = ui.get("propertiesRestoreHeight")
    if height is not None and (type(height) is not int or not 1 <= height <= 100000):
        raise ValueError("Invalid properties restore height.")
    sections = ui.get("exportSections", {})
    if (not isinstance(sections, dict) or set(sections) - {"Canvas", "Border", "Grid", "Line Weight", "Measurements", "Vignette", "Composite", "Visibility"}
            or any(type(value) is not bool for value in sections.values())):
        raise ValueError("Invalid export section state.")
    if recovery:
        scroll = ui.get("scroll")
        if not isinstance(scroll, list) or any(type(value) is not int or not 0 <= value <= 100000 for value in scroll):
            raise ValueError("Invalid recovered scroll positions.")
        if type(ui.get("tab")) is not int or not 0 <= ui["tab"] < tabCount:
            raise ValueError("Invalid recovered tab.")
        if type(ui.get("treeScroll", 0)) is not int or not 0 <= ui.get("treeScroll", 0) <= 100000:
            raise ValueError("Invalid recovered tree scroll position.")
        expanded = ui.get("expanded")
        if not isinstance(expanded, dict) or any(type(value) is not bool for value in expanded.values()):
            raise ValueError("Invalid recovered visibility tree.")
        selection = ui.get("selection")
        if not isinstance(selection, list) or any(not isinstance(entry, list) or len(entry) != 2 or
                type(entry[0]) is not int or (entry[1] is not None and (type(entry[1]) is not int or entry[1] not in (0, 1, 2, 3)))
                for entry in selection):
            raise ValueError("Invalid recovered selection.")
        if objectsById is not None:
            for objectId, index in selection:
                obj = objectsById.get(objectId)
                if obj is None or index is None:
                    continue  # Missing IDs retain the loader's existing skip behavior.
                if index >= len(ObjectControlPoints(obj)) and not (index == 3 and isinstance(obj, MeasurementGuide)):
                    raise ValueError("Invalid recovered selection for object type.")
        if ui.get("rotationObject") is not None and type(ui["rotationObject"]) is not int:
            raise ValueError("Invalid recovered furnishing handles.")


def DecodeFurnishingDefinitions(embedded, definitions):
    if not isinstance(embedded, dict) or len(embedded) > 100000:
        raise ValueError("Invalid embedded furnishing definitions.")
    projectDefinitions = {}
    for key, record in embedded.items():
        if not isinstance(key, str) or not key or not isinstance(record, dict):
            raise ValueError("Invalid embedded furnishing key.")
        if (any(not isinstance(record.get(field), str) or not record[field] for field in ("name", "svg"))
                or not isinstance(record.get("category"), (str, list)) or not record["category"]):
            raise ValueError("Invalid embedded furnishing metadata.")
        categories = FurnishingCategories(record["category"])
        keywords = record.get("keywords", [])
        if not isinstance(keywords, list) or any(not isinstance(word, str) for word in keywords):
            raise ValueError("Invalid embedded furnishing keywords.")
        try:
            from .svg_safety import ValidateFurnishingSvg
            root = ValidateFurnishingSvg(record["svg"])
        except (ElementTree.ParseError, ValueError) as error:
            raise ValueError("Invalid embedded furnishing SVG.") from error
        if root.tag not in ("svg", "{http://www.w3.org/2000/svg}svg"):
            raise ValueError("An embedded furnishing graphic must be SVG.")
        definition = {"key": key, "name": record["name"], "category": categories[0], "categories": categories, "keywords": list(keywords),
                      "width": ValidateNumber(record.get("width"), minimum = 1e-8, maximum = 1e12),
                      "length": ValidateNumber(record.get("length"), minimum = 1e-8, maximum = 1e12),
                      "graphicData": record["svg"].encode("utf-8"), "imagePath": None, "iconPath": None,
                      "image": None, "icon": None, "inherits": None, "sourcePath": None, "isUser": True,
                      "isEmbedded": True}
        definition["searchText"] = " ".join([definition["name"]] + categories + keywords).casefold()
        projectDefinitions[key] = definition
    # Embedded artwork is authoritative for this project, including keys that
    # have since become built-in. Keep the installation's catalogue unchanged.
    definitions = {**definitions, **projectDefinitions}

    def ResolveComponents(key, ancestors):
        if key in ancestors or len(ancestors) >= 64:
            raise ValueError("Embedded furnishing components contain circular or excessively nested references.")
        definition = projectDefinitions[key]
        if "components" in definition or "components" not in embedded[key]:
            return
        components = embedded[key]["components"]
        if not isinstance(components, list) or not components or len(components) > 100000:
            raise ValueError("Invalid embedded furnishing components.")
        center = ValidatePoint(embedded[key].get("compoundCenter"))
        resolved = []
        for component in components:
            if not isinstance(component, dict) or not isinstance(component.get("definition"), str):
                raise ValueError("Invalid embedded furnishing component reference.")
            childKey = component["definition"]
            if childKey in projectDefinitions:
                ResolveComponents(childKey, ancestors + [key])
            resolved.append({"definition": definitions.get(childKey, definitions["null"]), "definitionKey": childKey,
                **{field: ValidateNumber(component.get(field), minimum = 1e-8 if field in ("width", "length") else -1e12)
                   for field in ("x", "y", "angle", "width", "length", "zIndex")},
                **ValidateFlags({"flipHorizontal": False, "flipVertical": False, "fixedSize": False, **component},
                                ("flipHorizontal", "flipVertical", "fixedSize"))})
        definition["compoundCenter"] = (center.x(), center.y())
        definition["components"] = resolved

    for key in projectDefinitions:
        ResolveComponents(key, [])
    from .furnishing_limits import FurnishingExpansionSizes
    FurnishingExpansionSizes(projectDefinitions.values())
    return projectDefinitions


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
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("type"), str):
            raise ValueError("The project contains an invalid object record.")
        kind = record["type"]
        if kind in openingClasses:
            continue
        first, second = ValidatePoint(record["first"]), ValidatePoint(record["second"])
        width = ValidateNumber(record["width"], minimum = 0 if kind in ("MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide") else 1e-8 if kind in ("Label", "RoomLabel") else 1, maximum = 1e9)
        if kind in ("MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide") and width != 0:
            raise ValueError("Dimension guides cannot have a width.")
        if kind != "AngleGuide" and QtCore.QLineF(first, second).length() < 1e-8:
            raise ValueError("An object has zero length.")
        if kind in ("Label", "RoomLabel"):
            if not isinstance(record["text"], str) or len(record["text"]) > 100000:
                raise ValueError("A label contains invalid text.")
            obj = (RoomLabel if kind == "RoomLabel" else Label)(text = record["text"], intensity = ValidateNumber(record.get("intensity", 1.0), minimum = 0, maximum = 1))
            if kind == "RoomLabel":
                mode = record.get("unitsOverride")
                if mode is not None and mode not in unitModes:
                    raise ValueError("Invalid room label units.")
                obj.unitsOverride = mode
            obj.firstVertex, obj.secondVertex, obj.width = first, second, width
            labels.append(obj)
        elif kind == "NorthArrow":
            obj = NorthArrow()
            obj.intensity = ValidateNumber(record.get("intensity", 1.0), minimum = 0, maximum = 1)
            obj.firstVertex, obj.secondVertex, obj.width = first, second, width
            furnishings.append(obj)
        elif kind == "Furnishing":
            if not isinstance(record["definition"], str):
                raise ValueError("A furnishing definition is invalid.")
            obj = Furnishing(definitions.get(record["definition"], definitions["null"]))
            obj.behindCounters = ValidateFlags({"behindCounters": False, **record}, ("behindCounters",))["behindCounters"]
            for field in ("flipHorizontal", "flipVertical"):
                setattr(obj, field, ValidateFlags({field: False, **record}, (field,))[field])
            obj.definitionKey = record["definition"]
            obj.firstVertex, obj.secondVertex, obj.width = first, second, width
            furnishings.append(obj)
        elif kind in ("Wall", "Pillar", "Column", "Elevator", "Stair", "Counter", "Railing", "Arrow", "MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide"):
            if record["material"] not in wallMaterials:
                raise ValueError("A wall material is unknown.")
            cls = {"Wall": Wall, "Pillar": Pillar, "Column": Column, "Elevator": Elevator, "Stair": Stair, "Counter": Counter, "Railing": Railing, "Arrow": Arrow, "MeasurementGuide": MeasurementGuide, "BoundaryLine": BoundaryLine, "DashedLine": DashedLine, "SolidLine": SolidLine, "AngleGuide": AngleGuide}[kind]
            obj = cls(first, second, width, ValidateNumber(record["firstMiter"], minimum = 0, maximum = 1),
                      ValidateNumber(record["secondMiter"], minimum = 0, maximum = 1), record["material"])
            if isinstance(obj, MeasurementGuide):
                obj.textOffset = ValidatePoint(record.get("textOffset", [0, 0]))
            if isinstance(obj, DashedLine):
                weight = record.get("weightClass", "Objects")
                if not isinstance(weight, str) or weight not in lineWeightClasses:
                    raise ValueError("Invalid annotation line weight class.")
                obj.weightClass = weight
            if isinstance(obj, AngleGuide):
                obj.middleVertex = ValidatePoint(record["middle"])
            if isinstance(obj, Stair):
                obj.directionReversed = ValidateFlags(record, ("directionReversed",))["directionReversed"]
                autosize, count = record.get("autosize", True), record.get("manualStepCount", 1)
                if type(autosize) is not bool or type(count) is not int or not 1 <= count <= 100000:
                    raise ValueError("A stair contains invalid step settings.")
                obj.autosize, obj.manualStepCount = autosize, count
            if isinstance(obj, Railing):
                autosize, count = record.get("autosize", True), record.get("manualPostCount", 2)
                if type(autosize) is not bool or type(count) is not int or not 2 <= count <= 100000:
                    raise ValueError("A railing contains invalid post settings.")
                obj.autosize, obj.manualPostCount = autosize, count
            if isinstance(obj, Arrow):
                obj.solidTip = ValidateFlags(record, ("solidTip",))["solidTip"]
                obj.directionReversed = ValidateFlags({"directionReversed": False, **record}, ("directionReversed",))["directionReversed"]
                obj.tipSize = ReadArrowTipSize(record, obj.width)
                obj.intensity = ValidateNumber(record["intensity"], minimum = 0, maximum = 1)
            walls.append(obj)
        else:
            raise ValueError(f"Unknown object type: {kind}")
        obj.measurementHidden = ValidateFlags({"measurementHidden": False, **record}, ("measurementHidden",))["measurementHidden"]
        if isinstance(record.get("originalMaterial"), str):
            obj.originalMaterial = record["originalMaterial"]
        created[index] = obj
    from .furnishing_limits import FurnishingExpansionSizes, sceneExpansionLimit
    sizes = FurnishingExpansionSizes(obj.definition for obj in furnishings if type(obj) is Furnishing)
    if len(records) + sum(sizes[id(obj.definition)] - 1 for obj in furnishings if type(obj) is Furnishing) > sceneExpansionLimit:
        raise ValueError("The scene expands to more than 100,000 objects.")
    for index, record in enumerate(records):
        kind = record["type"]
        if kind not in openingClasses:
            continue
        parentIndex = record["parent"]
        if type(parentIndex) is not int or parentIndex not in created or type(created[parentIndex]) is not Wall:
            raise ValueError("A door or window has no valid parent wall.")
        parent = created[parentIndex]
        from .geometry_recovery import geometryIssueNames
        issues = record.get("geometryIssues", [])
        if not isinstance(issues, list) or any(not isinstance(code, str) or code not in geometryIssueNames for code in issues):
            raise ValueError("Invalid geometry highlight flags.")
        center = ValidateNumber(record["center"], minimum = -1e12 if "opening_bounds" in issues else 0,
                                maximum = 1e12 if "opening_bounds" in issues else 1)
        length = ValidateNumber(record["length"], minimum = 1, maximum = 1e9)
        span = length / QtCore.QLineF(parent.firstVertex, parent.secondVertex).length()
        if validatePlacement and "opening_bounds" not in issues and (center - span / 2 < -1e-8 or center + span / 2 > 1 + 1e-8):
            raise ValueError("A door or window extends beyond its parent wall.")
        obj = openingClasses[kind](parent, center - span / 2, center + span / 2)
        obj.centerFraction, obj.length = center, length
        obj.geometryIssues = tuple(issues)
        measurementFlipped = record.get("measurementFlipped", False)
        if type(measurementFlipped) is not bool:
            raise ValueError("An opening has an invalid dimension flip value.")
        obj.measurementFlipped = measurementFlipped
        for name in openingFields[type(obj)]:
            if name in ("measurementFlipped", "sillDepth", "depth", "depthOffset", "material", "wellDepth"):
                continue
            if hasattr(obj, name):
                if name in ("windowWell", "wellDashed"):
                    setattr(obj, name, ValidateFlags({name: False, **record}, (name,))[name])
                    continue
                if kind == "CasementWindow" and name == "hingeAtSecond" and name not in record:
                    continue
                setattr(obj, name, ValidateFlags(record, (name,))[name])
        if isinstance(obj, SilledWindow):
            obj.sillDepth = ValidateNumber(record["sillDepth"], minimum = 0)
        if "wellDepth" in openingFields[type(obj)]:
            obj.wellDepth = ValidateNumber(record.get("wellDepth", 600.0), minimum = 1, maximum = 1e9)
        if isinstance(obj, Fireplace):
            obj.material = record.get("material", parent.material)
            if obj.material not in wallMaterials:
                raise ValueError("A fireplace material is unknown.")
            depth = ValidateNumber(record["depth"], minimum = parent.width if validatePlacement and "fireplace_bounds" not in issues else 1, maximum = 1e9)
            obj.manualDepth = depth
            limit = (obj.depth - parent.width) / 2
            obj.manualDepthOffset = ValidateNumber(record["depthOffset"], minimum = -limit if validatePlacement and "fireplace_bounds" not in issues else -1e12,
                                                  maximum = limit if validatePlacement and "fireplace_bounds" not in issues else 1e12)
        windows.append(obj)
        obj.measurementHidden = ValidateFlags({"measurementHidden": False, **record}, ("measurementHidden",))["measurementHidden"]
        if isinstance(record.get("originalMaterial"), str):
            obj.originalMaterial = record["originalMaterial"]
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
            if any(wall is not opening.parentWall and geometry.ObjectsOverlap(opening, wall, contactTolerance = 1.0) for wall in candidates):
                raise ValueError("A door or window is obstructed by another wall.")
    objectIds = set()
    for index, obj in created.items():
        objectId = records[index].get("id")
        if objectId is not None:
            if type(objectId) is not int or objectId < 1 or objectId in objectIds:
                raise ValueError("The project contains invalid or duplicate object IDs.")
            objectIds.add(objectId)
            obj.objectId = objectId
    groups = []
    grouped = set()
    if not isinstance(scene["groups"], list) or not isinstance(scene["hidden"], list):
        raise ValueError("The project contains invalid groups or hidden objects.")
    for group in scene["groups"]:
        if (not isinstance(group, list) or len(group) < 2 or any(type(index) is not int or index not in created for index in group)
                or len(set(group)) != len(group) or grouped.intersection(group)):
            raise ValueError("The project contains invalid group membership.")
        grouped.update(group)
        groups.append(tuple(created[index] for index in group))
    hidden = scene["hidden"]
    if any(type(index) is not int or index not in created for index in hidden) or len(set(hidden)) != len(hidden):
        raise ValueError("The project contains invalid hidden objects.")
    hiddenObjects = [created[index] for index in hidden]
    replacements = {}
    expandedCount = len(created)
    nextObjectId = max(objectIds, default = 0) + 1

    def DecodeChildren(record, depth):
        nonlocal expandedCount, nextObjectId
        if depth >= 64 or not isinstance(record, dict) or record.get("type") != "Furnishing" or not isinstance(record.get("definition"), str):
            raise ValueError("Invalid compound furnishing fallback.")
        first, second = ValidatePoint(record.get("first")), ValidatePoint(record.get("second"))
        width = ValidateNumber(record.get("width"), minimum = 1, maximum = 1e9)
        if QtCore.QLineF(first, second).length() < 1e-8:
            raise ValueError("A compound child has zero length.")
        key = record["definition"]
        if key not in definitions and "children" in record:
            children = record["children"]
            if not isinstance(children, list) or not children or len(children) > 100000:
                raise ValueError("Invalid compound furnishing children.")
            return [part for child in children for part in DecodeChildren(child, depth + 1)]
        expandedCount += 1
        if expandedCount > 100000:
            raise ValueError("Compound fallback contains too many objects.")
        part = Furnishing(definitions.get(key, definitions["null"]))
        part.definitionKey = key
        part.behindCounters = ValidateFlags({"behindCounters": False, **record}, ("behindCounters",))["behindCounters"]
        for field in ("flipHorizontal", "flipVertical"):
            setattr(part, field, ValidateFlags({field: False, **record}, (field,))[field])
        part.measurementHidden = ValidateFlags({"measurementHidden": False, **record}, ("measurementHidden",))["measurementHidden"]
        part.firstVertex, part.secondVertex, part.width = first, second, width
        part.objectId = nextObjectId
        nextObjectId += 1
        return [part]

    for index, obj in created.items():
        record = records[index]
        if type(obj) is Furnishing and obj.definitionKey not in definitions and "children" in record:
            replacements[id(obj)] = DecodeChildren(record, 0)
    if replacements:
        furnishings = [part for obj in furnishings for part in replacements.get(id(obj), (obj,))]
        groups = [tuple(part for obj in group for part in replacements.get(id(obj), (obj,))) for group in groups]
        hiddenObjects = [part for obj in hiddenObjects for part in replacements.get(id(obj), (obj,))]
    settings = data["settings"]
    flags = ValidateFlags(settings, ("snapEnabled", "connectedVertices", "connectedObjects", "groupMode", "showGrid", "showMeasurements"))
    flags["collisionSettings"] = collisions
    flags["localTransforms"] = ValidateFlags({"localTransforms": False, **settings}, ("localTransforms",))["localTransforms"]
    ignored = settings.get("ignoredPotentialIssues", [])
    if (not isinstance(ignored, list) or len(ignored) > 100000
            or any(not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
                   for value in ignored)):
        raise ValueError("Invalid ignored potential issue records.")
    flags["ignoredPotentialIssues"] = list(dict.fromkeys(ignored))
    snap = settings["snap"]
    if isinstance(snap, dict) and "corners" not in snap:
        # Older projects used one switch for both kinds of target.
        snap = {**snap, "corners": snap.get("vertices", True)}
    flags["snap"] = ValidateFlags(snap, snapNames)
    flags["visibility"] = ValidateFlags({"Elevators": True, "Fireplaces": True, "North arrows": True, "Railings": True, "Labels": True, "Counters": True, "Arrows": True, "Measurement guides": True, "Boundary lines": True, "Dashed lines": True, "Solid lines": True, **settings["visibility"]}, visibilityNames)
    if flags["snapEnabled"] and not any(flags["snap"].values()):
        raise ValueError("Snapping is enabled without any snap options.")
    flags["wallWidth"] = ValidateNumber(settings["wallWidth"], minimum = 1)
    if settings["wallMaterial"] not in wallMaterials:
        raise ValueError("The new wall settings are invalid.")
    flags["wallMaterial"] = settings["wallMaterial"]
    flags["wallShape"] = settings.get("wallShape", "line")
    if flags["wallShape"] not in ("line", "square", "circle"):
        raise ValueError("Unknown wall tool shape.")
    if settings["doorType"] not in ("Door", "SlidingDoor", "PocketDoor", "BarnDoor", "BifoldDoor", "OpenDoorway", "SwingingDoor", "DoubleDoor") or settings["windowType"] not in ("Window", "SilledWindow", "CasementWindow", "AwningWindow", "DoubleCasementWindow"):
        raise ValueError("The active door/window type is unknown.")
    flags["doorType"], flags["windowType"] = settings["doorType"], settings["windowType"]
    build = settings.get("buildSettings", {"wallWidths": list(wallPresetWidths), "openingSizes": openingDefaultSizes})
    if not isinstance(build, dict) or not isinstance(build.get("wallWidths"), list) or len(build["wallWidths"]) != 4:
        raise ValueError("The project contains invalid default wall sizes.")
    if not isinstance(build.get("openingSizes"), dict):
        raise ValueError("The project contains invalid default opening sizes.")
    miscSizes = build.get("miscSizes", miscDefaultSizes)
    if isinstance(miscSizes, dict):
        miscSizes = {"Elevator": miscDefaultSizes["Elevator"], "Fireplace": miscDefaultSizes["Fireplace"], "Column": miscDefaultSizes["Column"], **miscSizes}
    if not isinstance(miscSizes, dict) or set(miscSizes) != set(miscDefaultSizes):
        raise ValueError("The project contains invalid default miscellaneous sizes.")
    flags["buildSettings"] = {
        "wallWidths": [ValidateNumber(value, minimum = .1, maximum = 10000) for value in build["wallWidths"]],
        "openingSizes": {key: ValidateNumber(build["openingSizes"].get(key, openingDefaultSizes[key]) if key in ("BarnDoor", "BifoldDoor", "CasementWindow", "AwningWindow", "DoubleCasementWindow", "SwingingDoor", "DoubleDoor") else build["openingSizes"][key], minimum = .1, maximum = 10000)
                         for key in openingDefaultSizes},
        "miscSizes": {key: ValidateNumber(miscSizes[key], minimum = .1, maximum = 10000) for key in miscDefaultSizes}}
    imperialSizes = build.get("imperialSizes", {})
    sizeKeys = {str(index) for index in range(4)} | set(openingDefaultSizes) | set(miscDefaultSizes)
    if not isinstance(imperialSizes, dict) or not set(imperialSizes) <= sizeKeys:
        raise ValueError("The project contains invalid imperial default sizes.")
    if imperialSizes:
        flags["buildSettings"]["imperialSizes"] = {
            key: ValidateNumber(value, minimum = 1, maximum = 101600) for key, value in imperialSizes.items()}
    grid = settings.get("viewportSettings", gridIntensityDefaults)
    linework = settings.get("lineworkSettings", lineworkDefaults)
    if not isinstance(linework, dict) or set(linework) != set(lineworkDefaults):
        raise ValueError("The project contains invalid line weights.")
    flags["lineworkSettings"] = {key: ValidateNumber(linework[key], minimum = 1 if key == "baseWidth" else 0,
                                                   maximum = 4 if key == "baseWidth" else 2)
                                 for key in lineworkDefaults}
    if not isinstance(grid, dict):
        raise ValueError("The project contains invalid viewport settings.")
    flags["viewportSettings"] = {key: ValidateNumber(grid[key], minimum = 0, maximum = 2 if key == "overall" else 1)
                                 for key in gridIntensityDefaults}
    measurements = settings.get("measurementSettings", measurementDefaults)
    if not isinstance(measurements, dict):
        raise ValueError("The project contains invalid dimension settings.")
    measurements = {**measurementDefaults, **measurements}
    if any(type(measurements[key]) is not int or measurements[key] not in
           ((0, 2) if key in ("stairs", "counters") else (0, 1, 2)) for key in measurementDefaults):
        raise ValueError("The project contains invalid dimension settings.")
    flags["measurementSettings"] = {key: measurements[key] for key in measurementDefaults}
    mode = settings.get("wallMeasurementMode", "All")
    if mode not in ("All", "Exterior", "Exterior stacked"):
        raise ValueError("Invalid wall dimension mode.")
    flags["wallMeasurementMode"] = mode
    reference = settings.get("wallMeasurementReference", "Wall faces")
    if reference not in ("Centerline", "Wall faces"):
        raise ValueError("Invalid wall dimension reference.")
    flags["wallMeasurementReference"] = reference
    visibility = settings.get("measurementVisibility", measurementVisibilityDefaults)
    if isinstance(visibility, dict) and "railings" not in visibility:
        visibility = {**visibility, "railings": False}
    flags["measurementVisibility"] = ValidateFlags(visibility, tuple(measurementVisibilityDefaults))
    folder = settings.get("exportFolder")
    filename = settings.get("exportFileName")
    if filename is not None:
        if not isinstance(filename, str) or not filename.strip() or filename in (".", "..") or any(character in filename for character in '<>:"/\\|?*\0'):
            raise ValueError("Invalid export filename.")
        flags["exportFileName"] = filename
    if folder is not None:
        if not isinstance(folder, str) or not folder.strip() or "\0" in folder:
            raise ValueError("Invalid export folder.")
        flags["exportFolder"] = folder
    export = settings.get("exportSettings", {})
    if not isinstance(export, dict):
        raise ValueError("Invalid export settings.")
    # Preserve the previous furnishing-only preference under its broader name.
    if "solidFurnishings" in export and "solidObjects" not in export:
        export = dict(export, solidObjects = export["solidFurnishings"])
    export = {key: value for key, value in export.items() if key != "solidFurnishings"}
    allowedExport = {"gridOrigin", "solidObjects", "wallStyle", "canvasTheme", "canvasColor", "linesColor", "borderColor", "gridColor", "texture", "textureAngle", "textureScale", "textureStrength", "textureHighlights", "textureMidtones", "textureShadows", "vignetteEnabled", "vignetteStrength", "showGrid", "viewportSettings", "lineworkSettings", "measurementVisibility", "visibility", "bounds", "scale", "scaleUnits", "scaleMode", "architecturalScale", "dpi", "ruler", "border", "borderSize", "unitsMode"}
    allowedExport.update(("wallMeasurementMode", "wallMeasurementReference"))
    if not isinstance(export, dict) or set(export) - allowedExport:
        raise ValueError("Invalid export settings.")
    flags["exportSettings"] = {}
    for name, value in export.items():
        if name == "scale":
            flags["exportSettings"][name] = ValidateNumber(value, minimum = .001, maximum = 1000000)
        elif name == "texture":
            if value is not None and (not isinstance(value, str) or value in ("", ".", "..") or "/" in value or "\\" in value):
                raise ValueError("Invalid composite texture name.")
            flags["exportSettings"][name] = value
        elif name == "textureScale":
            flags["exportSettings"][name] = ValidateNumber(value, minimum = 0, maximum = 4)
        elif name in ("textureStrength", "textureHighlights", "textureMidtones", "textureShadows"):
            flags["exportSettings"][name] = ValidateNumber(value, minimum = 0, maximum = 1)
        elif name == "textureAngle":
            flags["exportSettings"][name] = ValidateNumber(value, minimum = 0, maximum = 360)
        elif name == "vignetteStrength":
            flags["exportSettings"][name] = ValidateNumber(value, minimum = 0, maximum = 2)
        elif name == "scaleMode":
            if value not in ("Digital", "Architectural"):
                raise ValueError("Invalid export scale mode.")
            flags["exportSettings"][name] = value
        elif name == "architecturalScale":
            flags["exportSettings"][name] = ValidateNumber(value, minimum = 1, maximum = 100000)
        elif name == "dpi":
            if type(value) is not int or not 1 <= value <= 2400:
                raise ValueError("Invalid export DPI.")
            flags["exportSettings"][name] = value
        elif name == "gridOrigin":
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError("Invalid export grid origin.")
            flags["exportSettings"][name] = [ValidateNumber(entry) for entry in value]
        elif name == "bounds":
            if not isinstance(value, list) or len(value) != 4:
                raise ValueError("Invalid export bounds.")
            flags["exportSettings"][name] = [ValidateNumber(entry) for entry in value]
            if value[2] <= 0 or value[3] <= 0:
                raise ValueError("Export bounds must have positive dimensions.")
        elif name == "unitsMode":
            if value not in unitModes:
                raise ValueError("Invalid export display unit.")
            flags["exportSettings"][name] = value
        elif name in ("wallMeasurementMode", "wallMeasurementReference"):
            choices = ("All", "Exterior", "Exterior stacked") if name == "wallMeasurementMode" else ("Centerline", "Wall faces")
            if value not in choices:
                raise ValueError("Invalid export wall dimension setting.")
            flags["exportSettings"][name] = value
        elif name == "scaleUnits":
            if value not in ("px/m", "px/cm"):
                raise ValueError("Invalid export scale units.")
            flags["exportSettings"][name] = value
        elif name == "wallStyle":
            if value not in ("Material", "Solid", "Outline"):
                raise ValueError("Invalid export wall style.")
            flags["exportSettings"][name] = value
        elif name == "border":
            if value not in ("None", "Plain", "Frame", "Corner Marks", "Reference Zones", "Marked", "Ruler", "Ruler + Reference Zones"):
                raise ValueError("Invalid export border.")
            flags["exportSettings"][name] = value
        elif name == "borderSize":
            if type(value) is not int or not 1 <= value <= 128:
                raise ValueError("Invalid export border size.")
            flags["exportSettings"][name] = value
        elif name in ("canvasColor", "linesColor", "borderColor", "gridColor"):
            if not isinstance(value, str) or not QtGui.QColor(value).isValid():
                raise ValueError("Invalid export color.")
            flags["exportSettings"][name] = QtGui.QColor(value).name()
        elif name == "canvasTheme":
            if not isinstance(value, str):
                raise ValueError("Invalid export canvas theme.")
            flags["exportSettings"][name] = value
        elif name in ("showGrid", "ruler", "vignetteEnabled", "solidObjects"):
            flags["exportSettings"].update(ValidateFlags(export, (name,)))
        else:
            keys = set(flags[name])
            if name == "measurementVisibility" and isinstance(value, dict):
                value = {key: enabled for key, enabled in value.items() if key != "elevators"}
                if not value:
                    continue
            if not isinstance(value, dict) or set(value) - keys:
                raise ValueError("Invalid export option group.")
            if name in ("visibility", "measurementVisibility"):
                flags["exportSettings"][name] = ValidateFlags(value, tuple(value))
            else:
                flags["exportSettings"][name] = {
                    key: ValidateNumber(entry, minimum = 1 if name == "lineworkSettings" and key == "baseWidth" else 0,
                                        maximum = (4 if key == "baseWidth" else 2) if name == "lineworkSettings" else (2 if key == "overall" else 1))
                    for key, entry in value.items()}
    spacings = settings.get("railingSpacings", railingSpacingDefaults)
    if not isinstance(spacings, dict) or any(key not in spacings for key in railingSpacingDefaults):
        raise ValueError("Invalid railing sizing settings.")
    flags["railingSpacings"] = {key: ValidateNumber(spacings[key], minimum = .1, maximum = 10000) for key in railingSpacingDefaults}
    if not flags["railingSpacings"]["minimum"] <= flags["railingSpacings"]["target"] <= flags["railingSpacings"]["maximum"]:
        raise ValueError("Invalid railing spacing range.")
    steps = settings.get("stairStepSizes", stairStepSizeDefaults)
    if not isinstance(steps, dict):
        raise ValueError("The project contains invalid tread depth settings.")
    flags["stairStepSizes"] = {key: ValidateNumber(steps[key], minimum = .1, maximum = 10000) for key in stairStepSizeDefaults}
    if flags["stairStepSizes"]["minimum"] > flags["stairStepSizes"]["maximum"]:
        raise ValueError("Minimum stair tread depth exceeds maximum tread depth.")
    imperialAutoSizes = settings.get("imperialAutoSizes", {})
    if not isinstance(imperialAutoSizes, dict) or not set(imperialAutoSizes) <= {"stairs", "railings"}:
        raise ValueError("The project contains invalid imperial autosizing settings.")
    flags["imperialAutoSizes"] = {}
    for kind, values in imperialAutoSizes.items():
        keys = stairStepSizeDefaults if kind == "stairs" else railingSpacingDefaults
        if not isinstance(values, dict) or set(values) != set(keys):
            raise ValueError("The project contains invalid imperial autosizing settings.")
        limits = {key: ValidateNumber(values[key], minimum = 1, maximum = 101600) for key in keys}
        if limits["minimum"] > limits["maximum"] or kind == "railings" and not limits["minimum"] <= limits["target"] <= limits["maximum"]:
            raise ValueError("The project contains inconsistent imperial autosizing limits.")
        flags["imperialAutoSizes"][kind] = limits
    flags["unitsMode"] = settings.get("unitsMode", "Adaptive Metric")
    if settings.get("referenceImage") is not None:
        flags["referenceImage"] = ValidateReferenceImage(settings["referenceImage"], validatedImages)
    flags["measurementPrecision"] = settings.get("measurementPrecision", "Medium")
    if not isinstance(flags["measurementPrecision"], str) or flags["measurementPrecision"] not in measurementPrecisions:
        raise ValueError("The project contains an invalid dimension precision.")
    if flags["unitsMode"] not in unitModes:
        raise ValueError("The project contains an unknown display unit.")
    flags["autoSizingUnitsMode"] = settings.get("autoSizingUnitsMode", flags["unitsMode"])
    if flags["autoSizingUnitsMode"] not in unitModes:
        raise ValueError("The project contains an unknown autosizing unit.")
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
    return walls, windows, furnishings, groups, hiddenObjects, flags, view, labels
