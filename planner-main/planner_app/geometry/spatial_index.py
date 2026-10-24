"""Ordered broad-phase queries on numeric (left, top, right, bottom) bounds."""
import math


class BoundsIndex:
    def __init__(self, cellSize):
        self.cellSize = max(cellSize, 1e-5)
        self.entries = []
        self.buckets = {}
        self.largeEntries = []

    def Insert(self, bounds, value):
        index = len(self.entries)
        boundLeft, boundTop, boundRight, boundBottom = bounds
        if boundRight < boundLeft:
            boundLeft, boundRight = boundRight, boundLeft
        if boundBottom < boundTop:
            boundTop, boundBottom = boundBottom, boundTop
        left, right = math.floor(boundLeft / self.cellSize), math.floor(boundRight / self.cellSize)
        top, bottom = math.floor(boundTop / self.cellSize), math.floor(boundBottom / self.cellSize)
        self.entries.append(((boundLeft, boundTop, boundRight, boundBottom), value))
        if (right - left + 1) * (bottom - top + 1) > 256:
            self.largeEntries.append(index)
            return
        for x in range(left, right + 1):
            for y in range(top, bottom + 1):
                self.buckets.setdefault((x, y), []).append(index)

    def Query(self, bounds):
        boundLeft, boundTop, boundRight, boundBottom = bounds
        if boundRight < boundLeft:
            boundLeft, boundRight = boundRight, boundLeft
        if boundBottom < boundTop:
            boundTop, boundBottom = boundBottom, boundTop
        left, right = math.floor(boundLeft / self.cellSize), math.floor(boundRight / self.cellSize)
        top, bottom = math.floor(boundTop / self.cellSize), math.floor(boundBottom / self.cellSize)
        if (right - left + 1) * (bottom - top + 1) > 256:
            candidates = range(len(self.entries))
        else:
            candidates = set(self.largeEntries)
            for x in range(left, right + 1):
                for y in range(top, bottom + 1):
                    candidates.update(self.buckets.get((x, y), ()))
            candidates = sorted(candidates)
        if boundLeft == boundRight or boundTop == boundBottom:
            return []
        # Subtraction order matters for material ownership. Touching edges and
        # zero-area rectangles do not intersect, matching the existing adapter.
        result = []
        for index in candidates:
            (entryLeft, entryTop, entryRight, entryBottom), value = self.entries[index]
            if (entryLeft < entryRight and entryTop < entryBottom
                    and boundLeft < entryRight and boundRight > entryLeft
                    and boundTop < entryBottom and boundBottom > entryTop):
                result.append(value)
        return result
