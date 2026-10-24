"""Frozen Qt primitives from the verified pre-extraction backup."""

"""Convex polygon subtraction without Qt path boolean precision loss."""
from PySide6 import QtCore, QtGui


def SplitPolygon(points, first, second, orientation):
    inside, outside = [], []
    edge = second - first
    edgeX, edgeY = edge.x(), edge.y()
    firstX, firstY = first.x(), first.y()
    distances = [(edgeX * (point.y() - firstY) - edgeY * (point.x() - firstX)) * orientation for point in points]
    for index, point in enumerate(points):
        nextPoint = points[(index + 1) % len(points)]
        distance = distances[index]
        nextDistance = distances[(index + 1) % len(points)]
        (inside if distance >= 0 else outside).append(point)
        if (distance >= 0) != (nextDistance >= 0):
            crossing = point + (nextPoint - point) * (distance / (distance - nextDistance))
            inside.append(crossing)
            outside.append(crossing)
    return inside, outside


def SubtractConvexPolygon(points, cutter):
    if not QtGui.QPolygonF(points).boundingRect().intersects(QtGui.QPolygonF(cutter).boundingRect()):
        return [points]
    coordinates = [(point.x(), point.y()) for point in cutter]
    area = sum(firstX * coordinates[(index + 1) % len(coordinates)][1] -
               coordinates[(index + 1) % len(coordinates)][0] * firstY
               for index, (firstX, firstY) in enumerate(coordinates))
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
            coordinates = [(point.x(), point.y()) for point in outside]
            area = abs(sum(firstX * coordinates[(index + 1) % len(coordinates)][1] -
                           coordinates[(index + 1) % len(coordinates)][0] * firstY
                           for index, (firstX, firstY) in enumerate(coordinates)))
            if area > 1e-7:
                fragments.append(outside)
    return fragments

"""Ordered broad-phase queries with bounded storage for oversized bounds."""
import math


class BoundsIndex:
    def __init__(self, cellSize):
        self.cellSize = max(cellSize, 1e-5)
        self.entries = []
        self.buckets = {}
        self.largeEntries = []

    def Insert(self, bounds, value):
        index = len(self.entries)
        self.entries.append((bounds, value))
        left, right = math.floor(bounds.left() / self.cellSize), math.floor(bounds.right() / self.cellSize)
        top, bottom = math.floor(bounds.top() / self.cellSize), math.floor(bounds.bottom() / self.cellSize)
        if (right - left + 1) * (bottom - top + 1) > 256:
            self.largeEntries.append(index)
            return
        for x in range(left, right + 1):
            for y in range(top, bottom + 1):
                self.buckets.setdefault((x, y), []).append(index)

    def Query(self, bounds):
        left, right = math.floor(bounds.left() / self.cellSize), math.floor(bounds.right() / self.cellSize)
        top, bottom = math.floor(bounds.top() / self.cellSize), math.floor(bounds.bottom() / self.cellSize)
        if (right - left + 1) * (bottom - top + 1) > 256:
            candidates = range(len(self.entries))
        else:
            candidates = set(self.largeEntries)
            for x in range(left, right + 1):
                for y in range(top, bottom + 1):
                    candidates.update(self.buckets.get((x, y), ()))
            candidates = sorted(candidates)
        # Subtraction order matters for material ownership; retain insertion order.
        return [self.entries[index][1] for index in candidates if bounds.intersects(self.entries[index][0])]
