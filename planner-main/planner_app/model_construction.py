"""Detached model construction inputs and project membership plans without Qt."""
from typing import NamedTuple
import math
from .record_validation import ValidateCoordinates, ValidateNumber
from .record_schema import ReadArrowTipSize, openingFieldsByType, geometryIssueNames
from .geometry.sizing import sizingCountLimit
from .geometry.reserved_doors import ReservedDoorWithinHost

linearKinds = ("Wall", "Pillar", "Column", "Elevator", "Stair", "Counter", "Railing", "Arrow",
               "MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide")
guideKinds = ("MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide")


class ObjectConstruction(NamedTuple):
    kind: str
    category: str
    first: tuple
    second: tuple
    width: float
    fields: dict
    points: dict | None
    firstMiter: float = 0.0
    secondMiter: float = 0.0
    material: str = "Generic"


def ConstructionFlag(record, name, default = None):
    value = record.get(name, default)
    if type(value) is not bool:
        raise ValueError("The project contains invalid option settings.")
    return value


def PlanObjectConstruction(record, materials, unitModes, lineWeightClasses, placement = None,
                           delta = (0.0, 0.0), distance = math.hypot):
    """Plan one non-opening model, preserving project/paste validation policies.

    Placement supplies translated geometry from a normalized selection payload.
    Project records instead receive strict numeric, text and sizing validation.
    Returned values never reference a live model or mutate the source record.
    """
    project = placement is None
    if project:
        if not isinstance(record, dict) or not isinstance(record.get("type"), str):
            raise ValueError("The project contains an invalid object record.")
        kind = record["type"]
        first, second = ValidateCoordinates(record["first"]), ValidateCoordinates(record["second"])
        width = ValidateNumber(record["width"], minimum = 0 if kind in guideKinds else 1e-8 if kind in ("Label", "RoomLabel") else 1, maximum = 1e9)
        if kind in guideKinds and width != 0:
            raise ValueError("Dimension guides cannot have a width.")
        if kind != "AngleGuide" and distance(second[0] - first[0], second[1] - first[1]) < 1e-8:
            raise ValueError("An object has zero length.")
    else:
        kind = record["type"]
        first, second, width = placement
    category = "labels" if kind in ("Label", "RoomLabel") else "furnishings" if kind in ("Furnishing", "NorthArrow") else "walls"
    fields, points = {}, None
    firstMiter = secondMiter = 0.0
    material = "Generic"
    if kind in ("Label", "RoomLabel"):
        text = record["text"]
        if project and (not isinstance(text, str) or len(text) > 100000):
            raise ValueError("A label contains invalid text.")
        intensity = record.get("intensity", 1.0)
        fields.update(text = text, intensity = ValidateNumber(intensity, minimum = 0, maximum = 1) if project else intensity)
        if kind == "RoomLabel":
            mode = record.get("unitsOverride")
            if project and mode is not None and mode not in unitModes:
                raise ValueError("Invalid room label units.")
            fields["unitsOverride"] = mode
    elif kind == "NorthArrow":
        intensity = record.get("intensity", 1.0)
        fields["intensity"] = ValidateNumber(intensity, minimum = 0, maximum = 1) if project else intensity
    elif kind == "Furnishing":
        if project and not isinstance(record["definition"], str):
            raise ValueError("A furnishing definition is invalid.")
        for name in ("behindCounters", "flipHorizontal", "flipVertical"):
            fields[name] = ConstructionFlag(record, name, False)
        fields["definitionKey"] = record["definition"]
    elif kind in linearKinds:
        if project:
            if record["material"] not in materials:
                raise ValueError("A wall material is unknown.")
            firstMiter = ValidateNumber(record["firstMiter"], minimum = 0, maximum = 1)
            secondMiter = ValidateNumber(record["secondMiter"], minimum = 0, maximum = 1)
        else:
            if not all(math.isfinite(record[name]) for name in ("firstMiter", "secondMiter")) or record["material"] not in materials:
                raise ValueError("Invalid wall construction settings")
            firstMiter, secondMiter = record["firstMiter"], record["secondMiter"]
        material = record["material"]
        if kind in guideKinds:
            point = record.get("textOffset", [0, 0])
            points = {}
            points["textOffset"] = ValidateCoordinates(point) if project else tuple(point)
        if kind == "MeasurementGuide":
            fields["depth"] = ValidateNumber(record.get("depth", 0), minimum = -1e9, maximum = 1e9)
        if kind in ("DashedLine", "SolidLine"):
            weight = record.get("weightClass", "Objects")
            if project and (not isinstance(weight, str) or weight not in lineWeightClasses):
                raise ValueError("Invalid annotation line weight class.")
            fields["weightClass"] = weight
        if kind == "AngleGuide":
            point = record["middle"]
            points["middleVertex"] = ValidateCoordinates(point) if project else (point[0] + delta[0], point[1] + delta[1])
        if kind == "Stair":
            fields["directionReversed"] = ConstructionFlag(record, "directionReversed") if project else bool(record["directionReversed"])
        if kind in ("Stair", "Railing"):
            minimum, countName = (1, "manualStepCount") if kind == "Stair" else (2, "manualPostCount")
            autosize, count = record.get("autosize", True), record.get(countName, minimum)
            if project and (type(autosize) is not bool or type(count) is not int or not minimum <= count <= sizingCountLimit):
                raise ValueError("A stair contains invalid step settings." if kind == "Stair" else "A railing contains invalid post settings.")
            fields.update(autosize = autosize)
            fields[countName] = count
        if kind == "Arrow":
            fields["solidTip"] = ConstructionFlag(record, "solidTip") if project else record["solidTip"]
            fields["directionReversed"] = ConstructionFlag(record, "directionReversed", False) if project else record.get("directionReversed", False)
            fields["tipSize"] = ReadArrowTipSize(record, width)
            fields["intensity"] = ValidateNumber(record["intensity"], minimum = 0, maximum = 1) if project else record["intensity"]
    else:
        raise ValueError(f"Unknown object type: {kind}")
    if project:
        fields["measurementHidden"] = ConstructionFlag(record, "measurementHidden", False)
        if isinstance(record.get("originalMaterial"), str):
            fields["originalMaterial"] = record["originalMaterial"]
    return ObjectConstruction(kind, category, first, second, width, fields, points, firstMiter, secondMiter, material)


