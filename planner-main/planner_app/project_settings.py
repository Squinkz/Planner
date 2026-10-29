"""Project preference and saved panel-state validation without Qt."""
import base64
from .record_validation import ValidateFlags, ValidateNumber
from .measurement_units import unitModes, measurementPrecisions
from .preferences import (wallPresetWidths, openingDefaultSizes, miscDefaultSizes, measurementDefaults,
    measurementVisibilityDefaults, stairStepSizeDefaults, railingSpacingDefaults, lineworkDefaults, collisionDefaults)
from .export_settings import NormalizeExportSettings

visibilityNames = ("World", "Walls", "Doors", "Windows", "Fireplaces", "Elevators", "Stairs", "Counters", "Railings", "Furnishings", "Labels", "Arrows", "Measurement guides", "Boundary lines", "Dashed lines", "Solid lines", "North arrows")
snapNames = ("grid", "vertices", "corners", "midpoints", "alignment")


def ReadProjectSettings(settings, materials, gridDefaults, resolveColor, validateReference, collisions = None):
    """Normalize preferences, delegating native colors and images at their original validation positions."""
    flags = ValidateFlags(settings, ("snapEnabled", "connectedVertices", "connectedObjects", "groupMode", "showGrid", "showMeasurements"))
    flags["collisionSettings"] = ValidateFlags(settings.get("collisionSettings", collisionDefaults), tuple(collisionDefaults)) if collisions is None else collisions
    flags["localTransforms"] = ValidateFlags({"localTransforms": False, **settings}, ("localTransforms",))["localTransforms"]
    flags["floors"] = ValidateFlags({"floors": True, **settings}, ("floors",))["floors"]
    roomStyle = settings.get("roomStyle", "Tinted" if flags["floors"] else "Canvas")
    if roomStyle not in ("Canvas", "Tinted"):
        raise ValueError("Invalid room style.")
    flags["roomStyle"] = roomStyle
    flags["floors"] = roomStyle == "Tinted"
    flags["solidRooms"] = ValidateFlags({"solidRooms": False, **settings}, ("solidRooms",))["solidRooms"]
    ignored = settings.get("ignoredPotentialIssues", [])
    if (not isinstance(ignored, list) or len(ignored) > 100000
            or any(not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
                   for value in ignored)):
        raise ValueError("Invalid ignored potential issue records.")
    flags["ignoredPotentialIssues"] = list(dict.fromkeys(ignored))
    snap = settings["snap"]
    if isinstance(snap, dict) and "corners" not in snap:
        # Older projects used one switch for both kinds of target.
        snap = {**snap, "corners": snap.get("vertices", True)}
    flags["snap"] = ValidateFlags(snap, snapNames)
    flags["visibility"] = ValidateFlags({"Elevators": True, "Fireplaces": True, "North arrows": True, "Railings": True, "Labels": True, "Counters": True, "Arrows": True, "Measurement guides": True, "Boundary lines": True, "Dashed lines": True, "Solid lines": True, **settings["visibility"]}, visibilityNames)
    if flags["snapEnabled"] and not any(flags["snap"].values()):
        raise ValueError("Snapping is enabled without any snap options.")
    flags["wallWidth"] = ValidateNumber(settings["wallWidth"], minimum = 1)
    if settings["wallMaterial"] not in materials:
        raise ValueError("The new wall settings are invalid.")
    flags["wallMaterial"] = settings["wallMaterial"]
    flags["wallShape"] = settings.get("wallShape", "line")
    if flags["wallShape"] not in ("line", "square", "circle"):
        raise ValueError("Unknown wall tool shape.")
    if settings["doorType"] not in ("Door", "SlidingDoor", "PocketDoor", "BarnDoor", "BifoldDoor", "OpenDoorway", "SwingingDoor", "DoubleDoor") or settings["windowType"] not in ("Window", "SilledWindow", "CasementWindow", "AwningWindow", "DoubleCasementWindow"):
        raise ValueError("The active door/window type is unknown.")
    flags["doorType"], flags["windowType"] = settings["doorType"], settings["windowType"]
    build = settings.get("buildSettings", {"wallWidths": list(wallPresetWidths), "openingSizes": openingDefaultSizes})
    if not isinstance(build, dict) or not isinstance(build.get("wallWidths"), list) or len(build["wallWidths"]) != 4:
        raise ValueError("The project contains invalid default wall sizes.")
    if not isinstance(build.get("openingSizes"), dict):
        raise ValueError("The project contains invalid default opening sizes.")
    miscSizes = build.get("miscSizes", miscDefaultSizes)
    if isinstance(miscSizes, dict):
        miscSizes = {"Elevator": miscDefaultSizes["Elevator"], "Fireplace": miscDefaultSizes["Fireplace"], "Column": miscDefaultSizes["Column"], **miscSizes}
    if not isinstance(miscSizes, dict) or set(miscSizes) != set(miscDefaultSizes):
        raise ValueError("The project contains invalid default miscellaneous sizes.")
    flags["buildSettings"] = {
        "wallWidths": [ValidateNumber(value, minimum = .1, maximum = 10000) for value in build["wallWidths"]],
        "openingSizes": {key: ValidateNumber(build["openingSizes"].get(key, openingDefaultSizes[key]) if key in ("BarnDoor", "BifoldDoor", "CasementWindow", "AwningWindow", "DoubleCasementWindow", "SwingingDoor", "DoubleDoor") else build["openingSizes"][key], minimum = .1, maximum = 10000)
                         for key in openingDefaultSizes},
        "miscSizes": {key: ValidateNumber(miscSizes[key], minimum = .1, maximum = 10000) for key in miscDefaultSizes}}
    imperialSizes = build.get("imperialSizes", {})
    sizeKeys = {str(index) for index in range(4)} | set(openingDefaultSizes) | set(miscDefaultSizes)
    if not isinstance(imperialSizes, dict) or not set(imperialSizes) <= sizeKeys:
        raise ValueError("The project contains invalid imperial default sizes.")
    if imperialSizes:
        flags["buildSettings"]["imperialSizes"] = {
            key: ValidateNumber(value, minimum = 1, maximum = 101600) for key, value in imperialSizes.items()}
    grid = settings.get("viewportSettings", gridDefaults)
    linework = settings.get("lineworkSettings", lineworkDefaults)
    if not isinstance(linework, dict) or set(linework) != set(lineworkDefaults):
        raise ValueError("The project contains invalid line weights.")
    flags["lineworkSettings"] = {key: ValidateNumber(linework[key], minimum = 1 if key == "baseWidth" else 0,
                                                   maximum = 4 if key == "baseWidth" else 2)
                                 for key in lineworkDefaults}
    if not isinstance(grid, dict):
        raise ValueError("The project contains invalid viewport settings.")
    flags["viewportSettings"] = {key: ValidateNumber(grid[key], minimum = 0, maximum = 2 if key == "overall" else 1)
                                 for key in gridDefaults}
    measurements = settings.get("measurementSettings", measurementDefaults)
    if not isinstance(measurements, dict):
        raise ValueError("The project contains invalid dimension settings.")
    measurements = {**measurementDefaults, **measurements}
    if any(type(measurements[key]) is not int or measurements[key] not in
           ((0, 2) if key in ("stairs", "counters") else (0, 1, 2)) for key in measurementDefaults):
        raise ValueError("The project contains invalid dimension settings.")
    flags["measurementSettings"] = {key: measurements[key] for key in measurementDefaults}
    mode = settings.get("wallMeasurementMode", "All")
    if mode not in ("All", "Exterior", "Exterior stacked"):
        raise ValueError("Invalid wall dimension mode.")
    flags["wallMeasurementMode"] = mode
    reference = settings.get("wallMeasurementReference", "Wall faces")
    if reference not in ("Centerline", "Wall faces"):
        raise ValueError("Invalid wall dimension reference.")
    flags["wallMeasurementReference"] = reference
    visibility = settings.get("measurementVisibility", measurementVisibilityDefaults)
    if isinstance(visibility, dict) and "railings" not in visibility:
        visibility = {**visibility, "railings": False}
    flags["measurementVisibility"] = ValidateFlags(visibility, tuple(measurementVisibilityDefaults))
    folder = settings.get("exportFolder")
    filename = settings.get("exportFileName")
    if filename is not None:
        if not isinstance(filename, str) or not filename.strip() or filename in (".", "..") or any(character in filename for character in '<>:"/\\|?*\0'):
            raise ValueError("Invalid export filename.")
        flags["exportFileName"] = filename
    if folder is not None:
        if not isinstance(folder, str) or not folder.strip() or "\0" in folder:
            raise ValueError("Invalid export folder.")
        flags["exportFolder"] = folder
    flags["exportSettings"] = NormalizeExportSettings(settings.get("exportSettings", {}), flags,
                                                      unitModes, measurementPrecisions, measurementDefaults)
    for name in ("canvasColor", "linesColor", "borderColor", "gridColor"):
        if flags["exportSettings"].get(name) is not None:
            flags["exportSettings"][name] = resolveColor(flags["exportSettings"][name])
    spacings = settings.get("railingSpacings", railingSpacingDefaults)
    if not isinstance(spacings, dict) or any(key not in spacings for key in railingSpacingDefaults):
        raise ValueError("Invalid railing sizing settings.")
    flags["railingSpacings"] = {key: ValidateNumber(spacings[key], minimum = .1, maximum = 10000) for key in railingSpacingDefaults}
    if not flags["railingSpacings"]["minimum"] <= flags["railingSpacings"]["target"] <= flags["railingSpacings"]["maximum"]:
        raise ValueError("Invalid railing spacing range.")
    steps = settings.get("stairStepSizes", stairStepSizeDefaults)
    if not isinstance(steps, dict):
        raise ValueError("The project contains invalid tread depth settings.")
    flags["stairStepSizes"] = {key: ValidateNumber(steps[key], minimum = .1, maximum = 10000) for key in stairStepSizeDefaults}
    if flags["stairStepSizes"]["minimum"] > flags["stairStepSizes"]["maximum"]:
        raise ValueError("Minimum stair tread depth exceeds maximum tread depth.")
    imperialAutoSizes = settings.get("imperialAutoSizes", {})
    if not isinstance(imperialAutoSizes, dict) or not set(imperialAutoSizes) <= {"stairs", "railings"}:
        raise ValueError("The project contains invalid imperial autosizing settings.")
    flags["imperialAutoSizes"] = {}
    for kind, values in imperialAutoSizes.items():
        keys = stairStepSizeDefaults if kind == "stairs" else railingSpacingDefaults
        if not isinstance(values, dict) or set(values) != set(keys):
            raise ValueError("The project contains invalid imperial autosizing settings.")
        limits = {key: ValidateNumber(values[key], minimum = 1, maximum = 101600) for key in keys}
        if limits["minimum"] > limits["maximum"] or kind == "railings" and not limits["minimum"] <= limits["target"] <= limits["maximum"]:
            raise ValueError("The project contains inconsistent imperial autosizing limits.")
        flags["imperialAutoSizes"][kind] = limits
    flags["unitsMode"] = settings.get("unitsMode", "Adaptive Metric")
    if settings.get("referenceImage") is not None:
        flags["referenceImage"] = validateReference(settings["referenceImage"])
    flags["measurementPrecision"] = settings.get("measurementPrecision", "Medium")
    if not isinstance(flags["measurementPrecision"], str) or flags["measurementPrecision"] not in measurementPrecisions:
        raise ValueError("The project contains an invalid dimension precision.")
    if flags["unitsMode"] not in unitModes:
        raise ValueError("The project contains an unknown display unit.")
    flags["autoSizingUnitsMode"] = settings.get("autoSizingUnitsMode", flags["unitsMode"])
    if flags["autoSizingUnitsMode"] not in unitModes:
        raise ValueError("The project contains an unknown autosizing unit.")
    return flags


