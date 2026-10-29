"""Activity-log transport validation, fingerprints and descriptions without Qt."""
import base64
import hashlib
import json
import math
import re
import zlib
from datetime import datetime


activityByteLimit = 64 * 1024 * 1024


def EncodeActivityLog(data):
    raw = json.dumps(data, ensure_ascii = False, separators = (",", ":"), allow_nan = False).encode("utf-8")
    if len(raw) > activityByteLimit:
        raise ValueError("The activity log exceeds the 64 MiB limit. Clear the log before saving.")
    return dict(version = 1, encoding = "zlib-base64", data = base64.b64encode(zlib.compress(raw)).decode("ascii"))


def EncodeActivityStacks(stacks, sceneLinks, digests, fingerprint):
    """Bind opaque journal tokens to retained descriptions, caching lazy digests."""
    links = {}
    for name, stack in stacks.items():
        links[name] = []
        for token, edit in stack:
            entryId = sceneLinks.get(token)
            if entryId is not None and token not in digests:
                digests[token] = fingerprint(edit)
            links[name].append([entryId, digests[token]] if entryId is not None else None)
    return links


def RestoreActivityStacks(data, stacks, fingerprint):
    sceneLinks, digests = {}, {}
    for name, stack in stacks.items():
        if len(stack) != len(data[name]):
            continue
        for (token, edit), link in zip(stack, data[name]):
            if link is not None and fingerprint(edit) == link[1]:
                sceneLinks[token] = link[0]
                digests[token] = link[1]
    return sceneLinks, digests


def DecodeActivityLog(record):
    if record is None:
        return None
    try:
        if (not isinstance(record, dict) or set(record) != {"version", "encoding", "data"}
                or type(record["version"]) is not int or record["version"] != 1 or record["encoding"] != "zlib-base64"):
            raise ValueError()
        if not isinstance(record["data"], str) or len(record["data"]) > activityByteLimit:
            raise ValueError()
        decoder = zlib.decompressobj()
        payload = decoder.decompress(base64.b64decode(record["data"], validate = True), activityByteLimit + 1)
        if len(payload) > activityByteLimit or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError()
        data = json.loads(payload)
        if not isinstance(data, dict) or set(data) != {"entries", "undo", "redo", "issues", "gridStep"}:
            raise ValueError()
        entries = data["entries"]
        if not isinstance(entries, list):
            raise ValueError()
        ids = set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"id", "time", "kind", "summary", "details", "objects", "anchor"}:
                raise ValueError()
            if type(entry["id"]) is not int or entry["id"] <= 0 or entry["id"] in ids:
                raise ValueError()
            ids.add(entry["id"])
            for key, limit in (("kind", 32), ("summary", 4096), ("details", 65536)):
                if not isinstance(entry[key], str) or len(entry[key]) > limit:
                    raise ValueError()
            if entry["time"] is not None:
                if not isinstance(entry["time"], str) or len(entry["time"]) > 40:
                    raise ValueError()
                timestamp = datetime.fromisoformat(entry["time"])
                if timestamp.tzinfo is None or not 1900 <= timestamp.year <= 9998:
                    raise ValueError()
            if not isinstance(entry["objects"], list) or any(type(value) is not int or value <= 0 for value in entry["objects"]):
                raise ValueError()
            anchor = entry["anchor"]
            if anchor is not None and (not isinstance(anchor, dict) or set(anchor) != {"scope", "edit", "side"}
                    or anchor["scope"] not in ("Scene", "Export") or type(anchor["edit"]) is not int
                    or anchor["edit"] <= 0 or anchor["side"] not in ("before", "after")):
                raise ValueError()
        for name in ("undo", "redo"):
            if not isinstance(data[name], list) or len(data[name]) > 200:
                raise ValueError()
            for link in data[name]:
                if link is not None and (not isinstance(link, list) or len(link) != 2
                        or type(link[0]) is not int or link[0] not in ids or not isinstance(link[1], str)
                        or len(link[1]) != 64 or any(char not in "0123456789abcdef" for char in link[1])):
                    raise ValueError()
        if any(entry["anchor"] and entry["anchor"]["edit"] not in ids for entry in entries):
            raise ValueError()
        if not isinstance(data["issues"], dict) or len(data["issues"]) > 100000:
            raise ValueError()
        for key, issue in data["issues"].items():
            if not isinstance(key, str) or not isinstance(issue, dict) or set(issue) != {"object", "label", "fingerprint"}:
                raise ValueError()
            if type(issue["object"]) is not int or issue["object"] <= 0 or not isinstance(issue["label"], str) or len(issue["label"]) > 4096:
                raise ValueError()
            if issue["fingerprint"] is not None and (not isinstance(issue["fingerprint"], str) or len(issue["fingerprint"]) > 128):
                raise ValueError()
        if type(data["gridStep"]) not in (int, float) or not 0 < data["gridStep"] <= 1e12:
            raise ValueError()
        return data
    except (ValueError, TypeError, KeyError, OverflowError, zlib.error, RecursionError) as error:
        raise ValueError("Invalid activity log.") from error



