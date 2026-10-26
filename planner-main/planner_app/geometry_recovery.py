"""Explicit per-object choices for geometry that cannot be loaded safely."""
import copy
import math
from PySide6 import QtCore
from .models import Wall, Window, Fireplace
from .object_schema import openingClasses, openingFields
from .viewport.geometry import FootprintGeometry


class GeometryLoadCancelled(Exception):
    pass


geometryIssueNames = ("opening_bounds", "opening_overlap", "opening_obstruction", "fireplace_bounds")
knownObjectTypes = {"Wall", "Pillar", "Column", "Elevator", "Stair", "Counter", "Railing", "Arrow", "MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide", "Label", "RoomLabel", "Furnishing", "NorthArrow", *openingClasses}


def Finite(value, minimum = -1e12, maximum = 1e12):
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum


def RecordWall(record):
    if (not isinstance(record, dict) or record.get("type") != "Wall" or not Finite(record.get("width"), 1, 1e9)
            or any(not isinstance(record.get(name), list) or len(record[name]) != 2 or not all(Finite(value) for value in record[name]) for name in ("first", "second"))):
        return None
    wall = Wall(QtCore.QPointF(*record["first"]), QtCore.QPointF(*record["second"]), record["width"],
                record.get("firstMiter", 0) if Finite(record.get("firstMiter", 0), 0, 1) else 0,
                record.get("secondMiter", 0) if Finite(record.get("secondMiter", 0), 0, 1) else 0)
    return wall if QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() > 1e-8 else None


def RecordOpening(record, parent):
    obj = openingClasses[record["type"]](parent, .25, .75)
    obj.centerFraction, obj.length = record["center"], record["length"]
    obj.geometryIssues = geometryIssueNames
    for name in openingFields[type(obj)]:
        if name in record and name not in ("depth", "depthOffset"):
            setattr(obj, name, record[name])
    if isinstance(obj, Fireplace):
        obj.manualDepth = record.get("depth", parent.width)
        obj.manualDepthOffset = record.get("depthOffset", 0)
    return obj


