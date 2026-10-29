"""Portable selection record checks, independent of Qt and model construction."""
import math
from .record_schema import openingFieldsByType, ReadArrowTipSize, selectionObjectLimit
from .furnishing_assets import FurnishingAssetProblems
from .geometry.sizing import sizingCountLimit


def ValidateSelectionPayload(payload, definitions, materials, unitModes, lineWeightClasses):
    """Return normalized records or None; adapters validate/decode embedded SVGs."""
    try:
        if payload["version"] != 1:
            return None
        records = payload["objects"]
        if not isinstance(records, list) or not 1 <= len(records) <= selectionObjectLimit:
            return None
        if any(not isinstance(record, dict) for record in records):
            return None
        payload = dict(payload, objects = [dict(record) for record in records])
        records = payload["objects"]
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
            if objectType in openingFieldsByType:
                points.append(record["center"])
                direction = record.get("wallDirection")
                if direction is not None:
                    if (not isinstance(direction, list) or len(direction) != 2
                            or any(type(value) not in (int, float) or not math.isfinite(value) for value in direction)
                            or not .999999 <= math.hypot(*direction) <= 1.000001):
                        return None
                if not math.isfinite(record["length"]) or record["length"] < 1 or not math.isfinite(record["fraction"]):
                    return None
                parent = record["parent"]
                if parent is not None and (type(parent) is not int or not 0 <= parent < len(records)
                                           or records[parent]["type"] != "Wall"):
                    return None
                if objectType == "CasementWindow":
                    record.setdefault("hingeAtSecond", False)
                record.setdefault("measurementFlipped", False)
                if "wellDepth" in openingFieldsByType[objectType]:
                    record.setdefault("windowWell", False)
                    record.setdefault("wellDashed", False)
                    record.setdefault("wellDepth", 600.0)
                    if type(record["wellDepth"]) not in (float, int) or not math.isfinite(record["wellDepth"]) or not 1 <= record["wellDepth"] <= 1e9:
                        return None
                if type(record["measurementFlipped"]) is not bool:
                    return None
                flags = tuple(name for name in openingFieldsByType[objectType]
                              if name not in ("measurementFlipped", "sillDepth", "depth", "depthOffset", "material", "wellDepth"))
                if any(not isinstance(record[flag], bool) for flag in flags):
                    return None
                if objectType == "SilledWindow" and (not math.isfinite(record["sillDepth"]) or record["sillDepth"] < 0):
                    return None
                if objectType == "Fireplace" and any(type(record[name]) not in (float, int) or not math.isfinite(record[name])
                                                      for name in ("depth", "depthOffset")):
                    return None
                if objectType == "Fireplace" and record.get("material") not in materials:
                    return None
            elif objectType in ("Wall", "Pillar", "Column", "Elevator", "Stair", "Counter", "Railing", "Furnishing", "Label", "RoomLabel", "NorthArrow", "Arrow", "MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide"):
                points.extend((record["first"], record["second"]))
                if not math.isfinite(record["width"]) or record["width"] < (0 if objectType in ("MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide") else 1e-8 if objectType in ("Label", "RoomLabel") else 1):
                    return None
                if objectType in ("MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide") and record["width"] != 0:
                    return None
                if objectType in ("MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide"):
                    if objectType in ("DashedLine", "SolidLine") and record.get("weightClass", "Objects") not in lineWeightClasses:
                        return None
                    points.append(record.get("textOffset", [0, 0]))
                if objectType == "AngleGuide":
                    points.append(record["middle"])
                if objectType in ("Label", "RoomLabel"):
                    if objectType == "RoomLabel" and record.get("unitsOverride") is not None:
                        if record["unitsOverride"] not in unitModes:
                            return None
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
                        if FurnishingAssetProblems(key, definitions, allowNull = False):
                            return None
                        checkedAssets.add(key)
                elif objectType == "NorthArrow":
                    intensity = record.get("intensity", 1.0)
                    if type(intensity) not in (int, float) or not math.isfinite(intensity) or not 0 <= intensity <= 1:
                        return None
                elif (record["material"] not in materials
                      or not all(math.isfinite(record[field]) for field in ("firstMiter", "secondMiter"))):
                    return None
                if objectType == "Arrow":
                    if type(record["solidTip"]) is not bool or type(record.get("directionReversed", False)) is not bool:
                        return None
                    ReadArrowTipSize(record, record["width"])
                    intensity = record["intensity"]
                    if type(intensity) not in (int, float) or not math.isfinite(intensity) or not 0 <= intensity <= 1:
                        return None
                if objectType == "MeasurementGuide":
                    depth = record.get("depth", 0)
                    if type(depth) not in (int, float) or not math.isfinite(depth) or not -1e9 <= depth <= 1e9:
                        return None
                if objectType == "Railing" and (type(record.get("autosize", True)) is not bool or
                        type(record.get("manualPostCount", 2)) is not int or not 2 <= record.get("manualPostCount", 2) <= sizingCountLimit):
                    return None
                if objectType == "Stair" and not isinstance(record["directionReversed"], bool):
                    return None
                if objectType == "Stair" and (type(record.get("autosize", True)) is not bool or
                        type(record.get("manualStepCount", 1)) is not int or not 1 <= record.get("manualStepCount", 1) <= sizingCountLimit):
                    return None
            else:
                return None
        if not all(isinstance(point, list) and len(point) == 2 and all(math.isfinite(value) for value in point) for point in points):
            return None
        for record in records:
            if record["type"] not in openingFieldsByType:
                minimum = 1e-8 if record["type"] in ("Label", "RoomLabel") else 1
                if record["type"] != "AngleGuide" and math.hypot(record["second"][0] - record["first"][0], record["second"][1] - record["first"][1]) < minimum:
                    return None
            elif record["parent"] is not None:
                parent = records[record["parent"]]
                length = math.hypot(parent["second"][0] - parent["first"][0], parent["second"][1] - parent["first"][1])
                if length < record["length"] or not 0 <= record["fraction"] <= 1:
                    return None
        return payload if any(record["selected"] for record in records) else None
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, IndexError):
        return None
