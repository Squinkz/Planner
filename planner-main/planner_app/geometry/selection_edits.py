"""Move/rotate and reflection plans without model mutation or scene discovery."""
from dataclasses import dataclass
import math
from operator import eq
from .affine import ReflectionFrame, TransformAffinePoint, TransformAffinePoints, NeedsNativeAffine
from .editing import TransformPoint, OpeningTransformTarget, AngleEndpoints


@dataclass(frozen = True, slots = True)
class MoveObjectRecord:
    key: object
    points: tuple
    opening: bool = False
    originIndex: int | None = None


@dataclass(frozen = True, slots = True)
class ReflectionObjectRecord:
    key: object
    points: tuple
    kind: str
    angle: float = 0.0
    flipped: bool = False
    guideOffset: tuple | None = None
    originIndex: int | None = None
    length: float | None = None


def EditLocalOrigin(points, originIndex):
    if originIndex is not None:
        return points[originIndex]
    return (points[0][0] + points[1][0]) / 2, (points[0][1] + points[1][1]) / 2


def PlanMoveSelection(records, attachments, guides, delta, angle, sharedOrigin, localOrigins = False, originsMatch = eq):
    """Selected vertices win; the first discovered attachment claims the rest.

    Attachments are (source key, target key, vertex index, captured point).
    Guides are (key, point count, offset). Owner keys remain opaque.
    """
    radians = math.radians(angle % 360)
    cosine, sine = math.cos(radians), math.sin(radians)
    vertices, origins, openingTargets = {}, {}, []
    for record in records:
        origin = EditLocalOrigin(record.points, record.originIndex) if localOrigins else sharedOrigin
        origins[record.key] = origin
        if record.opening:
            target, direction = OpeningTransformTarget(record.points[0], record.points[1], origin, delta, cosine, sine)
            openingTargets.append((record.key, target, direction))
        else:
            for index, point in enumerate(record.points):
                vertices[(record.key, index)] = point, origin
    for source, key, index, point in attachments:
        vertices.setdefault((key, index), (point, origins[source]))
    points = [(key, index, TransformPoint(point, origin, delta, cosine, sine))
              for (key, index), (point, origin) in vertices.items()]
    offsets = []
    for key, count, offset in guides:
        keys = [(key, index) for index in range(count)]
        if all(vertex in vertices for vertex in keys) and all(originsMatch(vertices[vertex][1], vertices[keys[0]][1]) for vertex in keys):
            offsets.append((key, TransformPoint(offset, (0, 0), None, cosine, sine)))
    return points, openingTargets, offsets


def PlanSelectionReflection(records, openings, sharedCenter, horizontal, local = False, value = None, backend = None):
    """Return ordered object edits and pre-mutation opening targets.

    Opening entries are (key, parent key, first, second). Parent frames take
    precedence over a selected opening's own frame. Readable text keeps its
    orientation policy and artwork uses flip flags instead of negative sizes.
    """
    if not records:
        return [], []
    frames = {}
    sharedFrame = ReflectionFrame(sharedCenter, 0.0, horizontal, backend) if not local else None
    mapBackend = backend if local or (sharedFrame is not None and NeedsNativeAffine(sharedFrame)) else None
    for record in records:
        if local:
            center = EditLocalOrigin(record.points, record.originIndex)
            x, y = record.points[1][0] - record.points[0][0], record.points[1][1] - record.points[0][1]
            angle = math.degrees(math.atan2(y, x)) - 90
            frames[record.key] = ReflectionFrame(center, angle, horizontal, backend)
        else:
            frames[record.key] = sharedFrame
    targets = []
    for key, parent, first, second in openings:
        frame = frames.get(parent, frames.get(key))
        if frame is not None:
            first, second = TransformAffinePoints((first, second), frame, mapBackend)
            targets.append((key, ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2),
                            (second[0] - first[0], second[1] - first[1])))
    edits = []
    for record in records:
        if record.kind == "opening":
            continue
        frame = frames[record.key]
        if record.kind in ("artwork", "text"):
            if record.kind == "artwork" and value is not None and value == record.flipped:
                continue
            center = EditLocalOrigin(record.points, None)
            target = center if local else TransformAffinePoint(center, frame, mapBackend)
            deltaX, deltaY = target[0] - center[0], target[1] - center[1]
            points = record.points
            if not local:
                length = record.length
                if length is None:
                    length = math.hypot(points[1][0] - points[0][0], points[1][1] - points[0][1])
                points = AngleEndpoints(points[0], points[1], length, -record.angle)
            points = tuple((point[0] + deltaX, point[1] + deltaY) for point in points)
            edits.append((record.key, record.kind, points, not record.flipped if record.kind == "artwork" else None, None))
        else:
            source = record.points if record.guideOffset is None else record.points + (record.guideOffset, (0, 0))
            points = TransformAffinePoints(source, frame, mapBackend)
            offset = None
            if record.guideOffset is not None:
                target, zero = points[-2:]
                points = points[:-2]
                offset = target[0] - zero[0], target[1] - zero[1]
            edits.append((record.key, record.kind, points, None, offset))
    return edits, targets
