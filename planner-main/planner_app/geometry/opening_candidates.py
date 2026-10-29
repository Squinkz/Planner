"""Opening facing and fireplace snap candidates using numeric coordinates."""
import math


def OpeningFacingChanges(first, second, position, pixelsPerMillimeter, policy):
    directionX, directionY = second[0] - first[0], second[1] - first[1]
    length = math.hypot(directionX, directionY)
    if length < 1e-10:
        return {}
    directionX /= length
    directionY /= length
    offsetX = position[0] - (first[0] + second[0]) / 2
    offsetY = position[1] - (first[1] + second[1]) / 2
    along = offsetX * directionX + offsetY * directionY
    across = offsetX * -directionY + offsetY * directionX
    hingeSign, sideField, sideSign = policy
    changes = {}
    # Strict pixel thresholds preserve the current value on either divider.
    if hingeSign and abs(along) * pixelsPerMillimeter > 2:
        changes["hingeAtSecond"] = along * hingeSign > 0
    if sideField is not None and abs(across) * pixelsPerMillimeter > 2:
        changes[sideField] = across * sideSign > 0
    return changes


def FireplaceDepthSnap(offset, targets, basePixelsPerMillimeter, zoom, snapRange):
    if targets:
        target = min(targets, key = lambda target: abs(target - offset))
        if abs(target - offset) * basePixelsPerMillimeter * zoom <= snapRange:
            return target
    return None


def FireplacePlacementCandidates(originalFraction, openingLength, wallLength, offset, limit,
                                direction, normal, placements, offsetSnap):
    """Yield in snap priority order so the adapter can reject collisions lazily.

    Guide payloads are opaque and returned unchanged. Stable sorting retains
    discovery order for equally ranked snaps, including the unsnapped fallback.
    """
    halfSpan = openingLength / (2 * wallLength)
    for priority, distance, correction, guides in sorted(placements, key = lambda candidate: candidate[:2]):
        fraction = originalFraction + (correction[0] * direction[0] + correction[1] * direction[1]) / wallLength
        depthOffset = offset + (correction[0] * normal[0] + correction[1] * normal[1])
        # Depth snapping can accompany a lateral correction, but must not
        # override a candidate that already corrects the depth independently.
        applyOffsetSnap = offsetSnap is not None and abs(depthOffset - offset) < 1e-8
        if applyOffsetSnap:
            depthOffset = offsetSnap
        if not halfSpan - 1e-8 <= fraction <= 1 - halfSpan + 1e-8 or abs(depthOffset) > limit + 1e-8:
            continue
        yield (max(halfSpan, min(1 - halfSpan, fraction)), depthOffset, guides,
               priority < 3 or applyOffsetSnap, min(priority, 1) if applyOffsetSnap else priority)
