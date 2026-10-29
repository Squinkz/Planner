"""Dimension-action eligibility and split policy without scene or graphics types."""
from dataclasses import dataclass
from .geometry.measurements import EffectiveWallSplitSettings
from .record_schema import openingFieldsByType


@dataclass(frozen = True)
class DimensionActions:
    canHide: bool = False
    canFlip: bool = False


def ImmediateDimensionActions(kind, visible, showMeasurements, visibility):
    if not visible:
        return DimensionActions()
    if kind in ("MeasurementGuide", "BoundaryLine", "DashedLine", "SolidLine", "AngleGuide"):
        return DimensionActions(canHide = kind not in ("BoundaryLine", "DashedLine", "SolidLine"))
    if not showMeasurements:
        return DimensionActions()
    category = "stairs" if kind == "Stair" else "counters" if kind == "Counter" else "railings" if kind == "Railing" else "walls"
    if not visibility[category]:
        return DimensionActions()
    if kind not in openingFieldsByType and kind not in ("Wall", "Pillar", "Column", "Stair", "Counter", "Railing"):
        return DimensionActions()
    return None


def PlanDimensionActions(kind, mode, measurementSettings, hidden, parentHidden = False, parentVisible = True):
    settings = (dict(measurementSettings, doors = 0, windows = 0, stairs = 2, counters = 2)
                if mode == "Exterior stacked" else EffectiveWallSplitSettings(measurementSettings, mode))
    canFlip = False
    if kind in openingFieldsByType:
        if parentHidden or not parentVisible:
            return DimensionActions(), settings, False
        category = "doors" if kind in ("Door", "DoubleDoor", "SwingingDoor", "SlidingDoor", "PocketDoor", "BarnDoor", "BifoldDoor", "OpenDoorway") else "windows"
        split = settings[category]
        if split == 2 and kind != "Fireplace":
            return DimensionActions(), settings, False
        canFlip = not hidden and mode == "All" and split == 1 and kind in (
            "Door", "DoubleDoor", "SlidingDoor", "BarnDoor", "Window", "SilledWindow", "CasementWindow", "AwningWindow", "DoubleCasementWindow")
    return None, settings, canFlip
