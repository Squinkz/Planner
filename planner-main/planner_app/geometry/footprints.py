"""Numeric wall bodies, rectangular footprints and curved-column approximations."""
import math


def WallBody(first, second, width):
    # The caller transforms endpoints and width before body normalization.
    firstX, firstY = first
    secondX, secondY = second
    deltaX, deltaY = secondX - firstX, secondY - firstY
    length = math.hypot(deltaX, deltaY)
    if length < 1e-10:
        return ()
    factor = width / (2 * length)
    offsetX, offsetY = -deltaY * factor, deltaX * factor
    return ((firstX + offsetX, firstY + offsetY), (secondX + offsetX, secondY + offsetY),
            (secondX - offsetX, secondY - offsetY), (firstX - offsetX, firstY - offsetY))


def RectangleFootprint(first, second, width):
    """Return a rectangle specification (x, y, width, height), corners and axes.

    Retain origin/extent separately: converting to edge bounds and back changes
    floating-point results at large world offsets.
    """
    firstX, firstY = first
    secondX, secondY = second
    deltaX, deltaY = secondX - firstX, secondY - firstY
    length = math.hypot(deltaX, deltaY)
    if length < 1e-8:
        return (0.0, 0.0, 0.0, 0.0), (), ()
    direction = (deltaX / length, deltaY / length)
    normal = (-direction[1], direction[0])
    offsetX, offsetY = normal[0] * (width / 2), normal[1] * (width / 2)
    corners = ((firstX + offsetX, firstY + offsetY), (secondX + offsetX, secondY + offsetY),
               (secondX - offsetX, secondY - offsetY), (firstX - offsetX, firstY - offsetY))
    rectangle = (min(firstX, secondX) - abs(offsetX), min(firstY, secondY) - abs(offsetY),
                 abs(deltaX) + 2 * abs(offsetX), abs(deltaY) + 2 * abs(offsetY))
    return rectangle, corners, (direction, normal)


def ColumnHandleCorners(first, second, width):
    deltaX, deltaY = second[0] - first[0], second[1] - first[1]
    length = math.hypot(deltaX, deltaY)
    if length < 1e-8:
        return ()
    factor = width / (2 * length)
    offsetX, offsetY = -deltaY * factor, deltaX * factor
    return ((first[0] + offsetX, first[1] + offsetY), (second[0] + offsetX, second[1] + offsetY),
            (second[0] - offsetX, second[1] - offsetY), (first[0] - offsetX, first[1] - offsetY))


def ColumnPolygon(along, width, tolerance = .5):
    """Relative ellipse vertices; the adapter retains and translates this shape."""
    length = math.hypot(*along)
    if length < 1e-8 or width <= 0:
        return ()
    factor = width / (2 * length)
    acrossX, acrossY = -along[1] * factor, along[0] * factor
    radius = max(length, width / 2)
    step = math.acos(max(-1, min(1, 1 - tolerance / radius)))
    count = max(16, 4 * math.ceil(math.pi / (4 * step)))
    polygon = []
    for index in range(count):
        cosine = math.cos(index * math.tau / count)
        sine = math.sin(index * math.tau / count)
        polygon.append((acrossX * cosine + along[0] * sine, acrossY * cosine + along[1] * sine))
    return tuple(polygon)


def PolygonAxes(corners):
    axes = []
    for index, point in enumerate(corners):
        following = corners[(index + 1) % len(corners)]
        deltaX, deltaY = following[0] - point[0], following[1] - point[1]
        length = math.hypot(deltaX, deltaY)
        axes.append((-deltaY / length, deltaX / length))
    return axes


def ColumnContains(first, second, width, position):
    alongX, alongY = (second[0] - first[0]) / 2, (second[1] - first[1]) / 2
    length = math.hypot(alongX, alongY)
    if length < 1e-8 or width <= 0:
        return False
    offsetX = position[0] - (first[0] + second[0]) / 2
    offsetY = position[1] - (first[1] + second[1]) / 2
    directionX, directionY = alongX / length, alongY / length
    return (((offsetX * directionX + offsetY * directionY) / length) ** 2
            + ((offsetX * -directionY + offsetY * directionX) / (width / 2)) ** 2 <= 1)


def FireplacePolygon(first, second, direction, normal, width, depth, depthOffset, flipped):
    centerX = (first[0] + second[0]) / 2 + normal[0] * depthOffset
    centerY = (first[1] + second[1]) / 2 + normal[1] * depthOffset
    if flipped:
        normal = (-normal[0], -normal[1])
    return tuple((centerX + direction[0] * (x * width) + normal[0] * (y * depth),
                  centerY + direction[1] * (x * width) + normal[1] * (y * depth))
                 for x, y in ((-.5, -.5), (-.5, .5), (.5, .5), (.5, -.5),
                              (.30, -.5), (.20, 0), (-.20, 0), (-.30, -.5)))


def FireplaceFootprint(first, second, normal, width, depth, depthOffset):
    centerX = (first[0] + second[0]) / 2 + normal[0] * depthOffset
    centerY = (first[1] + second[1]) / 2 + normal[1] * depthOffset
    offsetX, offsetY = normal[0] * (depth / 2), normal[1] * (depth / 2)
    return RectangleFootprint((centerX - offsetX, centerY - offsetY),
                              (centerX + offsetX, centerY + offsetY), width)
