"""Versioned sparse history, validated against the current scene before loading."""
import json
from types import SimpleNamespace
from .models import MeasurementGuide, AngleGuide, Arrow, Railing, Stair, Fireplace, NorthArrow, DashedLine
from .object_schema import openingFields, openingClasses
from .project_codec import EncodeObjectRecord, DecodeProject
from .history_edits import ReferenceImageEdit
from .reference_image import ValidateReferenceImage
from .history_records import ReadHistoryMembership, ReadHistoryOrders, ReadReferenceHistory, HistoryEntryFields, ValidateHistoryHeader, PlanHistoryVariants



def EncodeEntry(category, entry, parentReference = None):
    obj = entry[0]
    if category in (5, 8):
        entry = (obj, (entry[1].x(), entry[1].y()), (entry[2].x(), entry[2].y()), *entry[3:])
    values = HistoryEntryFields(category, entry, type(obj).__name__, parentReference)
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
    if not ValidateHistoryHeader(history):
        return empty
    currentState = SceneEditingMixin.CaptureState(current)
    currentObjects = {entry[0].objectId: entry[0] for category in stateCategories for entry in currentState[category]}
    variants, records = PlanHistoryVariants(history, {objectId: type(obj).__name__ for objectId, obj in currentObjects.items()},
                                            lambda objectId: EncodeObjectRecord(currentObjects[objectId], {}))
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
        changes = ReadHistoryMembership(value, pool, groups = groups)
        return tuple(tuple((position, tuple(pool[objectId] for objectId in ids) if groups else pool[ids])
                           for position, ids in side) for side in changes)

    decoded = {"undo": [], "redo": []}
    for name in decoded:
        for edit in history[name]:
            if "referenceImage" in edit:
                changes, pivots = ReadReferenceHistory(edit)
                decoded[name].append(ReferenceImageEdit(changes, pivots))
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
            orders = ReadHistoryOrders(edit["orders"], pool, stateCategories)
            decodedOrders = {category: tuple(tuple(pool[objectId] for objectId in side) for side in sides)
                             for category, sides in orders.items()}
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
