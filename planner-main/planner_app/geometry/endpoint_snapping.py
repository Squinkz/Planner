"""Numeric footprint-cap recovery and endpoint snap candidate policy."""
import math


def NearestRunControlTarget(origin, direction, targets, angleLocked, distance, limit = math.inf):
    """Choose an eligible control point in discovery order using native distances.

    The distance callback receives source indices, retaining world/screen units
    and native rounding. Targets are unused placeholders when the angle is free.
    """
    nearest = None
    nearestDistance = limit
    for index, target in enumerate(targets):
        if angleLocked:
            offsetX, offsetY = target[0] - origin[0], target[1] - origin[1]
            if (abs(offsetX * direction[1] - offsetY * direction[0]) > .01
                    or offsetX * direction[0] + offsetY * direction[1] < 0):
                continue
        measured = distance(index)
        if measured < nearestDistance:
            nearest, nearestDistance = index, measured
    return None if nearest is None else (nearest, nearestDistance)


def CapEndpoint(snapped, opposite, offset, normal, width, angleLocked):
    if angleLocked:
        return snapped[0] - offset[0], snapped[1] - offset[1]
    # Recover the centerline from a cap corner without changing the width as
    # the run rotates. Corners inside the half-width circle have no solution.
    x, y = snapped[0] - opposite[0], snapped[1] - opposite[1]
    radius = math.hypot(x, y)
    halfWidth = width / 2
    if radius <= halfWidth:
        return None
    runLength = math.sqrt(radius * radius - halfWidth * halfWidth)
    side = 1 if offset[0] * normal[0] + offset[1] * normal[1] > 0 else -1
    angle = math.atan2(y, x) - math.atan2(side * halfWidth, runLength)
    return opposite[0] + math.cos(angle) * runLength, opposite[1] + math.sin(angle) * runLength


def AlignmentPlacementCandidates(candidates, aligned, alignmentOnly, controlGuides):
    """Yield unique placements in collision-test order, with fallbacks last.

    Distance values and guide payloads come from the caller. Keep discovery
    order on ties and do not modify any input collections.
    """
    ordered = sorted(candidates, key = lambda candidate: candidate[0])
    ordered.extend((0, candidate, controlGuides) for candidate in (aligned, alignmentOnly))
    tested = set()
    for distance, candidate, guides in ordered:
        if candidate in tested:
            continue
        tested.add(candidate)
        yield candidate, guides


def SelectEndpointSnap(position, opposite, candidates, alignmentCandidates, straightWall):
    """Select geometry/alignment before grid, preserving straight-wall ties."""
    if not candidates:
        return position, False, 3, []
    selfAlignments = [candidate for candidate in alignmentCandidates if straightWall
                      and any(abs(coordinate - opposite[axis]) <= .01 for axis, coordinate in candidate[3])]
    priority, distance, target, guides = min(candidates, key = lambda candidate:
        (candidate[0], 0 if candidate in selfAlignments else 1, candidate[1]))
    guides = guides if priority == 1 else []
    if straightWall:
        guides = [(axis, coordinate) for axis, coordinate in guides if abs(target[axis] - coordinate) <= .01]
    return target, True, priority, guides
