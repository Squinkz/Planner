"""Polygon operations on sequences of numeric (x, y) pairs.

Coordinates keep the caller's coordinate system. Polygon order, winding,
fragment order and the existing clipping tolerances are preserved.
"""


def ClipHalfPlane(points, origin, normal):
    """Keep dot(point - origin, normal) <= 0; neither input is mutated."""
    clipped = []
    distances = [(x - origin[0]) * normal[0] + (y - origin[1]) * normal[1] for x, y in points]
    for index, first in enumerate(points):
        second = points[(index + 1) % len(points)]
        firstDistance, secondDistance = distances[index], distances[(index + 1) % len(points)]
        if firstDistance <= 0:
            clipped.append(first)
        if (firstDistance <= 0) != (secondDistance <= 0):
            fraction = firstDistance / (firstDistance - secondDistance)
            clipped.append((first[0] + (second[0] - first[0]) * fraction,
                            first[1] + (second[1] - first[1]) * fraction))
    return clipped


def SplitPolygon(points, first, second, orientation):
    inside, outside = [], []
    firstX, firstY = first
    edgeX, edgeY = second[0] - firstX, second[1] - firstY
    distances = [(edgeX * (y - firstY) - edgeY * (x - firstX)) * orientation for x, y in points]
    for index, point in enumerate(points):
        nextPoint = points[(index + 1) % len(points)]
        distance, nextDistance = distances[index], distances[(index + 1) % len(points)]
        (inside if distance >= 0 else outside).append(point)
        if (distance >= 0) != (nextDistance >= 0):
            fraction = distance / (distance - nextDistance)
            crossing = (point[0] + (nextPoint[0] - point[0]) * fraction,
                        point[1] + (nextPoint[1] - point[1]) * fraction)
            inside.append(crossing)
            outside.append(crossing)
    return inside, outside


def SubtractConvexPolygon(points, cutter):
    """Return outside fragments in the same order as sequential edge clipping.

    The cutter must be convex. Degenerate bounds/cutters leave the subject intact;
    discard thresholds are in the caller's squared coordinate units, as before.
    Neither input is mutated. An unchanged subject is returned by reference.
    """
    bounds = []
    for polygon in (points, cutter):
        if not polygon:
            bounds.append((0, 0, 0, 0))
            continue
        left, top = polygon[0]
        right, bottom = left, top
        for x, y in polygon[1:]:
            if x < left:
                left = x
            elif x > right:
                right = x
            if y < top:
                top = y
            elif y > bottom:
                bottom = y
        # Preserve the prior origin/extent arithmetic at extreme offsets,
        # including its floating-point rounding at the far rectangle edges.
        bounds.append((left, top, left + (right - left), top + (bottom - top)))
    left, top, right, bottom = bounds[0]
    cutterLeft, cutterTop, cutterRight, cutterBottom = bounds[1]
    if (left >= right or top >= bottom or cutterLeft >= cutterRight or cutterTop >= cutterBottom
            or left >= cutterRight or right <= cutterLeft or top >= cutterBottom or bottom <= cutterTop):
        return [points]
    area = sum(x * cutter[(index + 1) % len(cutter)][1] - cutter[(index + 1) % len(cutter)][0] * y
               for index, (x, y) in enumerate(cutter))
    if abs(area) < 1e-9:
        return [points]
    orientation = 1 if area > 0 else -1
    fragments = []
    remaining = list(points)
    for index, first in enumerate(cutter):
        if len(remaining) < 3:
            break
        remaining, outside = SplitPolygon(remaining, first, cutter[(index + 1) % len(cutter)], orientation)
        if len(outside) >= 3:
            area = abs(sum(x * outside[(index + 1) % len(outside)][1] - outside[(index + 1) % len(outside)][0] * y
                           for index, (x, y) in enumerate(outside)))
            if area > 1e-7:
                fragments.append(outside)
    return fragments
