"""Geometry repair candidates and descriptions from records, without Qt or mutation."""
import math
from .record_validation import Finite


def ProposeOpeningGeometry(record, parentWidth, parentLength):
    kind = record["type"]
    candidate = dict(record)
    invalidDimensions = False
    for name, fallback, minimum in (("center", .5, -1e12), ("length", min(900, parentLength), 1)):
        if not Finite(record.get(name), minimum, 1e9 if name == "length" else 1e12):
            candidate[name] = fallback
            invalidDimensions = True
    for name in ("sillDepth", "depth", "depthOffset", "wellDepth"):
        if name in record or kind == "Fireplace" and name in ("depth", "depthOffset"):
            minimum = -1e12 if name == "depthOffset" else 1 if name in ("depth", "wellDepth") else 0
            if not Finite(record.get(name), minimum, 1e9 if name in ("depth", "wellDepth") else 1e12):
                candidate[name] = 600 if name == "wellDepth" else 0 if name == "depthOffset" else parentWidth if name == "depth" else 40
                invalidDimensions = True
    if invalidDimensions:
        issue = dict(code = "dimensions", description = "The opening has impossible dimensions or coordinates.",
                     repair = candidate if candidate["length"] >= 1 else None)
        return issue
    if kind == "Fireplace":
        depth = record.get("depth", parentWidth)
        limit = max(0, (depth - parentWidth) / 2)
        offset = record.get("depthOffset", 0)
        if depth < parentWidth or abs(offset) > limit + 1e-8:
            depth = max(parentWidth, depth)
            limit = (depth - parentWidth) / 2
            candidate.update(depth = depth, depthOffset = max(-limit, min(limit, offset)))
            if "fireplace_bounds" not in record.get("geometryIssues", []):
                issue = dict(code = "fireplace_bounds", description = "The fireplace depth or offset does not fit its wall.", highlight = True, repair = candidate)
                return issue
    return None


def ProposeObjectGeometry(record, wallWidth, definitions):
    kind = record["type"]
    candidate = dict(record)
    for name in (("first", "second", "middle", "textOffset") if kind == "AngleGuide" else ("first", "second")):
        point = record.get(name)
        if not isinstance(point, list) or len(point) != 2:
            candidate[name] = [0, 0]
        else:
            candidate[name] = [value if Finite(value) else 0 for value in point]
    if kind in ("MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine") and "textOffset" in record:
        point = record["textOffset"]
        if not isinstance(point, list) or len(point) != 2 or not all(Finite(value) for value in point):
            candidate["textOffset"] = [0, 0]
    minimum = 0 if kind in ("MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide") else 1e-8 if kind in ("Label", "RoomLabel") else 1
    if not Finite(record.get("width"), minimum, 1e9) or kind in ("MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide") and record.get("width") != 0:
        candidate["width"] = 0 if kind in ("MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide") else wallWidth if kind == "Wall" else definitions.get(record.get("definition"), definitions["null"])["width"]
    if kind != "AngleGuide" and math.hypot(candidate["second"][0] - candidate["first"][0], candidate["second"][1] - candidate["first"][1]) < 1e-8:
        candidate["second"] = [candidate["first"][0] + (1000 if candidate["first"][0] <= 1e12 - 1000 else -1000), candidate["first"][1]]
    for name in ("firstMiter", "secondMiter"):
        if kind not in ("Label", "RoomLabel", "Furnishing", "NorthArrow") and not Finite(record.get(name), 0, 1):
            candidate[name] = 0
    return candidate if candidate != record else None


def GeometryRepairText(record, repair):
    descriptions = []
    for name, value in repair.items():
        if isinstance(record, dict) and record.get(name) == value:
            continue
        if name in ("first", "second"):
            descriptions.append(f"{'Start' if name == 'first' else 'End'} position: ({value[0]:g}, {value[1]:g}) mm")
        elif name == "center":
            descriptions.append(f"Position along wall: {value * 100:g}%")
        elif name in ("width", "length", "depth", "sillDepth", "depthOffset"):
            label = {"sillDepth": "Sill depth", "depthOffset": "Depth offset"}.get(name, name.capitalize())
            descriptions.append(f"{label}: {value:g} mm")
        else:
            descriptions.append(f"{name}: {value}")
    return "Repair will set:\n" + "\n".join(descriptions)
