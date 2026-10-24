"""Nominal catalog/default sizing for new objects; all results are millimeters."""
import math


def NominalPlacementSize(millimeters, unitsMode):
    if unitsMode in ("Feet and Inches", "Inches"):
        # Standard metric sizes map at 25 mm per nominal inch. Actual geometry
        # still uses the exact 25.4 mm inch, including above one meter.
        return max(1, math.floor(millimeters / 25 + .5)) * 25.4
    return millimeters


def FurnishingPlacementSize(definition, unitsMode):
    return tuple(NominalPlacementSize(definition[field], unitsMode) for field in ("width", "length"))
