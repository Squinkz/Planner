"""Stair and railing sizing from numeric lengths, points and spacing limits."""
import math


sizingCountLimit = 100000


def RailingPostCount(length, spacingBounds, manualCount = None):
    if manualCount is not None:
        return max(2, manualCount)
    minimum, maximum, target = spacingBounds
    minimumCount = max(1, math.ceil(length / maximum - 1e-10))
    maximumCount = max(1, math.floor(length / minimum + 1e-10))
    if minimumCount <= maximumCount:
        count = max(minimumCount, min(maximumCount, int(length / target + .5)))
    else:
        count = min({minimumCount, maximumCount}, key = lambda count:
                    (max(minimum - length / count, 0, length / count - maximum), abs(length / count - target)))
    return count + 1


def StairLandingTrims(first, second, width, neighbors):
    """Neighbors are (first point, second point, width), excluding this stair."""
    neighbors = tuple(neighbors)
    trims = []
    for vertex, endpoint in ((first, second), (second, first)):
        directionX, directionY = endpoint[0] - vertex[0], endpoint[1] - vertex[1]
        length = math.hypot(directionX, directionY)
        trim = 0.0
        if length > 1e-10:
            inverseLength = 1 / length
            directionX, directionY = directionX * inverseLength, directionY * inverseLength
            for otherFirst, otherSecond, otherWidth in neighbors:
                if math.hypot(vertex[0] - otherFirst[0], vertex[1] - otherFirst[1]) <= .01:
                    otherX, otherY = otherSecond[0] - otherFirst[0], otherSecond[1] - otherFirst[1]
                elif math.hypot(vertex[0] - otherSecond[0], vertex[1] - otherSecond[1]) <= .01:
                    otherX, otherY = otherFirst[0] - otherSecond[0], otherFirst[1] - otherSecond[1]
                else:
                    continue
                otherLength = math.hypot(otherX, otherY)
                if otherLength < 1e-10:
                    continue
                inverseLength = 1 / otherLength
                otherX, otherY = otherX * inverseLength, otherY * inverseLength
                cross = abs(directionX * otherY - directionY * otherX)
                if cross < 1e-6:
                    continue
                dot = directionX * otherX + directionY * otherY
                innerDistance = (otherWidth / 2 + width / 2 * dot) / cross
                intersectionDistance = math.hypot(width / 2, innerDistance)
                if dot < 0 and abs(width - otherWidth) > 1e-6 and intersectionDistance > 2 * max(width, otherWidth):
                    continue
                trim = max(trim, min(length, max(0.0, innerDistance)))
        trims.append(trim)
    return tuple(trims)


def StairStepLayout(length, trims, stepSizeBounds, manualCount = None):
    firstTrim, secondTrim = trims
    runLength = max(0.0, length - firstTrim - secondTrim)
    landingCount = int(firstTrim > 1e-8) + int(secondTrim > 1e-8)
    if runLength < 1e-8:
        return 0, 0.0, landingCount
    if manualCount is not None:
        treadCount = max(1, manualCount - landingCount)
        return treadCount, runLength / treadCount, landingCount
    minimumSize, maximumSize = stepSizeBounds
    targetSize = (minimumSize + maximumSize) / 2
    minimumCount = max(1, math.ceil(runLength / maximumSize - 1e-10))
    maximumCount = math.floor(runLength / minimumSize + 1e-10)
    if minimumCount <= maximumCount:
        treadCount = max(minimumCount, min(maximumCount, round(runLength / targetSize)))
    else:
        # A short run may not fit any whole number of treads within the bounds.
        candidates = {minimumCount, max(1, maximumCount)}
        treadCount = min(candidates, key = lambda count: (max(minimumSize - runLength / count, 0, runLength / count - maximumSize),
                                                         abs(runLength / count - targetSize)))
    return treadCount, runLength / treadCount, landingCount


def StairCountForStepSize(length, trims, size):
    firstTrim, secondTrim = trims
    runLength = max(0.0, length - firstTrim - secondTrim)
    landingCount = int(firstTrim > 1e-8) + int(secondTrim > 1e-8)
    return min(sizingCountLimit, max(1, int(runLength / max(size, .001) + .5)) + landingCount)