def PlanProjectMemberships(records, createdKeys, scene):
    keys = frozenset(createdKeys)
    objectIds, assignments = set(), []
    for index in createdKeys:
        objectId = records[index].get("id")
        if objectId is not None:
            if type(objectId) is not int or objectId < 1 or objectId in objectIds:
                raise ValueError("The project contains invalid or duplicate object IDs.")
            objectIds.add(objectId)
            assignments.append((index, objectId))
    if not isinstance(scene["groups"], list) or not isinstance(scene["hidden"], list):
        raise ValueError("The project contains invalid groups or hidden objects.")
    groups, hidden = scene["groups"], scene["hidden"]
    grouped, plannedGroups = set(), []
    for group in groups:
        if (not isinstance(group, list) or len(group) < 2 or any(type(index) is not int or index not in keys for index in group)
                or len(set(group)) != len(group) or grouped.intersection(group)):
            raise ValueError("The project contains invalid group membership.")
        grouped.update(group)
        plannedGroups.append(tuple(group))
    if any(type(index) is not int or index not in keys for index in hidden) or len(set(hidden)) != len(hidden):
        raise ValueError("The project contains invalid hidden objects.")
    return assignments, plannedGroups, list(hidden), objectIds


class OpeningConstruction(NamedTuple):
    kind: str
    firstFraction: float
    secondFraction: float
    fields: dict


