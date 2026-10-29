"""Proportional corner and edge resize snapping with numeric geometry."""
import math
from .snapping import SnapPoint


def SnapResize(north, center, originalWidth, originalLength, width, length, field, sign,
               centered, minimumSize, targets, scale, vertexRange, alignmentEnabled, gridStep,
               distance = math.hypot):
    """Return width, length, applied, priority and guides without changing inputs.

    Targets are the already filtered direct/alignment points, including enabled
    midpoints. A desktop backend may supply its distance primitive for exact
    anchor ties. Corner resizing retains the original aspect ratio.
    """
    northX, northY = north
    eastX, eastY = northY, -northX
    factor = 2 if centered else 1
    if field == "corner":
        eastSign, northSign = sign
        diagonalX = eastX * (eastSign * originalWidth) + northX * (northSign * originalLength)
        diagonalY = eastY * (eastSign * originalWidth) + northY * (northSign * originalLength)
        anchorX = center[0] if centered else center[0] - diagonalX / 2
        anchorY = center[1] if centered else center[1] - diagonalY / 2
        corner = (anchorX + (eastX * (eastSign * width) + northX * (northSign * length)) / factor,
                  anchorY + (eastY * (eastSign * width) + northY * (northSign * length)) / factor)
        diagonalLength = math.hypot(diagonalX, diagonalY)
        snapped, applied, priority, guides = SnapPoint(corner, targets, scale, vertexRange,
            alignmentEnabled, gridStep, (anchorX, anchorY), (diagonalX / diagonalLength, diagonalY / diagonalLength))
        resizeScale = factor * ((snapped[0] - anchorX) * diagonalX + (snapped[1] - anchorY) * diagonalY) / (diagonalX * diagonalX + diagonalY * diagonalY)
        resizeScale = max(minimumSize / min(originalWidth, originalLength), resizeScale)
        return originalWidth * resizeScale, originalLength * resizeScale, applied, priority, guides

    axisX, axisY = north if field == "length" else (eastX, eastY)
    tangentX, tangentY = (eastX, eastY) if field == "length" else north
    size = length if field == "length" else width
    originalSize = originalLength if field == "length" else originalWidth
    halfSpan = (originalWidth if field == "length" else originalLength) / 2
    anchorX = center[0] if centered else center[0] - axisX * (sign * originalSize / 2)
    anchorY = center[1] if centered else center[1] - axisY * (sign * originalSize / 2)
    edgeX = anchorX + axisX * (sign * size / factor)
    edgeY = anchorY + axisY * (sign * size / factor)
    bestKey, bestGuides, priority = None, [], 3
    for offsetX, offsetY in ((0.0, 0.0), (tangentX * halfSpan, tangentY * halfSpan),
                             (-tangentX * halfSpan, -tangentY * halfSpan)):
        point = edgeX + offsetX, edgeY + offsetY
        snapped, applied, priority, guides = SnapPoint(point, targets, scale, vertexRange,
            alignmentEnabled, gridStep, (anchorX + offsetX, anchorY + offsetY), (axisX * sign, axisY * sign))
        if applied:
            snappedSize = factor * sign * (((snapped[0] - anchorX) - offsetX) * axisX + ((snapped[1] - anchorY) - offsetY) * axisY)
            if snappedSize >= 1:
                key = priority, distance(point[0] - snapped[0], point[1] - snapped[1])
                if bestKey is None or key < bestKey:
                    bestKey, bestSize, bestGuides = key, snappedSize, guides
    # A vertex can meet any point of the edge, not just the three anchors.
    for targetX, targetY, direct in targets:
        if not direct:
            continue
        offsetX, offsetY = targetX - edgeX, targetY - edgeY
        if abs(offsetX * tangentX + offsetY * tangentY) > halfSpan + .01:
            continue
        separation = abs(offsetX * axisX + offsetY * axisY)
        snappedSize = factor * sign * ((targetX - anchorX) * axisX + (targetY - anchorY) * axisY)
        if separation * scale < vertexRange and snappedSize >= 1:
            key = 0, separation
            if bestKey is None or key < bestKey:
                bestKey, bestSize, bestGuides = key, snappedSize, []
    if bestKey is not None:
        size, priority = bestSize, bestKey[0]
    # With no accepted candidate the last point probe's priority is retained,
    # including a grid probe that had no eligible intersection with the ray.
    width, length = (width, size) if field == "length" else (size, length)
    return width, length, bestKey is not None, priority, bestGuides
