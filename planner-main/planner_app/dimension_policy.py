"""Action eligibility follows potential ambient dimensions, never selection bounds."""
from dataclasses import dataclass
from .geometry.measurements import EffectiveWallSplitSettings
from PySide6 import QtCore, QtGui
from .models import (Wall, Pillar, Column, Elevator, Stair, Counter, Railing, Window, Fireplace,
                     Door, DoubleDoor, SwingingDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor,
                     OpenDoorway, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow,
                     MeasurementGuide, BoundaryLine)


@dataclass(frozen = True)
class DimensionActions:
    canHide: bool = False
    canFlip: bool = False


def AvailableDimensionActions(viewport, obj):
    if obj is None or not viewport.IsObjectVisible(obj):
        return DimensionActions()
    # Standalone dimension annotations draw independently of the ambient master.
    if isinstance(obj, MeasurementGuide):
        return DimensionActions(canHide = not isinstance(obj, BoundaryLine))
    if not viewport.showMeasurements:
        return DimensionActions()
    category = ("stairs" if isinstance(obj, Stair) else "counters" if isinstance(obj, Counter) else
                "railings" if isinstance(obj, Railing) else "walls")
    if not viewport.measurementVisibility[category]:
        return DimensionActions()
    if not isinstance(obj, Window) and type(obj) not in (Wall, Pillar, Column, Stair, Counter, Railing):
        return DimensionActions()
    if isinstance(obj, Elevator):
        return DimensionActions()
    key = viewport.SceneRenderKey(("dimension-actions", id(obj)))
    cache = getattr(viewport, "dimensionActionCache", None)
    if cache is None:
        viewport.dimensionActionCache = cache = {}
    if key in cache:
        return cache[key]
    stacked = viewport.wallMeasurementMode == "Exterior stacked"
    settings = (dict(viewport.measurementSettings, doors = 0, windows = 0, stairs = 2, counters = 2)
                if stacked else EffectiveWallSplitSettings(viewport.measurementSettings, viewport.wallMeasurementMode))
    canFlip = False
    openingCategory = None
    if isinstance(obj, Window):
        if obj.parentWall.measurementHidden or not viewport.IsObjectVisible(obj.parentWall):
            return DimensionActions()
        openingCategory = ("doors" if isinstance(obj, (Door, DoubleDoor, SwingingDoor, SlidingDoor,
                           PocketDoor, BarnDoor, BifoldDoor, OpenDoorway)) else "windows")
        split = settings[openingCategory]
        if split == 2 and not isinstance(obj, Fireplace):
            return DimensionActions()
        canFlip = not obj.measurementHidden and viewport.wallMeasurementMode == "All" and split == 1 and type(obj) in (
            Door, DoubleDoor, SlidingDoor, BarnDoor, Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow)
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
