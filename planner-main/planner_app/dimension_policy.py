"""Action eligibility follows potential ambient dimensions, never selection bounds."""
from .dimension_actions import DimensionActions, ImmediateDimensionActions, PlanDimensionActions
from .geometry.measurements import EffectiveWallSplitSettings
from PySide6 import QtCore, QtGui
from .models import (Wall, Pillar, Column, Elevator, Stair, Counter, Railing, Window, Fireplace,
                     Door, DoubleDoor, SwingingDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor,
                     OpenDoorway, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow,
                     MeasurementGuide, BoundaryLine)


def AvailableDimensionActions(viewport, obj):
    if obj is None:
        return DimensionActions()
    kind = type(obj).__name__
    immediate = ImmediateDimensionActions(kind, viewport.IsObjectVisible(obj), viewport.showMeasurements, viewport.measurementVisibility)
    if immediate is not None:
        return immediate
    key = viewport.SceneRenderKey(("dimension-actions", id(obj)))
    cache = getattr(viewport, "dimensionActionCache", None)
    if cache is None:
        viewport.dimensionActionCache = cache = {}
    if key in cache:
        return cache[key]
    stacked = viewport.wallMeasurementMode == "Exterior stacked"
    opening = isinstance(obj, Window)
    immediate, settings, canFlip = PlanDimensionActions(kind, viewport.wallMeasurementMode, viewport.measurementSettings,
        obj.measurementHidden, parentHidden = obj.parentWall.measurementHidden if opening else False,
        parentVisible = viewport.IsObjectVisible(obj.parentWall) if opening else True)
    if immediate is not None:
        return immediate
    walls = [wall for wall in viewport.walls if type(wall) in (Wall, Pillar, Column) and viewport.IsObjectVisible(wall)]
    path = viewport.ConnectedWallPath(walls)
    if viewport.wallMeasurementMode != "All":
        viewport.roomDetection.UpdateBoundary()
        scale = viewport.basePixelsPerMillimeter * viewport.zoom
        origin = viewport.WorldToViewport(QtCore.QPointF())
        path = QtGui.QTransform(scale, 0, 0, -scale, origin.x(), origin.y()).map(viewport.roomDetection.exteriorPath)
    if isinstance(obj, (Stair, Counter, Railing)):
        members = [wall for wall in viewport.walls if type(wall) is type(obj) and viewport.IsObjectVisible(wall)]
        spans = (viewport.StairDimensions(members) if isinstance(obj, Stair) else
                 viewport.ConnectedCounterPath(members, True)[1] if isinstance(obj, Counter) else
                 viewport.ConnectedRailingPath(members, True)[1])
    else:
        # Ignore only the queried object's hidden flag so Show remains available.
        openings = [opening for opening in viewport.windows if viewport.IsObjectVisible(opening)
                    and (not opening.measurementHidden or opening is obj)
                    and (not opening.parentWall.measurementHidden or opening.parentWall is obj)]
        spans = viewport.WallDimensions(walls, path, openings, measurementSettings = settings)
        if stacked and not isinstance(obj, Window):
            spans = spans + viewport.WallDimensions(walls, path, openings,
                measurementSettings = dict(settings, doors = 2, windows = 2))
    canHide = any(obj in owners or type(obj) is Wall and any(isinstance(owner, Window) and owner.parentWall is obj for owner in owners)
                  for first, second, owners in spans)
    if type(obj) is Column and viewport.wallMeasurementMode == "All":
        canHide = True  # Columns have their own ambient bounding dimensions.
    result = DimensionActions(canHide, canFlip)
    cache[key] = result
    while len(cache) > 128:
        cache.pop(next(iter(cache)))
    return result
