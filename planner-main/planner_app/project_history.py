"""Versioned sparse history, validated against the current scene before loading."""
import json
import math
from types import SimpleNamespace
from .models import MeasurementGuide, AngleGuide, Arrow, Railing, Stair, Fireplace, NorthArrow
from .object_schema import openingFields, openingClasses
from .project_codec import EncodeObjectRecord, DecodeProject
from .history_edits import ReferenceImageEdit
from .reference_image import ValidateReferenceImage



def EncodeEntry(category, entry, parentReference = None):
    obj = entry[0]
    if category == 0:
        values = {"first": [entry[1], entry[2]], "second": [entry[3], entry[4]], "width": entry[5],
                  "firstMiter": entry[6], "secondMiter": entry[7], "material": entry[8]}
        if isinstance(obj, AngleGuide):
            values["middle"] = list(entry[10][:2])
        if isinstance(obj, MeasurementGuide):
            values["textOffset"] = list(entry[10][-2:])
        if isinstance(obj, Arrow):
            values.update(solidTip = entry[10][0], tipSize = entry[10][1], intensity = entry[10][2])
        if isinstance(obj, Railing):
            values.update(autosize = entry[9][0], manualPostCount = entry[9][1])
        if isinstance(obj, Stair):
            values.update(autosize = entry[9][0], manualStepCount = entry[9][1], directionReversed = entry[10])
    elif category == 3:
        fields = {"hingeAtSecond": entry[4], "swingsOutwards": entry[5], "panelsFlipped": entry[5],
                  "sillDepth": entry[6], "measurementFlipped": entry[7]}
        if isinstance(obj, Fireplace):
            fields.update(depth = entry[6][0], depthOffset = entry[6][1], material = entry[6][2])
        values = {name: fields[name] for name in openingFields[type(obj)] if hasattr(obj, name)}
        values.update(parent = parentReference, center = entry[2], length = entry[3])
    else:
        values = {"first": [entry[1].x(), entry[1].y()], "second": [entry[2].x(), entry[2].y()], "width": entry[3]}
        if category == 8:
            values.update(text = entry[4], intensity = entry[5])
        elif category == 5 and type(obj).__name__ == "Furnishing":
            values["behindCounters"] = entry[4]
            values["flipHorizontal"] = entry[5]
            values["flipVertical"] = entry[6]
        elif category == 5 and isinstance(obj, NorthArrow):
            values["intensity"] = entry[7] if len(entry) > 8 else 1.0
    values["measurementHidden"] = entry[-1]
    return EncodeObjectRecord(obj, {}, values)


def EncodeHistoryState(state, recordCache = None):
    """Encode a transient capture for validation, without cloning scene models."""
    if recordCache is None:
        recordCache = {}
    objects = [entry[0] for index in (0, 3, 5, 8) for entry in state[index]]
    indices = {id(obj): index for index, obj in enumerate(objects)}
    records = []
    for category in (0, 3, 5, 8):
        for entry in state[category]:
            obj = entry[0]
            parentReference = indices[id(entry[1])] if category == 3 else None
            if category == 3:
                key = (id(obj), obj.objectId, category, parentReference, *entry[2:])
            elif category in (5, 8):
                definition = getattr(obj, "definitionKey", obj.definition["key"]) if category == 5 else None
                key = (id(obj), obj.objectId, category, entry[1].x(), entry[1].y(), entry[2].x(), entry[2].y(), *entry[3:], definition)
            else:
                key = (id(obj), obj.objectId, category, *entry[1:])
            record = recordCache.get(key)
            if record is None:
                record = EncodeEntry(category, entry, parentReference)
                recordCache[key] = record
            records.append(record)
    groups = sorted(sorted(indices[id(obj)] for obj in group if id(obj) in indices) for group in state[6])
    hidden = sorted(indices[id(obj)] for obj in state[7] if id(obj) in indices)
    return {"objects": records, "groups": groups, "hidden": hidden}


