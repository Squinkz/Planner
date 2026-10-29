"""Numeric measurement spans; visibility policy and retained caches belong to callers."""
import math
from dataclasses import dataclass


def GuideDepthOffset(first, second, depth):
    """World offset toward the upright guide's lower side, independent of endpoint order."""
    deltaX, deltaY = second[0] - first[0], second[1] - first[1]
    length = math.hypot(deltaX, deltaY)
    if depth == 0 or length < 1e-10:
        return 0.0, 0.0
    if deltaX < 0 or deltaX == 0 and deltaY > 0:
        deltaX, deltaY = -deltaX, -deltaY
    return deltaY / length * depth, -deltaX / length * depth


def MergeMeasurementSegments(polygon):
    segments = []
    for first, second in zip(polygon, polygon[1:]):
        deltaX, deltaY = second[0] - first[0], second[1] - first[1]
        length = math.hypot(deltaX, deltaY)
        if length < .0001:
            continue
        direction = (deltaX / length, deltaY / length)
        if segments and math.hypot(segments[-1][2][0] - direction[0], segments[-1][2][1] - direction[1]) < 1e-6:
            segments[-1] = (segments[-1][0], second, direction)
        else:
            segments.append((first, second, direction))
    if len(segments) > 1 and math.hypot(segments[-1][2][0] - segments[0][2][0],
                                        segments[-1][2][1] - segments[0][2][1]) < 1e-6:
        segments[0] = (segments[-1][0], segments[0][1], segments[0][2])
        segments.pop()
    return segments


def FindMeasurementOwners(first, second, direction, candidates):
    """Candidates: (opaque key, x, y, axisX, axisY, length, halfWidth, caps)."""
    midpointX, midpointY = (first[0] + second[0]) / 2, (first[1] + second[1]) / 2
    directionX, directionY = direction
    owners = []
    for key, wallX, wallY, axisX, axisY, wallLength, halfWidth, caps in candidates:
        cross = directionX * axisY - directionY * axisX
        if abs(cross) >= 1e-6:
            if caps and abs(directionX * axisX + directionY * axisY) < 1e-6:
                along = (midpointX - wallX) * axisX + (midpointY - wallY) * axisY
                across = abs((midpointX - wallX) * axisY - (midpointY - wallY) * axisX)
                if min(abs(along), abs(along - wallLength)) < .01 and across <= halfWidth + .01:
                    owners.append(key)
            continue
        across = abs((midpointX - wallX) * axisY - (midpointY - wallY) * axisX)
        if abs(across - halfWidth) < .01:
            firstAlong = (first[0] - wallX) * axisX + (first[1] - wallY) * axisY
            secondAlong = (second[0] - wallX) * axisX + (second[1] - wallY) * axisY
            if max(firstAlong, secondAlong) > 0 and min(firstAlong, secondAlong) < wallLength:
                owners.append(key)
    return owners


def PrepareMeasurementPolygons(polygons):
    """Precompute the original convex projection slabs once per geometry change."""
    prepared = []
    for polygon in polygons:
        axes = []
        for index, point in enumerate(polygon):
            following = polygon[(index + 1) % len(polygon)]
            edgeX, edgeY = following[0] - point[0], following[1] - point[1]
            length = math.hypot(edgeX, edgeY)
            if length < 1e-8:
                continue
            axisX, axisY = -edgeY / length, edgeX / length
            projections = [vertex[0] * axisX + vertex[1] * axisY for vertex in polygon]
            axes.append((axisX, axisY, min(projections) - .01, max(projections) + .01))
        prepared.append(tuple(axes))
    return prepared


def CoveredMeasurementSpans(first, direction, length, polygons, minimum, mergeTolerance = None):
    spans = []
    for axes in polygons:
        start, end = 0.0, length
        for axisX, axisY, low, high in axes:
            origin = first[0] * axisX + first[1] * axisY
            slope = direction[0] * axisX + direction[1] * axisY
            if abs(slope) < 1e-8:
                if origin < low or origin > high:
                    end = -1.0
                    break
            else:
                bounds = sorted(((low - origin) / slope, (high - origin) / slope))
                start, end = max(start, bounds[0]), min(end, bounds[1])
            if end <= start:
                break
        if end - start > minimum:
            spans.append((start, end))
    if mergeTolerance is not None:
        # Adjacent footprint pieces must not introduce internal measurement cuts.
        merged = []
        for start, end in sorted(spans):
            if merged and start <= merged[-1][1] + mergeTolerance:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        return merged
    return spans


def OpeningOnMeasuredSide(midpoint, parentFirst, parentSecond, flipped):
    normalX, normalY = -(parentSecond[1] - parentFirst[1]), parentSecond[0] - parentFirst[0]
    if flipped:
        normalX, normalY = -normalX, -normalY
    return (midpoint[0] - parentFirst[0]) * normalX + (midpoint[1] - parentFirst[1]) * normalY > 0


def OpeningProjection(first, direction, openingFirst, openingSecond, pocket = False, hingeAtSecond = False):
    if pocket:
        midpoint = ((openingFirst[0] + openingSecond[0]) / 2, (openingFirst[1] + openingSecond[1]) / 2)
        if hingeAtSecond:
            openingFirst = midpoint
        else:
            openingSecond = midpoint
    firstAlong = (openingFirst[0] - first[0]) * direction[0] + (openingFirst[1] - first[1]) * direction[1]
    secondAlong = (openingSecond[0] - first[0]) * direction[0] + (openingSecond[1] - first[1]) * direction[1]
    return min(firstAlong, secondAlong), max(firstAlong, secondAlong)