def PlanProjectOpening(record, parentLength, parentWidth, parentMaterial, materials, validatePlacement = True, parkingBounds = (0, 1)):
    """Validate opening fields using a resolved parent's numeric dimensions.

    Recovery deliberately retains raw fireplace depths and offsets. Model
    properties clamp them for ordinary rendering unless recovery flags allow
    the original geometry to remain visible.
    """
    kind = record["type"]
    issues = record.get("geometryIssues", [])
    if not isinstance(issues, list) or any(not isinstance(code, str) or code not in geometryIssueNames for code in issues):
        raise ValueError("Invalid geometry highlight flags.")
    center = ValidateNumber(record["center"], minimum = -1e12 if "opening_bounds" in issues else 0,
                            maximum = 1e12 if "opening_bounds" in issues else 1)
    length = ValidateNumber(record["length"], minimum = 1, maximum = 1e9)
    span = length / parentLength
    first, second = center - span / 2, center + span / 2
    withinHost = (ReservedDoorWithinHost(parentLength, length, center, record.get("hingeAtSecond", False), parkingBounds)
                  if kind in ("BarnDoor", "PocketDoor") else first >= -1e-8 and second <= 1 + 1e-8)
    if validatePlacement and "opening_bounds" not in issues and not withinHost:
        raise ValueError("A door or window extends beyond its parent wall.")
    fields = dict(centerFraction = center, length = length, geometryIssues = tuple(issues))
    flipped = record.get("measurementFlipped", False)
    if type(flipped) is not bool:
        raise ValueError("An opening has an invalid dimension flip value.")
    fields["measurementFlipped"] = flipped
    for name in openingFieldsByType[kind]:
        if name in ("measurementFlipped", "sillDepth", "depth", "depthOffset", "material", "wellDepth"):
            continue
        if kind == "CasementWindow" and name == "hingeAtSecond" and name not in record:
            continue
        fields[name] = ConstructionFlag(record, name, False if name in ("windowWell", "wellDashed") else None)
    if kind == "SilledWindow":
        fields["sillDepth"] = ValidateNumber(record["sillDepth"], minimum = 0)
    if "wellDepth" in openingFieldsByType[kind]:
        fields["wellDepth"] = ValidateNumber(record.get("wellDepth", 600.0), minimum = 1, maximum = 1e9)
    if kind == "Fireplace":
        material = record.get("material", parentMaterial)
        if material not in materials:
            raise ValueError("A fireplace material is unknown.")
        fields["material"] = material
        checkBounds = validatePlacement and "fireplace_bounds" not in issues
        depth = ValidateNumber(record["depth"], minimum = parentWidth if checkBounds else 1, maximum = 1e9)
        fields["manualDepth"] = depth
        effectiveDepth = depth if "fireplace_bounds" in issues else max(parentWidth, depth)
        limit = (effectiveDepth - parentWidth) / 2
        fields["manualDepthOffset"] = ValidateNumber(record["depthOffset"], minimum = -limit if checkBounds else -1e12,
                                                     maximum = limit if checkBounds else 1e12)
    fields["measurementHidden"] = ConstructionFlag(record, "measurementHidden", False)
    if isinstance(record.get("originalMaterial"), str):
        fields["originalMaterial"] = record["originalMaterial"]
    return OpeningConstruction(kind, first, second, fields)


def PlanCompoundFallback(record, definitionKeys, expandedCount, nextObjectId, distance = math.hypot):
    """Flatten unavailable compound definitions in serialized child order.

    Counts include the original scene objects, as in project decoding. The
    caller carries both counters between roots so limits and IDs span the
    whole scene. Known definitions terminate traversal, even with children.
    """
    plans = []

    def Visit(child, depth):
        nonlocal expandedCount, nextObjectId
        if depth >= 64 or not isinstance(child, dict) or child.get("type") != "Furnishing" or not isinstance(child.get("definition"), str):
            raise ValueError("Invalid compound furnishing fallback.")
        first, second = ValidateCoordinates(child.get("first")), ValidateCoordinates(child.get("second"))
        width = ValidateNumber(child.get("width"), minimum = 1, maximum = 1e9)
        if distance(second[0] - first[0], second[1] - first[1]) < 1e-8:
            raise ValueError("A compound child has zero length.")
        key = child["definition"]
        if key not in definitionKeys and "children" in child:
            children = child["children"]
            if not isinstance(children, list) or not children or len(children) > 100000:
                raise ValueError("Invalid compound furnishing children.")
            for part in children:
                Visit(part, depth + 1)
            return
        expandedCount += 1
        if expandedCount > 100000:
            raise ValueError("Compound fallback contains too many objects.")
        fields = dict(definitionKey = key)
        for name in ("behindCounters", "flipHorizontal", "flipVertical", "measurementHidden"):
            fields[name] = ConstructionFlag(child, name, False)
        fields["objectId"] = nextObjectId
        nextObjectId += 1
        plans.append(ObjectConstruction("Furnishing", "furnishings", first, second, width, fields, None))

    Visit(record, 0)
    return plans, expandedCount, nextObjectId


def PlanSelectionOpeningFields(record, kind, parentWidth):
    """Plan normalized clipboard fields in model setter order.

    Clipboard fireplace values use ordinary setters, unlike project recovery.
    Keep its offset tolerance and existing boolean coercion policy separate
    from the stricter project-record validation above.
    """
    fields = {}
    for name in openingFieldsByType[kind]:
        value = record[name]
        if name == "sillDepth" and (not math.isfinite(value) or value < 0):
            raise ValueError("Invalid sill depth")
        if name == "depth" and (not math.isfinite(value) or value < parentWidth):
            raise ValueError("Invalid fireplace depth")
        if name == "depthOffset" and (not math.isfinite(value) or abs(value) > (fields["depth"] - parentWidth) / 2 + 1e-8):
            raise ValueError("Invalid fireplace depth offset")
        fields[name] = value if name in ("sillDepth", "depth", "depthOffset", "material", "wellDepth") else bool(value)
    return fields
