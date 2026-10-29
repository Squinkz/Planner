"""Numeric edit transforms; model mutation, snapping and transactions stay outside."""
import math


def PointerRotation(offset, mouseAngle, initialAngle = None, snapping = False, local = False):
    """Return angle and rotation components from the captured gesture frame.

    Furnishings ignore the tiny disk around their pivot and snap relative to
    their captured angle in local mode. Structural selections use a relative
    angle, including at the pivot, and always snap that delta from zero.
    """
    if initialAngle is not None and not math.hypot(*offset) > 1e-8:
        return None
    pointerAngle = math.degrees(math.atan2(offset[1], offset[0]))
    angle = pointerAngle - mouseAngle if initialAngle is None else initialAngle + pointerAngle - mouseAngle
    if snapping:
        if initialAngle is None:
            angle = round(angle / 15) * 15
        else:
            origin = initialAngle if local else 0
            angle = origin + round((angle - origin) / 15) * 15
    rotation = math.radians(angle if initialAngle is None else angle - initialAngle)
    return angle, math.cos(rotation), math.sin(rotation)


def SelectionResizeCorrection(center, originalCenter, originalWidth, originalLength, bounds, field, sign, centered):
    """Keep a resized selection's stationary edge at its captured position."""
    left, top, width, height = bounds
    boundsCenterX, boundsCenterY = left + width / 2, top + height / 2
    x, y = center[0] - boundsCenterX, center[1] - boundsCenterY
    if field == "width" and not centered:
        anchoredX = originalCenter[0] - sign * originalWidth / 2
        x = anchoredX - (boundsCenterX - sign * width / 2)
    elif field == "length" and not centered:
        anchoredY = originalCenter[1] - sign * originalLength / 2
        y = anchoredY - (boundsCenterY - sign * height / 2)
    return x, y


def TransformPoint(point, origin, delta, cosine, sine):
    offsetX, offsetY = point[0] - origin[0], point[1] - origin[1]
    target = (origin[0] + (offsetX * cosine - offsetY * sine),
              origin[1] + (offsetX * sine + offsetY * cosine))
    if delta is not None:
        return target[0] + delta[0], target[1] + delta[1]
    return target


def OpeningTransformTarget(first, second, origin, delta, cosine, sine):
    center = ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)
    directionX, directionY = second[0] - first[0], second[1] - first[1]
    return (TransformPoint(center, origin, delta, cosine, sine),
            (directionX * cosine - directionY * sine, directionX * sine + directionY * cosine))


def ReattachTransformedOpening(target, targetDirection, first, second):
    directionX, directionY = second[0] - first[0], second[1] - first[1]
    lengthSquared = directionX * directionX + directionY * directionY
    offsetX, offsetY = target[0] - first[0], target[1] - first[1]
    length = math.sqrt(lengthSquared)
    if (length < 1 or abs(offsetX * directionY - offsetY * directionX) > .01 * length
            or abs(targetDirection[0] * directionY - targetDirection[1] * directionX) > .01 * length):
        return None
    return ((offsetX * directionX + offsetY * directionY) / lengthSquared,
            targetDirection[0] * directionX + targetDirection[1] * directionY < 0)


def RebaseMergedOpening(center, oldDirection, first, direction, length, openingLength):
    fraction = ((center[0] - first[0]) * direction[0] + (center[1] - first[1]) * direction[1]) / (length * length)
    halfSpan = openingLength / (2 * length)
    fits = halfSpan <= fraction <= 1 - halfSpan
    flipped = oldDirection[0] * direction[0] + oldDirection[1] * direction[1] < 0
    return fraction, fits, flipped


def OpeningOrientationChanges(fields, reversedAlongWall, reflected = False):
    """Return changed host-relative fields, leaving source data untouched.

    Reversing the tangent exchanges endpoint/hinge identities. Side flags
    and signed depth also depend on whether the transform reflects handedness.
    Measurement overrides stay relative to the artwork and are retained.
    """
    changes = {}
    if reversedAlongWall and "hingeAtSecond" in fields:
        changes["hingeAtSecond"] = not fields["hingeAtSecond"]
    if bool(reversedAlongWall) != bool(reflected):
        for name in ("swingsOutwards", "panelsFlipped"):
            if name in fields:
                changes[name] = not fields[name]
        if "depthOffset" in fields:
            changes["depthOffset"] = -fields["depthOffset"]
    return changes


def AngleEndpoints(first, second, length, angle):
    centerX, centerY = (first[0] + second[0]) / 2, (first[1] + second[1]) / 2
    radians = math.radians(angle % 360)
    halfX, halfY = -math.sin(radians) * (length / 2), math.cos(radians) * (length / 2)
    return (centerX - halfX, centerY - halfY), (centerX + halfX, centerY + halfY)


def ResizeHandleDimensions(north, width, length, delta, field, sign, centered, minimumSize):
    east = (north[1], -north[0])
    factor = 2 if centered else 1
    if field == "corner":
        eastSign, northSign = sign
        diagonalX = east[0] * (eastSign * width) + north[0] * (northSign * length)
        diagonalY = east[1] * (eastSign * width) + north[1] * (northSign * length)
        scale = 1 + factor * (delta[0] * diagonalX + delta[1] * diagonalY) / (diagonalX * diagonalX + diagonalY * diagonalY)
        scale = max(minimumSize / min(width, length), scale)
        return width * scale, length * scale
    axis = north if field == "length" else east
    size = max(1.0, (length if field == "length" else width)
               + factor * sign * (delta[0] * axis[0] + delta[1] * axis[1]))
    return (width, size) if field == "length" else (size, length)


