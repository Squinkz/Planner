"""Desktop property-unit adapter; numeric formatting lives in measurement_units."""
from .property_edits import PropertyScale
from .measurement_units import (MetricUnit, GridUnit, FormatLength, FormatArea, ParseImperialLength,
                                imperialModes, unitModes, measurementPrecisions)


def PropertyUnit(fieldName, obj, mode):
    adaptive = "cm" if PropertyScale(fieldName, type(obj).__name__) == 10 else "m"
    return MetricUnit(mode, adaptive)
