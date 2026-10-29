"""Portable history record validation and reference deltas; no models or Qt."""
import math
import json
from .record_schema import openingFieldsByType


historyLimit = 200
historyByteBudget = 16 * 1024 * 1024


def ReadHistoryMembership(value, knownIds, groups = False):
    knownIds = frozenset(knownIds)
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("Invalid history membership changes.")
    result = []
    for side in value:
        if not isinstance(side, list):
            raise ValueError("Invalid history membership side.")
        members = []
        seen = set()
        for item in side:
            if not isinstance(item, list) or len(item) != 2 or type(item[0]) is not int or not 0 <= item[0] < 100000:
                raise ValueError("Invalid history membership position.")
            ids = item[1] if groups else [item[1]]
            if (not isinstance(ids, list) or any(type(objectId) is not int or objectId not in knownIds for objectId in ids)
                    or len(set(ids)) != len(ids) or (groups and len(ids) < 2)):
                raise ValueError("Invalid history membership IDs.")
            key = tuple(ids)
            if key in seen:
                raise ValueError("Duplicate history membership.")
            seen.add(key)
            members.append((item[0], tuple(ids) if groups else ids[0]))
        result.append(tuple(members))
    return tuple(result)


def ReadHistoryOrders(orders, knownIds, stateCategories):
    knownIds = frozenset(knownIds)
    if not isinstance(orders, dict) or set(orders) - {str(category) for category in stateCategories}:
        raise ValueError("Invalid history order categories.")
    decodedOrders = {}
    for category, sides in orders.items():
        if not isinstance(sides, list) or len(sides) != 2:
            raise ValueError("Invalid history order.")
        for side in sides:
            if (not isinstance(side, list) or len(set(side)) != len(side)
                    or any(type(objectId) is not int or objectId not in knownIds for objectId in side)):
                raise ValueError("Invalid history order IDs.")
        decodedOrders[int(category)] = tuple(tuple(side) for side in sides)
    return decodedOrders


def ReadReferenceHistory(edit):
    reference = edit["referenceImage"]
    if (edit["changes"] or edit["orders"] or edit["groups"] != [[], []] or edit["hidden"] != [[], []]
            or not isinstance(reference, dict) or set(reference) != {"changes", "pivots"}
            or not isinstance(reference["changes"], dict)
            or set(reference["changes"]) - {"center", "width", "height", "angle", "opacity", "path", "data"}
            or any(not isinstance(pair, list) or len(pair) != 2 for pair in reference["changes"].values())):
        raise ValueError("Invalid reference history edit.")
    pivots = reference["pivots"]
    if (not isinstance(pivots, list) or len(pivots) != 2
            or any(pivot is not None and (not isinstance(pivot, list) or len(pivot) != 2
               or any(type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e12 for value in pivot)) for pivot in pivots)):
        raise ValueError("Invalid reference history pivot.")
    return reference["changes"], tuple(tuple(pivot) if pivot is not None else None for pivot in pivots)


def ApplyReferenceChanges(record, changes, forward, validate = False):
    if record is None:
        raise ValueError("Reference history has no image.")
    result = dict(record, center = list(record["center"]))
    source, target = (0, 1) if forward else (1, 0)
    for name, values in changes.items():
        if validate and result[name] != values[source]:
            raise ValueError("Reference history does not match the current image.")
        result[name] = list(values[target]) if name == "center" else values[target]
    return result


def HistoryEntryFields(category, entry, kind, parentReference = None):
    if category == 0:
        values = {"first": [entry[1], entry[2]], "second": [entry[3], entry[4]], "width": entry[5],
                  "firstMiter": entry[6], "secondMiter": entry[7], "material": entry[8]}
        if kind == "AngleGuide":
            values["middle"] = list(entry[10][:2])
        if kind in ("MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide"):
            values["textOffset"] = list(entry[10][-2:])
        if kind == "MeasurementGuide" and len(entry[10]) > 2 and entry[10][0] != 0:
            values["depth"] = entry[10][0]
        if kind in ("DashedLine", "SolidLine"):
            values["weightClass"] = entry[10][0]
        if kind == "Arrow":
            values.update(solidTip = entry[10][0], tipSize = entry[10][1], intensity = entry[10][2])
            if len(entry[10]) > 3 and entry[10][3]:
                values["directionReversed"] = True
        if kind == "Railing":
            values.update(autosize = entry[9][0], manualPostCount = entry[9][1])
        if kind == "Stair":
            values.update(autosize = entry[9][0], manualStepCount = entry[9][1], directionReversed = entry[10])
    elif category == 3:
        fields = {"hingeAtSecond": entry[4], "swingsOutwards": entry[5], "panelsFlipped": entry[5],
                  "sillDepth": entry[6], "measurementFlipped": entry[7]}
        fields.update(zip(("windowWell", "wellDepth", "wellDashed"), entry[9] if len(entry) > 9 else (False, 600.0, False)))
        if kind == "Fireplace":
            fields.update(depth = entry[6][0], depthOffset = entry[6][1], material = entry[6][2])
        values = {name: fields[name] for name in openingFieldsByType[kind]}
        values.update(parent = parentReference, center = entry[2], length = entry[3])
    else:
        values = {"first": list(entry[1]), "second": list(entry[2]), "width": entry[3]}
        if category == 8:
            values.update(text = entry[4], intensity = entry[5])
            if kind == "RoomLabel":
                values["unitsOverride"] = entry[6] if len(entry) > 7 else None
        elif category == 5 and kind == "Furnishing":
            values["behindCounters"] = entry[4]
            values["flipHorizontal"] = entry[5]
            values["flipVertical"] = entry[6]
        elif category == 5 and kind == "NorthArrow":
            values["intensity"] = entry[7] if len(entry) > 8 else 1.0
    values["measurementHidden"] = entry[8] if category == 3 else entry[-1]
    return values



