"""Qt-free field names and compatibility conversions for object records."""
import math

selectionObjectLimit = 10000
geometryIssueNames = ("opening_bounds", "opening_overlap", "opening_obstruction", "fireplace_bounds")


def ReadArrowTipSize(record, width):
    mode = record.get("tipSizeMode")
    if mode not in (None, "multiplier", "millimeters"):
        raise ValueError("An arrow contains an unknown tip size mode.")
    multiplier = mode == "multiplier" or mode is None and record["solidTip"]
    value = record["tipSize"]
    minimum = .1 if multiplier or mode == "millimeters" else 1
    maximum = 1000 if multiplier else 1e12
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("An arrow contains an invalid tip size.")
    if multiplier:
        value *= width
    elif mode is None:
        # The earliest open heads had a fixed 35 mm width; tipSize described
        # their stroke thickness instead. Preserve their outer dimensions.
        value = 35.0
    if not math.isfinite(value) or not 0 < value <= 1e12:
        raise ValueError("An arrow contains an invalid head dimension.")
    return value

openingFieldsByType = {
    "Fireplace": ("swingsOutwards", "depth", "depthOffset", "material", "measurementFlipped"),
    "Door": ("hingeAtSecond", "swingsOutwards", "measurementFlipped"),
    "SwingingDoor": ("hingeAtSecond", "measurementFlipped"),
    "DoubleDoor": ("swingsOutwards", "measurementFlipped"),
    "SlidingDoor": ("hingeAtSecond", "panelsFlipped", "measurementFlipped"),
    "PocketDoor": ("hingeAtSecond", "measurementFlipped"),
    "BarnDoor": ("hingeAtSecond", "swingsOutwards", "measurementFlipped"),
    "BifoldDoor": ("swingsOutwards", "measurementFlipped"),
    "OpenDoorway": ("measurementFlipped",),
    "Window": ("swingsOutwards", "measurementFlipped"),
    "SilledWindow": ("swingsOutwards", "sillDepth", "measurementFlipped"),
    "CasementWindow": ("hingeAtSecond", "swingsOutwards", "measurementFlipped"),
    "AwningWindow": ("swingsOutwards", "measurementFlipped"),
    "DoubleCasementWindow": ("swingsOutwards", "measurementFlipped"),
}
for windowType in ("Window", "SilledWindow", "CasementWindow", "AwningWindow", "DoubleCasementWindow"):
    openingFieldsByType[windowType] += ("windowWell", "wellDepth", "wellDashed")
