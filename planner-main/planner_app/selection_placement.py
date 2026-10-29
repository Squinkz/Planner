"""Translate and validate portable selection geometry before scene mutation."""
import math
from .record_schema import openingFieldsByType, selectionObjectLimit


def PlanSelectionPlacement(payload, delta, distance = math.hypot):
    """Yield detached non-opening placements; validate host references on completion.

    Records are borrowed from the already normalized clipboard payload. No
    record copies, models or scene snapshots are needed. Keep record order and
    defer opening construction/host discovery to the desktop adapter.
    """
    records = payload["objects"]
    if payload["version"] != 1 or not records or len(records) > selectionObjectLimit:
        raise ValueError("Invalid selection size or version")
    if len(delta) != 2 or not all(math.isfinite(value) for value in delta):
        raise ValueError("Invalid selection displacement")
    createdWalls = set()
    for index, record in enumerate(records):
        if not isinstance(record["selected"], bool):
            raise ValueError("Invalid selection flag")
        objectType = record["type"]
        if objectType in openingFieldsByType:
            continue
        firstX, firstY = record["first"]
        secondX, secondY = record["second"]
        first = firstX + delta[0], firstY + delta[1]
        second = secondX + delta[0], secondY + delta[1]
        width = record["width"]
        if not all(math.isfinite(value) for value in (*first, *second, width)):
            raise ValueError("Invalid translated selection geometry")
        minimumSize = 1e-8 if objectType in ("Label", "RoomLabel") else 1
        minimumWidth = 0 if objectType in ("MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide") else minimumSize
        if width < minimumWidth or objectType != "AngleGuide" and distance(second[0] - first[0], second[1] - first[1]) < minimumSize:
            raise ValueError("Selection geometry is too small")
        if objectType == "Wall":
            createdWalls.add(index)
        yield index, record, first, second, width
    for record in records:
        if record["type"] not in openingFieldsByType:
            continue
        if not math.isfinite(record["length"]) or record["length"] < 1:
            raise ValueError("Invalid opening length")
        if not math.isfinite(record["fraction"]) or not all(math.isfinite(value) for value in record["center"]):
            raise ValueError("Invalid opening placement")
        if record["parent"] is not None and record["parent"] not in createdWalls:
            raise ValueError("Invalid opening parent")
