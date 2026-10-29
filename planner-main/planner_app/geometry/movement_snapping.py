"""Movement frames, angular constraints and multi-anchor snapping without Qt."""
import math
from .snapping import PrepareTargetIndex, PrepareRayTargets, SnapPoint


def MovementAxes(first, second, sideways = False):
    x, y = second[0] - first[0], second[1] - first[1]
    length = math.hypot(x, y)
    if length < 1e-10:
        return (1.0, 0.0), (0.0, 1.0)
    x, y = x / length, y / length
    return ((y, -x), (x, y)) if sideways else ((x, y), (-y, x))


def ConstraintAxes(original):
    reference = math.atan2(original[1], original[0]) if math.hypot(*original) > 1e-10 else 0.0
    # Twelve infinite lines represent twenty-four rays, fifteen degrees apart.
    return tuple((math.cos(reference + index * math.pi / 12), math.sin(reference + index * math.pi / 12))
                 for index in range(12))


def ConstrainedAngle(direction, referenceAxis):
    reference = math.atan2(referenceAxis[1], referenceAxis[0])
    angleStep = math.radians(15)
    return reference + round((math.atan2(direction[1], direction[0]) - reference) / angleStep) * angleStep


def ConstrainMovement(delta, direction = None, constrain = False, axes = None):
    x, y = delta
    if direction is not None:
        along = x * direction[0] + y * direction[1]
        x, y = direction[0] * along, direction[1] * along
        if x * direction[0] + y * direction[1] < 0:
            direction = -direction[0], -direction[1]
    elif constrain:
        if axes is not None:
            direction = max(axes, key = lambda axis: abs(x * axis[0] + y * axis[1]))
            if x * direction[0] + y * direction[1] < 0:
                direction = -direction[0], -direction[1]
        elif abs(x) >= abs(y):
            direction = (-1.0 if x < 0 else 1.0), 0.0
        else:
            direction = 0.0, (-1.0 if y < 0 else 1.0)
        along = x * direction[0] + y * direction[1]
        x, y = direction[0] * along, direction[1] * along
    return (x, y), direction


def SnapMovement(anchors, delta, targets, scale, vertexRange, alignmentEnabled, gridStep,
                 direction = None, distance = math.hypot):
    """Return travel, applied, priority and guides with stable anchor ties.

    Targets are prepared once per movement, retaining the existing thresholds
    for indexed point and ray lookup. The input collections are read-only.
    A backend may supply its distance primitive to retain its floating-point
    tie behavior; all selection policy remains here.
    """
    targetIndex, rayTargets = None, None
    if len(targets) > 32:
        if direction is None:
            targetIndex = PrepareTargetIndex(targets)
        elif len(anchors) >= 3:
            rayTargets = PrepareRayTargets(targets)
    bestKey, guides, priority = None, [], 3
    result = delta
    for anchor in anchors:
        moved = anchor[0] + delta[0], anchor[1] + delta[1]
        snapped, applied, candidatePriority, candidateGuides = SnapPoint(
            moved, targets, scale, vertexRange, alignmentEnabled, gridStep,
            anchor if direction is not None else None, direction, targetIndex, rayTargets)
        if applied:
            key = candidatePriority, distance(moved[0] - snapped[0], moved[1] - snapped[1])
            if bestKey is None or key < bestKey:
                bestKey = key
                result = snapped[0] - anchor[0], snapped[1] - anchor[1]
                priority = candidatePriority
                guides = candidateGuides if priority == 1 else []
    if direction is not None:
        along = max(0.0, result[0] * direction[0] + result[1] * direction[1])
        result = direction[0] * along, direction[1] * along
    return result, bestKey is not None, priority, guides
