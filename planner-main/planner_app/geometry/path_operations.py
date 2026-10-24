"""Backend contract for opaque native paths; no graphics imports or global backend."""
from typing import Protocol, Callable


class PathOperations(Protocol):
    """Handles belong to one backend/coordinate system; operations do not mutate inputs.

    Retain fill rules, curve direction, contour order and operation order. Stroke
    defaults are backend defaults, not synthesized caps/joins or flattened curves.
    Callers own transforms, coordinate normalization, broad phases and caches.
    """
    def Empty(self): ...
    def Union(self, first, second): ...
    def Intersection(self, first, second): ...
    def Difference(self, first, second): ...
    def Contains(self, path, point): ...
    def Intersects(self, first, second): ...
    def Contours(self, path): ...
    def FillPolygons(self, path): ...
    def PrepareStroke(self, width = None, cap = None, join = None, miterLimit = None,
                      dashPattern = None, dashOffset = None, curveThreshold = None) -> Callable: ...


def ClipPathCoverage(backend, canvas, masks, clip = None):
    """Subtract ordered local coverage, then apply an optional existing clip.

    Masks must already be culled/transformed by the caller. Preserve sequential
    booleans: combining/reordering masks can change finite-precision curve output.
    """
    covered = backend.Empty()
    for mask in masks:
        covered = backend.Union(covered, mask)
    visible = backend.Difference(canvas, covered)
    if clip is not None:
        visible = backend.Intersection(visible, clip)
    return visible