def ActivityRecordFingerprint(record):
    # Project decoding normalizes numeric fields to floats. Equivalent 200 and
    # 200.0 values must identify the same retained edit after reopening.
    record = json.loads(json.dumps(record), parse_int = float)
    return hashlib.sha256(json.dumps(record, sort_keys = True, separators = (",", ":"),
                                    ensure_ascii = False, allow_nan = False).encode("utf-8")).hexdigest()



def DescribeReferenceChange(names):
    names = set(names)
    verb = ("Loaded" if "data" in names else "Resized" if names & {"width", "height"} else
            "Rotated" if "angle" in names else "Moved" if "center" in names else "Changed")
    return verb + " Reference Image", ", ".join(sorted(names)) or "Rotation pivot", []


def DescribeRecordChanges(changes, groups = False, hidden = False, orders = False):
    descriptions, objects = [], []
    for category, kind, name, objectId, created, deleted, first, second in changes:
        if kind == "Furnishing":
            name = "Furnishing"
        elif name == "MeasurementGuide":
            name = "Dimension Guide"
        else:
            name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
        verb = "Created" if created else "Deleted" if deleted else "Changed"
        if not created and not deleted:
            changed = {key for key in first if first[key] != second.get(key)}
            if "text" in changed:
                verb = "Renamed" if kind == "RoomLabel" else "Edited text of"
            elif changed <= {"first", "second", "middle", "center"}:
                if category == 3:
                    verb = "Moved"
                else:
                    delta = [second["first"][axis] - first["first"][axis] for axis in (0, 1)]
                    other = [second["second"][axis] - first["second"][axis] for axis in (0, 1)]
                    verb = "Moved" if all(abs(a - b) < 1e-6 for a, b in zip(delta, other)) else "Reshaped"
                    if verb == "Reshaped" and category in (5, 8):
                        oldLength = math.dist(first["first"], first["second"])
                        newLength = math.dist(second["first"], second["second"])
                        verb = "Rotated" if math.isclose(oldLength, newLength, abs_tol = 1e-6) else "Resized"
            elif changed & {"width", "length"}:
                verb = "Resized"
            elif "material" in changed:
                verb = "Changed material of"
            elif "intensity" in changed:
                verb = "Changed opacity of"
            elif changed & {"hingeAtSecond", "swingsOutwards", "panelsFlipped", "flipHorizontal", "flipVertical"}:
                verb = "Flipped"
            elif "directionReversed" in changed:
                verb = "Reversed"
            elif "measurementFlipped" in changed:
                verb = "Flipped dimensions of"
        descriptions.append(f"{verb} {name} #{objectId:04d}")
        objects.append(objectId)
    if not descriptions:
        if groups:
            descriptions.append("Changed object groups")
        elif hidden:
            descriptions.append("Changed object visibility")
        elif orders:
            descriptions.append("Changed object order")
        else:
            descriptions.append("Edited scene")
    summary = descriptions[0] if len(descriptions) == 1 else f"{descriptions[0]} (+{len(descriptions) - 1} objects)"
    return summary, "\n".join(descriptions), sorted(set(objects))

