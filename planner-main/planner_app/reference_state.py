"""Reference-image metadata and edit proposals, independent of Qt and decoding."""
import math


imageByteLimit = 40 * 1024 * 1024


def ValidateReferenceState(record):
    """Validate metadata; embedded image contents still require a decoder."""
    if not isinstance(record, dict):
        raise ValueError("Invalid reference image settings.")
    if not isinstance(record.get("path"), str) or "\0" in record["path"]:
        raise ValueError("Invalid reference image path.")
    encoded = record.get("data")
    if not isinstance(encoded, str) or len(encoded) > (imageByteLimit + 2) // 3 * 4:
        raise ValueError("Invalid embedded reference image.")
    if type(record.get("visible")) is not bool:
        raise ValueError("Invalid reference image visibility.")
    center = record.get("center")
    if not isinstance(center, list) or len(center) != 2:
        raise ValueError("Invalid reference image position.")
    values = center + [record.get(name) for name in ("width", "height", "angle", "opacity")]
    if any(type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e12 for value in values):
        raise ValueError("Invalid reference image dimensions or position.")
    if record["width"] < 1 or record["height"] < 1 or not 0 <= record["opacity"] <= 1:
        raise ValueError("Invalid reference image dimensions or opacity.")
    return {name: list(record[name]) if name == "center" else record[name] for name in
            ("path", "data", "visible", "center", "width", "height", "angle", "opacity")}


def EditReferenceProperty(state, name, value, pivot = None, rotating = False, linked = False):
    """Propose an edit in millimeters/degrees; None rejects a linked resize."""
    candidate = dict(state, center = list(state["center"]))
    if name in ("x", "y"):
        index = 0 if name == "x" else 1
        position = pivot if rotating and pivot is not None else state["center"]
        delta = value - position[index]
        candidate["center"][index] += delta
        if pivot is not None:
            pivot = (pivot[0] + (delta if index == 0 else 0), pivot[1] + (delta if index == 1 else 0))
    elif name == "angle":
        if rotating and pivot is not None:
            angle = math.radians(value - state["angle"])
            offsetX, offsetY = state["center"][0] - pivot[0], state["center"][1] - pivot[1]
            candidate["center"] = [pivot[0] + (offsetX * math.cos(angle) - offsetY * math.sin(angle)),
                                   pivot[1] + (offsetX * math.sin(angle) + offsetY * math.cos(angle))]
        candidate["angle"] = value
    else:
        dimension = "width" if name == "width" else "height"
        size = max(1, value)
        if linked:
            other = "height" if name == "width" else "width"
            otherSize = state[other] * size / state[dimension]
            if not 1 <= otherSize <= 1e12:
                return None
            candidate[other] = otherSize
        candidate[dimension] = size
    return candidate, pivot


def CalibrateReferenceState(state, first, second, distance, pivot = None):
    measured = math.hypot(second[0] - first[0], second[1] - first[1])
    if not math.isfinite(distance) or distance <= 0 or measured <= 1e-6:
        raise ValueError("Enter a distance greater than zero.")
    factor = distance / measured
    # The first picked point stays fixed while the image scales uniformly.
    center = [first[index] + (state["center"][index] - first[index]) * factor for index in (0, 1)]
    width, height = state["width"] * factor, state["height"] * factor
    if any(not math.isfinite(value) or abs(value) > 1e12 for value in (*center, width, height)) or min(width, height) < 1:
        raise ValueError("That distance would make the reference image too small or too large.")
    candidate = dict(state, center = center, width = width, height = height)
    if pivot is not None:
        pivot = tuple(first[index] + (pivot[index] - first[index]) * factor for index in (0, 1))
    return candidate, pivot
