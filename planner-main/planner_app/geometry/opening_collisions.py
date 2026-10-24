"""Ordered numeric broad phase for bulk opening collision validation."""
import math
from .spatial_index import BoundsIndex


class OpeningCollisionIndex:
    def __init__(self, wallBounds, openings, cellSize = 2000):
        """Openings contain (parent key, edge bounds); outputs are source indices.

        Same-parent openings remain candidates independent of their bounds,
        including zero-area footprints. Nonfinite records fall back to full
        narrow-phase checking. Nothing is cached across validation scopes.
        """
        self.wallIndex, self.openingIndex = BoundsIndex(cellSize), BoundsIndex(cellSize)
        self.wallCount, self.openingCount = len(wallBounds), len(openings)
        self.wallFallback, self.openingFallback = [], []
        self.parents = {}
        for index, bounds in enumerate(wallBounds):
            if all(math.isfinite(value) for value in bounds):
                left, top, right, bottom = bounds
                self.wallIndex.Insert((min(left, right), min(top, bottom), max(left, right), max(top, bottom)), index)
            else:
                self.wallFallback.append(index)
        for index, (parent, bounds) in enumerate(openings):
            self.parents.setdefault(parent, []).append(index)
            if all(math.isfinite(value) for value in bounds):
                left, top, right, bottom = bounds
                self.openingIndex.Insert((min(left, right), min(top, bottom), max(left, right), max(top, bottom)), index)
            else:
                self.openingFallback.append(index)

    def Query(self, bounds, parent):
        if not all(math.isfinite(value) for value in bounds):
            return list(range(self.wallCount)), list(range(self.openingCount))
        left, top, right, bottom = bounds
        bounds = min(left, right), min(top, bottom), max(left, right), max(top, bottom)
        walls = self.wallIndex.Query(bounds)
        openings = self.openingIndex.Query(bounds)
        if self.wallFallback:
            walls = sorted(set(walls).union(self.wallFallback))
        # Preserve scene order and duplicates by source position, not object ID.
        openings = sorted(set(openings).union(self.openingFallback, self.parents.get(parent, ())))
        return walls, openings
