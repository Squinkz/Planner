"""Room contour topology, stable areas and indexed assignment without Qt."""
import math
from .spatial_index import BoundsIndex


def ClassifyRoomContours(contours, bounds, containsPoint):
    """Containment is a read-only backend query on (contour index, numeric point)."""
    sizes = sorted(max(right - left, bottom - top) for left, top, right, bottom in bounds if right > left and bottom > top)
    index = BoundsIndex(sizes[len(sizes) // 2] if sizes else 1)
    for position, rect in enumerate(bounds):
        index.Insert(rect, position)
    depths, children = {}, {}
    for position, polygon in enumerate(contours):
        point = polygon[0]
        # Pick a representable point just inside an edge. Traced corners can
        # lie a few floating-point steps outside their enclosing contour.
        for first, second in zip(polygon, polygon[1:]):
            deltaX, deltaY = second[0] - first[0], second[1] - first[1]
            length = math.hypot(deltaX, deltaY)
            if not length:
                continue
            midpoint = ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)
            epsilon = min(length / 1000, max(1e-6, 16 * math.ulp(max(abs(midpoint[0]), abs(midpoint[1]), 1))))
            scale = epsilon / length
            offsetX, offsetY = -deltaY * scale, deltaX * scale
            candidates = ((midpoint[0] + offsetX, midpoint[1] + offsetY), (midpoint[0] - offsetX, midpoint[1] - offsetY))
            inside = next((candidate for candidate in candidates if containsPoint(position, candidate)), None)
            if inside is not None:
                point = inside
                break
        left, top = point[0] - .0001, point[1] - .0001
        candidates = index.Query((left, top, left + .0002, top + .0002))
        containing = [other for other in candidates if other != position and containsPoint(other, point)]
        depths[position] = len(containing)
        if containing:
            parent = min(containing, key = lambda other: (bounds[other][2] - bounds[other][0]) * (bounds[other][3] - bounds[other][1]))
            children.setdefault(parent, []).append(position)
    return depths, children


def ContourArea(polygon):
    # Translate before the shoelace sum so small rooms retain precision far
    # from the world origin. Preserve traversal and summation order.
    origin = polygon[0]
    points = [(point[0] - origin[0], point[1] - origin[1]) for point in polygon]
    return abs(sum(first[0] * second[1] - second[0] * first[1]
                   for first, second in zip(points, points[1:] + points[:1]))) / 2


def PlanRoomRegions(contours, depths, children):
    for position, depth in depths.items():
        if depth % 2 == 0:
            continue
        boundaries = (position, *children.get(position, ()))
        area = 0.0
        for boundary in boundaries:
            value = ContourArea(contours[boundary])
            area += value if boundary == position else -value
        yield boundaries, max(0.0, area)


def FindContainingRegion(point, index, containsRegion):
    """Keep spatial-query order and return the first containing candidate."""
    left, top = point[0] - .0001, point[1] - .0001
    for region in index.Query((left, top, left + .0002, top + .0002)):
        if containsRegion(region):
            return region
    return None