def BuildMeasurementSpan(first, second, direction, owners, interruptions, openings, fireplaces):
    """Assemble visible gaps and openings, offsetting fireplace spans to body faces.

    openings: (owner key, projected start, projected end). fireplaces: (projected
    start/end, normalX/Y, centerX/Y, depth, depthOffset). No scene models required.
    """
    length = math.hypot(second[0] - first[0], second[1] - first[1])
    dimensions = []
    cursor = 0.0
    for start, end in sorted(interruptions):
        if start - cursor > .0001:
            dimensions.append(((first[0] + direction[0] * cursor, first[1] + direction[1] * cursor),
                               (first[0] + direction[0] * start, first[1] + direction[1] * start), owners))
        openingStart = max(cursor, start)
        if end - openingStart > .0001:
            firstX, firstY = first[0] + direction[0] * openingStart, first[1] + direction[1] * openingStart
            secondX, secondY = first[0] + direction[0] * end, first[1] + direction[1] * end
            for low, high, normalX, normalY, centerX, centerY, depth, depthOffset in fireplaces:
                if openingStart < low - .01 or end > high + .01:
                    continue
                wallSide = (((firstX + secondX) / 2 - centerX) * normalX
                            + ((firstY + secondY) / 2 - centerY) * normalY)
                edge = depthOffset + (depth / 2 if wallSide > 0 else -depth / 2)
                shiftX, shiftY = normalX * (edge - wallSide), normalY * (edge - wallSide)
                firstX, firstY = firstX + shiftX, firstY + shiftY
                secondX, secondY = secondX + shiftX, secondY + shiftY
                break
            openingOwners = [key for key, low, high in openings if low <= openingStart + .01 and high >= end - .01]
            dimensions.append(((firstX, firstY), (secondX, secondY), openingOwners or owners))
        cursor = max(cursor, end)
    if length - cursor > .0001:
        dimensions.append(((first[0] + direction[0] * cursor, first[1] + direction[1] * cursor), second, owners))
    return dimensions


def ExposedMeasurementSpans(first, second, polygons):
    deltaX, deltaY = second[0] - first[0], second[1] - first[1]
    length = math.hypot(deltaX, deltaY)
    direction = (deltaX / length, deltaY / length)
    covered = CoveredMeasurementSpans(first, direction, length, polygons, .0001)
    exposed = []
    cursor = 0.0
    for start, end in sorted(covered):
        if start - cursor > .01:
            exposed.append(((first[0] + direction[0] * cursor, first[1] + direction[1] * cursor),
                            (first[0] + direction[0] * start, first[1] + direction[1] * start)))
        cursor = max(cursor, end)
    if length - cursor > .01:
        exposed.append(((first[0] + direction[0] * cursor, first[1] + direction[1] * cursor), second))
    return exposed


@dataclass(frozen = True, slots = True)
class MeasurementOpening:
    """Numeric opening snapshot; class/visibility policy is resolved by the adapter."""
    key: object
    first: tuple
    second: tuple
    parentFirst: tuple
    parentSecond: tuple
    mode: int
    oneSided: bool
    flipped: bool
    pocket: bool
    hingeAtSecond: bool
    fireplace: tuple | None = None


def PlanMeasurementComponents(memberGroups, openingParents, selectedKeys):
    """Ordered source indices and selection keys for each disconnected component.

    Repeated opening entries retain their indices; repeated component members do
    not duplicate an opening. No model references, graphics state or retained cache.
    """
    byParent = {}
    for index, parent in enumerate(openingParents):
        byParent.setdefault(parent, []).append(index)
    plans = []
    for members in memberGroups:
        memberKeys = set(members)
        indices = sorted(index for member in memberKeys for index in byParent.get(member, ()))
        plans.append((indices, frozenset(memberKeys.intersection(selectedKeys))))
    return plans


def EffectiveWallSplitSettings(settings, mode):
    # Exterior chains have no facing side. Preserve the stored All-mode choice
    # until the user explicitly changes a split control.
    return {key: 0 if mode == "Exterior" and value == 1 else value for key, value in settings.items()}


def BuildOpeningDimensions(first, second, direction, length, midpoint, owners, openings, cutters):
    """Coordinate interruption, side and fireplace policies for one exposed span.

    Length and midpoint are explicit to preserve the caller backend's arithmetic.
    Owner keys and opening order remain unchanged through the existing span kernel.
    """
    interruptions = CoveredMeasurementSpans(first, direction, length, cutters, .02, mergeTolerance = .02)
    projectedOpenings = []
    projectedFireplaces = []
    for opening in openings:
        if opening.mode == 2 and opening.fireplace is None:
            continue
        if opening.mode == 1 and opening.fireplace is None and opening.oneSided:
            if not OpeningOnMeasuredSide(midpoint, opening.parentFirst, opening.parentSecond, opening.flipped):
                continue
        low, high = OpeningProjection(first, direction, opening.first, opening.second,
                                      opening.pocket, opening.hingeAtSecond)
        # An inactive opening must not acquire a dimension merely because a
        # counter, stair or another opening interrupts the same span.
        projectedOpenings.append((opening.key, low, high))
        if opening.fireplace is not None:
            projectedFireplaces.append((low, high, *opening.fireplace))
        start, end = max(0.0, low), min(length, high)
        if end - start > .0001:
            interruptions.append((start, end))
    return BuildMeasurementSpan(first, second, direction, owners, interruptions, projectedOpenings, projectedFireplaces)
