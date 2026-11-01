from planner_app.geometry.polygons import PolygonTwiceArea, SplitPolygon


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
    area = PolygonTwiceArea(cutter)
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
            area = abs(PolygonTwiceArea(outside))
            if area > 1e-7:
                fragments.append(outside)
    return fragments
