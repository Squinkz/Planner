"""Numeric export crop and ruler interaction policy, independent of widgets."""
import math


def MoveCropOrigin(origin, axis, coordinate, step = None):
    if step is not None:
        coordinate = math.copysign(math.floor(abs(coordinate) / step + .5) * step, coordinate)
    result = list(origin)
    result[axis] = coordinate
    return result


def MoveCropEdge(bounds, edge, coordinate, reset = False, step = None, origin = 0):
    x, y, width, height = bounds
    edges = [x, x + width, y, y + height]
    opposite = edge ^ 1
    if reset:
        edges[edge] = coordinate
        # A reset lands exactly on the automatic guide and moves a crossed
        # opposite guide only as far as needed to retain a positive crop.
        if edge % 2 == 0 and edges[opposite] <= coordinate:
            edges[opposite] = coordinate + 1
        elif edge % 2 == 1 and edges[opposite] >= coordinate:
            edges[opposite] = coordinate - 1
    else:
        if step is not None:
            relative = coordinate - origin
            coordinate = origin + math.copysign(math.floor(abs(relative) / step + .5) * step, relative)
            limit = origin + ((math.ceil((edges[opposite] - origin) / step) - 1) * step if edge % 2 == 0
                     else (math.floor((edges[opposite] - origin) / step) + 1) * step)
        else:
            limit = edges[opposite] - 1 if edge % 2 == 0 else edges[opposite] + 1
        edges[edge] = min(coordinate, limit) if edge % 2 == 0 else max(coordinate, limit)
    return edges[0], edges[2], edges[1] - edges[0], edges[3] - edges[2]


def HitCropEdge(position, first, second):
    distances = (abs(position[0] - first[0]), abs(position[0] - second[0]),
                 abs(position[1] - first[1]), abs(position[1] - second[1]))
    edge = min(range(4), key = lambda index: distances[index])
    return edge if distances[edge] <= 8 else None


def HitCropRuler(position, crop, border):
    x, y = position
    left, top, right, bottom = crop
    if left <= x <= right and (top - border <= y < top or bottom < y <= bottom + border):
        return 0
    if top <= y <= bottom and (left - border <= x < left or right < x <= right + border):
        return 1
    return None