def ResizedHandleCenter(center, north, oldWidth, oldLength, width, length, field, sign, centered):
    if centered:
        return center
    east = (north[1], -north[0])
    if field == "corner":
        eastSign, northSign = sign
        centerX = center[0] + east[0] * (eastSign * (width - oldWidth) / 2)
        centerY = center[1] + east[1] * (eastSign * (width - oldWidth) / 2)
        return (centerX + north[0] * (northSign * (length - oldLength) / 2),
                centerY + north[1] * (northSign * (length - oldLength) / 2))
    axis = north if field == "length" else east
    size, oldSize = (length, oldLength) if field == "length" else (width, oldWidth)
    return (center[0] + axis[0] * (sign * (size - oldSize) / 2),
            center[1] + axis[1] * (sign * (size - oldSize) / 2))


def PrepareSelectionMembers(members, origin):
    """Input records: key, first, second, width, angle, original native length."""
    prepared = []
    for key, first, second, width, angle, length in members:
        northX, northY = (second[0] - first[0]) / length, (second[1] - first[1]) / length
        offsetX, offsetY = (first[0] + second[0]) / 2 - origin[0], (first[1] + second[1]) / 2 - origin[1]
        prepared.append((key, offsetX, offsetY, length, northX, northY, northY, -northX, width, angle))
    return prepared


def SelectionSpan(members, scaleX, scaleY, axis):
    minimum, maximum = float("inf"), -float("inf")
    for key, offsetX, offsetY, length, northX, northY, eastX, eastY, width, angle in members:
        scaledWidth = width * math.hypot(eastX * scaleX, eastY * scaleY)
        scaledLength = length * math.hypot(northX * scaleX, northY * scaleY)
        center = offsetX * scaleX if axis == 0 else offsetY * scaleY
        halfSpan = ((abs(eastX) * scaledWidth + abs(northX) * scaledLength) / 2 if axis == 0 else
                    (abs(eastY) * scaledWidth + abs(northY) * scaledLength) / 2)
        minimum, maximum = min(minimum, center - halfSpan), max(maximum, center + halfSpan)
    return maximum - minimum


def FitSelectionScale(members, scaleX, scaleY, axis, desiredSpan):
    if abs(SelectionSpan(members, scaleX, scaleY, axis) - desiredSpan) > 1e-6:
        low, high = 0.0, max(1.0, scaleX if axis == 0 else scaleY)
        while SelectionSpan(members, high if axis == 0 else scaleX, high if axis == 1 else scaleY, axis) < desiredSpan:
            high *= 2
        for iteration in range(40):
            scale = (low + high) / 2
            span = SelectionSpan(members, scale if axis == 0 else scaleX, scale if axis == 1 else scaleY, axis)
            if span < desiredSpan:
                low = scale
            else:
                high = scale
        if axis == 0:
            scaleX = (low + high) / 2
        else:
            scaleY = (low + high) / 2
    return scaleX, scaleY


def TransformSelectionMembers(members, center, scaleX, scaleY, rotation):
    cosine, sine = math.cos(rotation), math.sin(rotation)
    transformed = []
    for key, offsetX, offsetY, length, northX, northY, eastX, eastY, width, angle in members:
        offsetX, offsetY = offsetX * scaleX, offsetY * scaleY
        targetX = center[0] + (offsetX * cosine - offsetY * sine)
        targetY = center[1] + (offsetX * sine + offsetY * cosine)
        width *= math.hypot(eastX * scaleX, eastY * scaleY)
        length *= math.hypot(northX * scaleX, northY * scaleY)
        first = (targetX - northX * (length / 2), targetY - northY * (length / 2))
        second = (targetX + northX * (length / 2), targetY + northY * (length / 2))
        # The model's angle setter runs afterwards, preserving its endpoint
        # center/length reconstruction and the original floating-point order.
        transformed.append((key, first, second, width, angle + math.degrees(rotation)))
    return transformed


def ChooseWallSplit(first, direction, footprints, intervals):
    intervals = sorted(intervals)
    for corners, axes in footprints:
        if not corners:
            continue
        start, end = 0.0, 1.0
        for axisX, axisY in axes:
            projections = [x * axisX + y * axisY for x, y in corners]
            low, high = min(projections), max(projections)
            origin = first[0] * axisX + first[1] * axisY
            travel = direction[0] * axisX + direction[1] * axisY
            if abs(travel) < 1e-8:
                if origin <= low + 1e-8 or origin >= high - 1e-8:
                    end = start
                    break
            else:
                lower, upper = (low - origin) / travel, (high - origin) / travel
                start, end = max(start, min(lower, upper)), min(end, max(lower, upper))
            if end <= start:
                break
        if end - start > 1e-8:
            intervals.append((start, end))
    intervals.sort()
    candidates, cursor = [], 0.0
    for start, end in intervals + [(1.0, 1.0)]:
        if start - cursor > 1e-8:
            fraction = max(cursor, min(start, .5))
            if 1e-8 < fraction < 1 - 1e-8:
                candidates.append(fraction)
        cursor = max(cursor, end)
    return min(candidates, key = lambda fraction: (abs(fraction - .5), fraction)) if candidates else None
