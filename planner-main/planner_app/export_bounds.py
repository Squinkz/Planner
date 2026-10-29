"""Visible world-space export bounds, shared by the CLI and viewport preview."""
import math
from PySide6 import QtCore, QtGui
from .models import MeasurementGuide, Furnishing, NorthArrow, Label, Arrow, Fireplace
from .graphics.furnishings import FurnishingArtworkBounds
from .graphics.symbols import DrawOpeningSymbol
from .graphics.arrows import ArrowPaths, ConnectedArrowDirections, ConnectedArrowCorners
from .graphics.object_composite import ObjectPaintDevice
from .models import Window
from .export_settings import BorderSize


def AutomaticBounds(viewport):
    minX = minY = math.inf
    maxX = maxY = -math.inf
    arrows = [obj for obj in viewport.walls if isinstance(obj, Arrow) and viewport.IsObjectVisible(obj)]
    directions = ConnectedArrowDirections(arrows)
    corners = ConnectedArrowCorners(arrows, directions)
    for obj in viewport.walls + viewport.windows + viewport.furnishings + viewport.labels:
        if not viewport.IsObjectVisible(obj):
            continue
        points = viewport.ObjectFootprint(obj)[1]
        if isinstance(obj, Window) and not isinstance(obj, Fireplace):
            # Use the renderer's actual vector commands, in a local screen-space
            # frame. Physical footprints omit swings, sills and parked leaves.
            origin = obj.firstVertex
            delta = obj.secondVertex - origin
            device = ObjectPaintDevice(QtCore.QSize(1, 1), "#ffffff")
            with QtGui.QPainter(device) as painter:
                DrawOpeningSymbol(painter, QtCore.QPointF(), QtCore.QPointF(delta.x(), -delta.y()), obj.width, type(obj),
                    hingeAtSecond = getattr(obj, "hingeAtSecond", False), swingsOutwards = getattr(obj, "swingsOutwards", False),
                    panelsFlipped = getattr(obj, "panelsFlipped", False), pixelsPerMillimeter = 1,
                    sillDepth = getattr(obj, "sillDepth", 40), windowWell = obj.windowWell,
                    wellDepth = obj.wellDepth, wellDashed = obj.wellDashed)
            for path, pen, brush, transform, opacity, clip, mask, hints, brushOrigin in device.engine.commands:
                bounds = transform.map(path).boundingRect()
                points = list(points) + [origin + QtCore.QPointF(bounds.left(), -bounds.top()),
                                         origin + QtCore.QPointF(bounds.right(), -bounds.bottom())]
        if isinstance(obj, Arrow):
            first, second, showTip = directions[id(obj)]
            origin = first
            tail, head = ArrowPaths(QtCore.QPointF(), second - origin, obj.width, obj.solidTip, obj.tipSize, 1, showTip,
                                    [[point - origin for point in polygon] for polygon in corners[id(obj)]])
            for path in (tail, head):
                if not path.isEmpty():
                    bounds = path.boundingRect().translated(origin)
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