def PrepareGeometryValidation(data):
    from .geometry.spatial_index import BoundsIndex
    walls, parentOpenings = {}, {}
    wallIndex = BoundsIndex(2000)
    geometry = FootprintGeometry(1.0)
    for index, record in enumerate(data["scene"]["objects"]):
        wall = RecordWall(record)
        if wall is not None:
            walls[index] = wall
            bounds = geometry.ObjectFootprint(wall)[0]
            wallIndex.Insert((bounds.left(), bounds.top(), bounds.right(), bounds.bottom()), index)
        if (isinstance(record, dict) and isinstance(record.get("type"), str) and record["type"] in openingClasses
                and type(record.get("parent")) is int and Finite(record.get("center")) and Finite(record.get("length"), 1, 1e9)):
            parentOpenings.setdefault(record["parent"], []).append((index, record))
    intervalIndices = {}
    for parentIndex, openings in parentOpenings.items():
        parent = walls.get(parentIndex)
        if parent is None:
            continue
        length = QtCore.QLineF(parent.firstVertex, parent.secondVertex).length()
        spans = sorted(record["length"] / length for index, record in openings)
        intervals = BoundsIndex(spans[len(spans) // 2])
        for index, record in openings:
            half = record["length"] / (2 * length)
            intervals.Insert((record["center"] - half, 0, record["center"] + half, 1), index)
        intervalIndices[parentIndex] = intervals
    return walls, wallIndex, intervalIndices


def OpeningProblem(index, data, ignored = (), prepared = None):
    records = data["scene"]["objects"]
    record = records[index]
    parent = prepared[0][record["parent"]] if prepared is not None else RecordWall(records[record["parent"]])
    wallLength = QtCore.QLineF(parent.firstVertex, parent.secondVertex).length()
    half = record["length"] / (2 * wallLength)
    if "opening_bounds" not in ignored and (record["center"] - half < -1e-8 or record["center"] + half > 1 + 1e-8):
        return "opening_bounds", "The opening extends beyond its parent wall."
    sameParent = enumerate(records)
    if prepared is not None:
        intervals = prepared[2].get(record["parent"])
        candidates = intervals.Query((record["center"] - half, 0, record["center"] + half, 1)) if intervals is not None else ()
        sameParent = ((otherIndex, records[otherIndex]) for otherIndex in candidates)
    for otherIndex, other in sameParent:
        if otherIndex == index or not isinstance(other, dict) or other.get("type") not in openingClasses or other.get("parent") != record["parent"]:
            continue
        if not Finite(other.get("center")) or not Finite(other.get("length"), 1, 1e9):
            continue
        otherHalf = other["length"] / (2 * wallLength)
        if "opening_overlap" not in ignored and min(record["center"] + half, other["center"] + otherHalf) - max(record["center"] - half, other["center"] - otherHalf) > 1e-8:
            return "opening_overlap", f"The opening overlaps {other['type']} #{other.get('id', otherIndex + 1)} on the same wall."
    geometry = FootprintGeometry(1.0)
    geometry.collisionSettings = data["settings"]["collisionSettings"]
    obj = RecordOpening(record, parent)
    candidates = range(len(records))
    if prepared is not None:
        bounds = geometry.ObjectFootprint(obj)[0].adjusted(-1, -1, 1, 1)
        candidates = prepared[1].Query((bounds.left(), bounds.top(), bounds.right(), bounds.bottom()))
    for otherIndex in candidates:
        if otherIndex == record["parent"]:
            continue
        other = records[otherIndex]
        wall = prepared[0][otherIndex] if prepared is not None else RecordWall(records[otherIndex])
        if "opening_obstruction" not in ignored and wall is not None and geometry.ObjectsOverlap(obj, wall, contactTolerance = 1):
            return "opening_obstruction", f"The opening is obstructed by Wall #{other.get('id', otherIndex + 1)}."
    return None


def RepairOpening(index, data):
    records = data["scene"]["objects"]
    record = records[index]
    parent = RecordWall(records[record["parent"]])
    direction = parent.secondVertex - parent.firstVertex
    length = math.hypot(direction.x(), direction.y())
    axis = direction / length
    normal = QtCore.QPointF(-axis.y(), axis.x())
    blocked = []
    for otherIndex, other in enumerate(records):
        if otherIndex == index or not isinstance(other, dict):
            continue
        if other.get("type") in openingClasses and other.get("parent") == record["parent"] and Finite(other.get("center")) and Finite(other.get("length"), 1, 1e9):
            center = other["center"] * length
            blocked.append((center - other["length"] / 2, center + other["length"] / 2))
        elif otherIndex != record["parent"]:
            wall = RecordWall(other)
            if wall is not None:
                wallDirection = wall.secondVertex - wall.firstVertex
                wallDirection /= QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
                wallNormal = QtCore.QPointF(-wallDirection.y(), wallDirection.x()) * wall.width / 2
                offsets = [vertex + sign * wallNormal - parent.firstVertex for vertex in (wall.firstVertex, wall.secondVertex) for sign in (-1, 1)]
                across = [QtCore.QPointF.dotProduct(offset, normal) for offset in offsets]
                if min(across) < parent.width / 2 and max(across) > -parent.width / 2:
                    along = [QtCore.QPointF.dotProduct(offset, axis) for offset in offsets]
                    blocked.append((min(along), max(along)))
    gaps = [(0.0, length)]
    for lower, upper in sorted(blocked):
        gaps = [part for start, end in gaps for part in ((start, min(end, lower)), (max(start, upper), end)) if part[1] - part[0] >= 1]
    candidates = []
    for start, end in gaps:
        width = min(record["length"], end - start)
        center = max(start + width / 2, min(end - width / 2, record["center"] * length))
        candidate = dict(record, center = center / length, length = width)
        trial = copy.deepcopy(data)
        trial["scene"]["objects"][index] = candidate
        if OpeningProblem(index, trial) is None:
            candidates.append((abs(center - record["center"] * length), abs(width - record["length"]), candidate))
    return min(candidates, key = lambda entry: entry[:2])[2] if candidates else None


def FindGeometryIssue(index, data, definitions, prepared = None):
    records = data["scene"]["objects"]
    record = records[index]
    kind = record.get("type") if isinstance(record, dict) else None
    issue = {"index": index, "object": f"{kind or 'Unknown object'} #{(record.get('id') or index + 1) if isinstance(record, dict) else index + 1}",
             "highlight": False, "repair": None}
    if kind not in knownObjectTypes:
        issue.update(code = "unknown", description = "This object type is unsupported. Its geometry cannot be interpreted or highlighted.")
        return issue
    if kind in openingClasses:
        parentIndex = record.get("parent")
        if type(parentIndex) is not int or not 0 <= parentIndex < len(records) or RecordWall(records[parentIndex]) is None:
            issue.update(code = "attachment", description = "The opening has no usable parent wall. Its original position cannot be determined, so Highlight and Repair are unavailable.")
            return issue
        parent = RecordWall(records[parentIndex])
        candidate = dict(record)
        invalidDimensions = False
        for name, fallback, minimum in (("center", .5, -1e12), ("length", min(900, QtCore.QLineF(parent.firstVertex, parent.secondVertex).length()), 1)):
            if not Finite(record.get(name), minimum, 1e9 if name == "length" else 1e12):
                candidate[name] = fallback
                invalidDimensions = True
        for name in ("sillDepth", "depth", "depthOffset", "wellDepth"):
            if name in record or kind == "Fireplace" and name in ("depth", "depthOffset"):
                minimum = -1e12 if name == "depthOffset" else 1 if name in ("depth", "wellDepth") else 0
                if not Finite(record.get(name), minimum, 1e9 if name in ("depth", "wellDepth") else 1e12):
                    candidate[name] = 600 if name == "wellDepth" else 0 if name == "depthOffset" else parent.width if name == "depth" else 40
                    invalidDimensions = True
        if invalidDimensions:
            issue.update(code = "dimensions", description = "The opening has impossible dimensions or coordinates.",
                         repair = candidate if candidate["length"] >= 1 else None)
            return issue
        if kind == "Fireplace":
            depth = record.get("depth", parent.width)
            limit = max(0, (depth - parent.width) / 2)
            offset = record.get("depthOffset", 0)
            if depth < parent.width or abs(offset) > limit + 1e-8:
                depth = max(parent.width, depth)
                limit = (depth - parent.width) / 2
                candidate.update(depth = depth, depthOffset = max(-limit, min(limit, offset)))
                if "fireplace_bounds" not in record.get("geometryIssues", []):
                    issue.update(code = "fireplace_bounds", description = "The fireplace depth or offset does not fit its wall.", highlight = True, repair = candidate)
                    return issue
        problem = OpeningProblem(index, data, record.get("geometryIssues", ()), prepared)
        if problem is not None and problem[0] not in record.get("geometryIssues", []):
            issue.update(code = problem[0], description = problem[1], highlight = True, repair = RepairOpening(index, data))
            return issue
        return None
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
        candidate["width"] = 0 if kind in ("MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide") else data["settings"]["wallWidth"] if kind == "Wall" else definitions.get(record.get("definition"), definitions["null"])["width"]
    if kind != "AngleGuide" and math.hypot(candidate["second"][0] - candidate["first"][0], candidate["second"][1] - candidate["first"][1]) < 1e-8:
        candidate["second"] = [candidate["first"][0] + (1000 if candidate["first"][0] <= 1e12 - 1000 else -1000), candidate["first"][1]]
    for name in ("firstMiter", "secondMiter"):
        if kind not in ("Label", "RoomLabel", "Furnishing", "NorthArrow") and not Finite(record.get(name), 0, 1):
            candidate[name] = 0
    if candidate != record:
        issue.update(code = "dimensions", description = "The object has impossible dimensions or coordinates.", repair = candidate)
        return issue
    return None


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


def ResolveGeometry(data, definitions, choose):
    data = copy.deepcopy(data)
    notices = []
    for record in data["scene"]["objects"]:
        if isinstance(record, dict) and not isinstance(record.get("type"), str):
            record["type"] = "Unknown Object"
    while True:
        records = data["scene"]["objects"]
        order = sorted(range(len(records)), key = lambda index: isinstance(records[index], dict) and records[index].get("type") in openingClasses)
        prepared = PrepareGeometryValidation(data)
        issue = next((issue for index in order if (issue := FindGeometryIssue(index, data, definitions, prepared)) is not None), None)
        if issue is None:
            break
        record = records[issue["index"]]
        if issue["repair"] is not None:
            issue["repairText"] = GeometryRepairText(record, issue["repair"])
        else:
            issue["repairText"] = "No safe repair could be found."
        children = [index for index, obj in enumerate(records) if isinstance(obj, dict) and obj.get("type") in openingClasses and obj.get("parent") == issue["index"]]
        issue["removeText"] = f"Removing this wall also removes {len(children)} attached objects." if children else "Remove deletes this object from the recovered copy."
        choice = choose(issue)
        if choice is None:
            raise GeometryLoadCancelled()
        if choice == "repair" and issue["repair"] is not None:
            records[issue["index"]] = issue["repair"]
            notices.append(f"Repaired {issue['object']}: {issue['description']}")
        elif choice == "highlight" and issue["highlight"]:
            record["geometryIssues"] = list(dict.fromkeys([*record.get("geometryIssues", []), issue["code"]]))
            notices.append(f"Highlighted {issue['object']}: {issue['description']}")
        elif choice == "remove":
            removed = {issue["index"], *children}
            mapping = {old: new for new, old in enumerate(index for index in range(len(records)) if index not in removed)}
            data["scene"]["objects"] = [obj for index, obj in enumerate(records) if index not in removed]
            for obj in data["scene"]["objects"]:
                if isinstance(obj, dict) and obj.get("type") in openingClasses and type(obj.get("parent")) is int:
                    obj["parent"] = mapping.get(obj["parent"], -1)
            data["scene"]["groups"] = [members for group in data["scene"]["groups"] if len(members := [mapping[index] for index in group if index in mapping]) >= 2]
            data["scene"]["hidden"] = [mapping[index] for index in data["scene"]["hidden"] if index in mapping]
            notices.append(f"Removed {issue['object']} and {len(children)} attached objects.")
        else:
            raise ValueError("Unavailable geometry recovery action.")
    if notices and "history" in data:
        data.pop("history")
        notices.append("Discarded undo history after geometry recovery choices.")
    return data, notices


def ActiveGeometryIssues(obj, viewport):
    issues = getattr(obj, "geometryIssues", ())
    active = []
    if isinstance(obj, Window):
        length = QtCore.QLineF(obj.parentWall.firstVertex, obj.parentWall.secondVertex).length()
        half = obj.length / (2 * max(length, 1e-8))
        if "opening_bounds" in issues and (obj.centerFraction - half < -1e-8 or obj.centerFraction + half > 1 + 1e-8):
            active.append("opening_bounds")
        if "opening_overlap" in issues and any(other is not obj and other.parentWall is obj.parentWall and viewport.OpeningsOverlap(obj, other) for other in viewport.windows):
            active.append("opening_overlap")
        if "opening_obstruction" in issues and any(type(wall) is Wall and wall is not obj.parentWall and viewport.JoinedObjectsOverlap(obj, wall, contactTolerance = 1) for wall in viewport.walls):
            active.append("opening_obstruction")
        if "fireplace_bounds" in issues and isinstance(obj, Fireplace):
            if obj.manualDepth < obj.parentWall.width or abs(obj.manualDepthOffset) > max(0, (obj.manualDepth - obj.parentWall.width) / 2) + 1e-8:
                active.append("fireplace_bounds")
    return active