def ReadEditorUi(ui, recovery = False, tabCount = None, selectionLimit = None):
    if not isinstance(ui, dict):
        raise ValueError("Invalid panel state.")
    # Window placement belongs only to app recovery. Ignore legacy project fields.
    if recovery:
        if not isinstance(ui.get("geometry"), str) or len(ui["geometry"]) > 10000:
            raise ValueError("Invalid window state.")
        base64.b64decode(ui["geometry"], validate = True)
        if "maximized" in ui and type(ui["maximized"]) is not bool:
            raise ValueError("Invalid maximized state.")
        if "size" in ui and (not isinstance(ui["size"], list) or len(ui["size"]) != 2 or
                             any(type(size) is not int or not 200 <= size <= 100000 for size in ui["size"])):
            raise ValueError("Invalid window size.")
    for name in ("mainSplitter", "propertiesSplitter"):
        if (not isinstance(ui.get(name), list) or len(ui[name]) != 2 or
                any(type(size) is not int or not 0 <= size <= 100000 for size in ui[name])):
            raise ValueError("Invalid panel sizes.")
    if type(ui.get("propertiesCollapsed", False if recovery else None)) is not bool:
        raise ValueError("Invalid properties panel state.")
    height = ui.get("propertiesRestoreHeight")
    if height is not None and (type(height) is not int or not 1 <= height <= 100000):
        raise ValueError("Invalid properties restore height.")
    sections = ui.get("exportSections", {})
    if (not isinstance(sections, dict) or set(sections) - {"Canvas", "Border", "Grid", "Line Weight", "Measurements", "Title Block", "Vignette", "Composite", "Visibility"}
            or any(type(value) is not bool for value in sections.values())):
        raise ValueError("Invalid export section state.")
    if recovery:
        scroll = ui.get("scroll")
        if not isinstance(scroll, list) or any(type(value) is not int or not 0 <= value <= 100000 for value in scroll):
            raise ValueError("Invalid recovered scroll positions.")
        if type(ui.get("tab")) is not int or not 0 <= ui["tab"] < tabCount:
            raise ValueError("Invalid recovered tab.")
        if type(ui.get("treeScroll", 0)) is not int or not 0 <= ui.get("treeScroll", 0) <= 100000:
            raise ValueError("Invalid recovered tree scroll position.")
        expanded = ui.get("expanded")
        if not isinstance(expanded, dict) or any(type(value) is not bool for value in expanded.values()):
            raise ValueError("Invalid recovered visibility tree.")
        selection = ui.get("selection")
        if not isinstance(selection, list) or any(not isinstance(entry, list) or len(entry) != 2 or
                type(entry[0]) is not int or (entry[1] is not None and (type(entry[1]) is not int or entry[1] not in (0, 1, 2, 3)))
                for entry in selection):
            raise ValueError("Invalid recovered selection.")
        if selectionLimit is not None:
            for objectId, index in selection:
                limit = selectionLimit(objectId)
                if limit is None or index is None:
                    continue  # Missing IDs retain the loader's existing skip behavior.
                if index >= limit[0] and not (index == 3 and limit[1]):
                    raise ValueError("Invalid recovered selection for object type.")
        if ui.get("rotationObject") is not None and type(ui["rotationObject"]) is not int:
            raise ValueError("Invalid recovered furnishing handles.")

