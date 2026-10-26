"""Visible world-space export bounds, shared by the CLI and viewport preview."""
import math
from .models import MeasurementGuide, Furnishing, NorthArrow, Label
from .graphics.furnishings import FurnishingArtworkBounds
from .graphics.symbols import WindowWellPath
from .models import Window


def BorderSize(style, requested = 28):
    # Nine-pixel major ticks need clearance; labels and unit corners need more.
    minimum = {"None": 0, "Plain": 1, "Frame": 4, "Corner Marks": 4, "Reference Zones": 28, "Marked": 12, "Ruler": 28, "Ruler + Reference Zones": 56}[style]
    return max(minimum, requested) if style != "None" else 0


def AutomaticBounds(viewport):
    minX = minY = math.inf
    maxX = maxY = -math.inf
    for obj in viewport.walls + viewport.windows + viewport.furnishings + viewport.labels:
        if not viewport.IsObjectVisible(obj):
            continue
        points = viewport.ObjectFootprint(obj)[1]
        if isinstance(obj, Window) and obj.windowWell:
            bounds = WindowWellPath(obj.firstVertex, obj.secondVertex, obj.width, obj.wellDepth,
                                    swingsOutwards = not obj.swingsOutwards).boundingRect()
            points = list(points) + [bounds.topLeft(), bounds.bottomRight()]
        if isinstance(obj, MeasurementGuide):
            bounds = viewport.ObjectFootprint(obj)[0]
            points = list(points) + [bounds.topLeft(), bounds.bottomRight()]
        if isinstance(obj, Furnishing) and not isinstance(obj, (NorthArrow, Label)):
            renderer = viewport.furnishingRenderers.get(obj.definition["key"])
            if renderer is not None:
                artwork = FurnishingArtworkBounds(obj, renderer)
                points = list(points) + [artwork.topLeft(), artwork.bottomRight()]
        for point in points:
            minX, minY = min(minX, point.x()), min(minY, point.y())
            maxX, maxY = max(maxX, point.x()), max(maxY, point.y())
    if minX == math.inf:
        raise ValueError("Cannot detect automatic bounds: the plan has no visible objects.")
    border = 1000.0
    return (minX - border, minY - border, maxX - minX + 2 * border, maxY - minY + 2 * border)