def ValidateHistoryHeader(history):
    if not isinstance(history, dict) or history.get("format") != "Planner Changes" or type(history.get("version")) is not int or history["version"] != 1:
        return False
    if set(history) != {"format", "version", "undo", "redo"}:
        raise ValueError("Invalid history header.")
    if any(not isinstance(history[name], list) for name in ("undo", "redo")):
        raise ValueError("Invalid history stacks.")
    if len(history["undo"]) + len(history["redo"]) > historyLimit:
        raise ValueError("Too many history edits.")
    if len(json.dumps(history, ensure_ascii = False, separators = (",", ":"), allow_nan = False).encode("utf-8")) > historyByteBudget:
        raise ValueError("History exceeds its memory budget.")
    return True


def PlanHistoryVariants(history, currentTypes, readParent):
    seeds, variants = {}, {}
    for edit in history["undo"] + history["redo"]:
        if not isinstance(edit, dict) or set(edit) not in ({"changes", "groups", "hidden", "orders"},
                                                       {"changes", "groups", "hidden", "orders", "referenceImage"}):
            raise ValueError("Invalid history edit.")
        if not isinstance(edit["changes"], list) or len(edit["changes"]) > 100000:
            raise ValueError("Invalid history changes.")
        for change in edit["changes"]:
            if not isinstance(change, dict) or set(change) != {"category", "before", "after"} or type(change["category"]) is not int or change["category"] not in (0, 3, 5, 8):
                raise ValueError("Invalid history category.")
            for side in (change["before"], change["after"]):
                if side is None:
                    continue
                if (not isinstance(side, list) or len(side) != 2 or type(side[0]) is not int or not 0 <= side[0] < 100000
                        or not isinstance(side[1], dict) or type(side[1].get("id")) is not int or side[1]["id"] < 1):
                    raise ValueError("Invalid history object state.")
                record = side[1]
                old = seeds.get(record["id"])
                currentType = currentTypes.get(record["id"])
                if ((old is not None and old["type"] != record.get("type"))
                        or (currentType is not None and currentType != record.get("type"))):
                    raise ValueError("History changes an object's type.")
                seeds.setdefault(record["id"], record)
                variants.setdefault(json.dumps(record, sort_keys = True), record)
    # Unchanged parent walls are needed to validate openings, but are not saved
    # again for every edit and their current model identities remain canonical.
    for record in tuple(variants.values()):
        if record.get("type") in openingFieldsByType:
            parentId = record.get("parent")
            if type(parentId) is int and parentId not in seeds and parentId in currentTypes:
                if currentTypes[parentId] == "Wall":
                    # Encode only referenced unchanged parents, not the entire scene.
                    seeds[parentId] = readParent(parentId)
            if type(parentId) is not int or parentId not in seeds or seeds[parentId]["type"] != "Wall":
                raise ValueError("Invalid history opening parent.")
            parent = seeds[parentId]
            variants.setdefault(json.dumps(parent, sort_keys = True), parent)
    if len(variants) > 50000:
        raise ValueError("Too many distinct historical object states.")
    variantKeys = list(variants)
    indices = {key: index for index, key in enumerate(variantKeys)}
    records = []
    for index, record in enumerate(variants.values()):
        value = {**record, "id": index + 1}
        if record["type"] in openingFieldsByType:
            value["parent"] = indices[json.dumps(seeds[record["parent"]], sort_keys = True)]
        records.append(value)
    return variants, records