def EncodeEdit(edit):
    changes = []
    for category, oldIndex, newIndex, old, new in edit.changes:
        sides = []
        for position, entry in ((oldIndex, old), (newIndex, new)):
            if entry is None:
                sides.append(None)
                continue
            record = EncodeEntry(category, entry, entry[1].objectId if category == 3 else None)
            sides.append([position, record])
        changes.append({"category": category, "before": sides[0], "after": sides[1]})
    result = {"changes": changes,
            "groups": [[[position, [obj.objectId for obj in group]] for position, group in side] for side in edit.groups],
            "hidden": [[[position, obj.objectId] for position, obj in side] for side in edit.hidden],
            "orders": {str(category): [[obj.objectId for obj in side] for side in orders]
                       for category, orders in edit.orders.items()}}
    if isinstance(edit, ReferenceImageEdit):
        result["referenceImage"] = {"changes": {name: list(pair) for name, pair in edit.referenceChanges.items()},
                                    "pivots": [list(pivot) if pivot is not None else None for pivot in edit.pivots]}
    return result


def DecodeHistory(history, settings, definitions, current):
    """Ignore incompatible history; reject malformed journals without altering models.

    Decode each distinct changed object state once in a detached batch, then
    validate undo and redo chains using one transient state per direction.
    """
    from .history_edits import SceneEdit, historyLimit, historyByteBudget, stateCategories
    from .viewport.scene import SceneEditingMixin
    empty = {"undo": [], "redo": []}
    if not isinstance(history, dict) or history.get("format") != "Planner Changes" or type(history.get("version")) is not int or history["version"] != 1:
        return empty
    if set(history) != {"format", "version", "undo", "redo"}:
        raise ValueError("Invalid history header.")
    if any(not isinstance(history[name], list) for name in ("undo", "redo")):
        raise ValueError("Invalid history stacks.")
    if len(history["undo"]) + len(history["redo"]) > historyLimit:
        raise ValueError("Too many history edits.")
    if len(json.dumps(history, ensure_ascii = False, separators = (",", ":"), allow_nan = False).encode("utf-8")) > historyByteBudget:
        raise ValueError("History exceeds its memory budget.")
    currentState = SceneEditingMixin.CaptureState(current)
    currentObjects = {entry[0].objectId: entry[0] for category in stateCategories for entry in currentState[category]}
    seeds, variants = {}, {}
    for edit in history["undo"] + history["redo"]:
        if not isinstance(edit, dict) or set(edit) not in ({"changes", "groups", "hidden", "orders"},
                                                       {"changes", "groups", "hidden", "orders", "referenceImage"}):
            raise ValueError("Invalid history edit.")
        if not isinstance(edit["changes"], list) or len(edit["changes"]) > 100000:
            raise ValueError("Invalid history changes.")
        for change in edit["changes"]:
            if not isinstance(change, dict) or set(change) != {"category", "before", "after"} or type(change["category"]) is not int or change["category"] not in stateCategories:
                raise ValueError("Invalid history category.")
            for side in (change["before"], change["after"]):
                if side is None:
                    continue
                if (not isinstance(side, list) or len(side) != 2 or type(side[0]) is not int or not 0 <= side[0] < 100000
                        or not isinstance(side[1], dict) or type(side[1].get("id")) is not int or side[1]["id"] < 1):
                    raise ValueError("Invalid history object state.")
                record = side[1]
                old = seeds.get(record["id"])
                currentObject = currentObjects.get(record["id"])
                if ((old is not None and old["type"] != record.get("type"))
                        or (currentObject is not None and type(currentObject).__name__ != record.get("type"))):
                    raise ValueError("History changes an object's type.")
                seeds.setdefault(record["id"], record)
                variants.setdefault(json.dumps(record, sort_keys = True), record)
    # Unchanged parent walls are needed to validate openings, but are not saved
    # again for every edit and their current model identities remain canonical.
    for record in tuple(variants.values()):
        if record.get("type") in openingClasses:
            parentId = record.get("parent")
            if type(parentId) is int and parentId not in seeds and parentId in currentObjects:
                parent = currentObjects[parentId]
                if type(parent).__name__ == "Wall":
                    # Encode only referenced unchanged parents, not the entire scene.
                    seeds[parentId] = EncodeObjectRecord(parent, {})
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
        if record["type"] in openingClasses:
            value["parent"] = indices[json.dumps(seeds[record["parent"]], sort_keys = True)]
        records.append(value)
    # Reference pixels are independent of historical scene-model variants.
    # The current image was validated with project settings; validate older
    # replacement images only when replaying their reference deltas below.
    batchSettings = {key: value for key, value in settings.items() if key != "referenceImage"}
    batch = DecodeProject({"format": "Planner Project", "version": 1, "settings": batchSettings,
                           "scene": {"objects": records, "groups": [], "hidden": []}}, definitions, validatePlacement = False)
    walls, windows, furnishings, groups, hidden, flags, view, labels = batch
    snapshot = SimpleNamespace(walls = walls, windows = windows, furnishings = furnishings, labels = labels,
                               objectGroups = [], hiddenObjects = [], selectedWall = None, selectedVertex = None,
                               SelectionEntries = lambda: [])
    captured = SceneEditingMixin.CaptureState(snapshot)
    states = {entry[0].objectId - 1: (category, entry) for category in stateCategories for entry in captured[category]}
    pool = dict(currentObjects)
    for index, record in enumerate(variants.values()):
        pool.setdefault(record["id"], states[index][1][0])
    for objectId, obj in pool.items():
        obj.objectId = objectId
    normalized = {}
    for index, (key, record) in enumerate(variants.items()):
        category, entry = states[index]
        entry = (pool[record["id"]], *entry[1:])
        if category == 3:
            entry = (entry[0], pool[record["parent"]], *entry[2:])
            if record["type"] == "Fireplace":
                # Historical variants share one parent seed during batch decoding.
                # Keep each variant's depth/offset instead of its seed's clamp.
                entry = (*entry[:6], (record["depth"], record["depthOffset"], record.get("material", entry[6][2])), *entry[7:])
        normalized[key] = (category, entry)

    def ReadMembership(value, groups = False):
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
                if (not isinstance(ids, list) or any(type(objectId) is not int or objectId not in pool for objectId in ids)
                        or len(set(ids)) != len(ids) or (groups and len(ids) < 2)):
                    raise ValueError("Invalid history membership IDs.")
                key = tuple(ids)
                if key in seen:
                    raise ValueError("Duplicate history membership.")
                seen.add(key)
                members.append((item[0], tuple(pool[objectId] for objectId in ids) if groups else pool[ids[0]]))
            result.append(tuple(members))
        return tuple(result)

    decoded = {"undo": [], "redo": []}
    for name in decoded:
        for edit in history[name]:
            if "referenceImage" in edit:
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
                decoded[name].append(ReferenceImageEdit(reference["changes"], tuple(tuple(pivot) if pivot is not None else None for pivot in pivots)))
                continue
            changes, changedIds = [], set()
            for change in edit["changes"]:
                sides, positions = [], []
                for side in (change["before"], change["after"]):
                    if side is None:
                        sides.append(None)
                        positions.append(None)
                    else:
                        category, entry = normalized[json.dumps(side[1], sort_keys = True)]
                        if category != change["category"]:
                            raise ValueError("History object belongs to the wrong category.")
                        sides.append(entry)
                        positions.append(side[0])
                if all(side is None for side in sides) or (all(side is not None for side in sides) and sides[0][0] is not sides[1][0]):
                    raise ValueError("Invalid history object identity.")
                objectId = (sides[0] or sides[1])[0].objectId
                if objectId in changedIds:
                    raise ValueError("Duplicate history object change.")
                changedIds.add(objectId)
                changes.append((change["category"], *positions, *sides))
            orders = edit["orders"]
            if not isinstance(orders, dict) or set(orders) - {str(category) for category in stateCategories}:
                raise ValueError("Invalid history order categories.")
            decodedOrders = {}
            for category, sides in orders.items():
                if not isinstance(sides, list) or len(sides) != 2:
                    raise ValueError("Invalid history order.")
                for side in sides:
                    if (not isinstance(side, list) or len(set(side)) != len(side)
                            or any(type(objectId) is not int or objectId not in pool for objectId in side)):
                        raise ValueError("Invalid history order IDs.")
                decodedOrders[int(category)] = tuple(tuple(pool[objectId] for objectId in side) for side in sides)
            decoded[name].append(SceneEdit(changes, ReadMembership(edit["groups"], groups = True),
                                           ReadMembership(edit["hidden"]), decodedOrders))
    if sum(edit.byteSize for name in decoded for edit in decoded[name]) > historyByteBudget:
        raise ValueError("Decoded history exceeds its memory budget.")
    for name in decoded:
        state = currentState
        reference = settings.get("referenceImage")
        validatedImages = {reference["data"]} if reference is not None else set()
        for edit in reversed(decoded[name]):
            state = edit.Apply(state, name == "redo", validate = True)
            if isinstance(edit, ReferenceImageEdit):
                reference = edit.ApplyReference(reference, name == "redo", validate = True)
                reference = ValidateReferenceImage(reference, validatedImages)
    return decoded
