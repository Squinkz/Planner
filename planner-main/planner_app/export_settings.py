"""Export option policy and sizing, independent of Qt and rendering."""
import copy
import math
import base64
from .record_validation import ValidateNumber, ValidateFlags


def NormalizeExportSettings(export, baseSettings, unitModes, measurementPrecisions, measurementDefaults):
    """Normalize transport options; adapters must validate/resolve color strings."""
    if not isinstance(export, dict):
        raise ValueError("Invalid export settings.")
    # Preserve the previous furnishing-only preference under its broader name.
    if "solidFurnishings" in export and "solidObjects" not in export:
        export = dict(export, solidObjects = export["solidFurnishings"])
    export = {key: value for key, value in export.items() if key != "solidFurnishings"}
    if "floors" in export:
        legacyFloors = ValidateFlags(export, ("floors",))["floors"]
        export = dict(export)
        export.setdefault("roomStyle", "Tinted" if legacyFloors else "Canvas")
        del export["floors"]
    allowedExport = {"gridOrigin", "solidObjects", "roomStyle", "solidRooms", "wallStyle", "canvasTheme", "canvasColor", "linesColor", "borderColor", "gridColor", "texture", "textureAngle", "textureScale", "textureStrength", "textureHighlights", "textureMidtones", "textureShadows", "vignetteEnabled", "vignetteStrength", "showGrid", "viewportSettings", "lineworkSettings", "measurementVisibility", "visibility", "bounds", "scale", "scaleUnits", "scaleMode", "architecturalScale", "dpi", "ruler", "border", "borderSize", "unitsMode"}
    allowedExport.update(("wallMeasurementMode", "wallMeasurementReference", "fileType", "measurementPrecision", "measurementSettings", "titleBlock"))
    if not isinstance(export, dict) or set(export) - allowedExport:
        raise ValueError("Invalid export settings.")
    normalized = {}
    for name, value in export.items():
        if name == "titleBlock":
            normalized[name] = NormalizeTitleBlock(value)
        elif name == "fileType":
            if value not in ("PNG", "SVG", "PNG_OPTIMIZED"):
                raise ValueError("Invalid export file type.")
            normalized[name] = value
        elif name == "scale":
            normalized[name] = ValidateNumber(value, minimum = .001, maximum = 1000000)
        elif name == "texture":
            if value is not None and (not isinstance(value, str) or value in ("", ".", "..") or "/" in value or "\\" in value):
                raise ValueError("Invalid composite texture name.")
            normalized[name] = value
        elif name == "textureScale":
            normalized[name] = None if value is None else ValidateNumber(value, minimum = 0, maximum = 4)
        elif name in ("textureStrength", "textureHighlights", "textureMidtones", "textureShadows"):
            normalized[name] = ValidateNumber(value, minimum = 0, maximum = 1)
        elif name == "textureAngle":
            normalized[name] = ValidateNumber(value, minimum = 0, maximum = 360)
        elif name == "vignetteStrength":
            normalized[name] = ValidateNumber(value, minimum = 0, maximum = 2)
        elif name == "scaleMode":
            if value not in ("Digital", "Architectural"):
                raise ValueError("Invalid export scale mode.")
            normalized[name] = value
        elif name == "architecturalScale":
            normalized[name] = ValidateNumber(value, minimum = 1, maximum = 100000)
        elif name == "dpi":
            if type(value) is not int or not 1 <= value <= 2400:
                raise ValueError("Invalid export DPI.")
            normalized[name] = value
        elif name == "gridOrigin":
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError("Invalid export grid origin.")
            normalized[name] = [ValidateNumber(entry) for entry in value]
        elif name == "bounds":
            if not isinstance(value, list) or len(value) != 4:
                raise ValueError("Invalid export bounds.")
            normalized[name] = [ValidateNumber(entry) for entry in value]
            if value[2] <= 0 or value[3] <= 0:
                raise ValueError("Export bounds must have positive dimensions.")
        elif name == "unitsMode":
            if value not in unitModes:
                raise ValueError("Invalid export display unit.")
            normalized[name] = value
        elif name == "measurementPrecision":
            if not isinstance(value, str) or value not in measurementPrecisions:
                raise ValueError("Invalid export dimension precision.")
            normalized[name] = value
        elif name == "measurementSettings":
            if not isinstance(value, dict) or set(value) - set(measurementDefaults):
                raise ValueError("Invalid export dimension splits.")
            if any(type(entry) is not int or entry not in ((0, 2) if key in ("stairs", "counters") else (0, 1, 2))
                   for key, entry in value.items()):
                raise ValueError("Invalid export dimension splits.")
            normalized[name] = dict(value)
        elif name in ("wallMeasurementMode", "wallMeasurementReference"):
            choices = ("All", "Exterior", "Exterior stacked") if name == "wallMeasurementMode" else ("Centerline", "Wall faces")
            if value not in choices:
                raise ValueError("Invalid export wall dimension setting.")
            normalized[name] = value
        elif name == "scaleUnits":
            if value not in ("px/m", "px/cm"):
                raise ValueError("Invalid export scale units.")
            normalized[name] = value
        elif name == "wallStyle":
            if value not in ("Material", "Solid", "Outline"):
                raise ValueError("Invalid export wall style.")
            normalized[name] = value
        elif name == "border":
            if value not in ("None", "Plain", "Frame", "Corner Marks", "Reference Zones", "Marked", "Ruler", "Ruler + Reference Zones"):
                raise ValueError("Invalid export border.")
            normalized[name] = value
        elif name == "borderSize":
            if type(value) is not int or not 1 <= value <= 128:
                raise ValueError("Invalid export border size.")
            normalized[name] = value
        elif name in ("canvasColor", "linesColor", "borderColor", "gridColor"):
            # An explicit Theme choice stays tied to the captured canvas theme.
            if value is not None and not isinstance(value, str):
                raise ValueError("Invalid export color.")
            normalized[name] = value
        elif name == "canvasTheme":
            if not isinstance(value, str):
                raise ValueError("Invalid export canvas theme.")
            normalized[name] = value
        elif name == "roomStyle":
            if value not in ("Canvas", "Tinted"):
                raise ValueError("Invalid export room style.")
            normalized[name] = value
        elif name in ("showGrid", "ruler", "vignetteEnabled", "solidObjects", "solidRooms"):
            normalized.update(ValidateFlags(export, (name,)))
        else:
            keys = set(baseSettings[name])
            if name == "measurementVisibility" and isinstance(value, dict):
                value = {key: enabled for key, enabled in value.items() if key != "elevators"}
                if not value:
                    continue
            if not isinstance(value, dict) or set(value) - keys:
                raise ValueError("Invalid export option group.")
            if name in ("visibility", "measurementVisibility"):
                normalized[name] = ValidateFlags(value, tuple(value))
            else:
                normalized[name] = {
                    key: ValidateNumber(entry, minimum = 1 if name == "lineworkSettings" and key == "baseWidth" else 0,
                                        maximum = (4 if key == "baseWidth" else 2) if name == "lineworkSettings" else (2 if key == "overall" else 1))
                    for key, entry in value.items()}
    return normalized


def BorderSize(style, requested = 28):
    # Nine-pixel major ticks need clearance; labels and unit corners need more.
    minimum = {"None": 0, "Plain": 1, "Frame": 4, "Corner Marks": 4, "Reference Zones": 28, "Marked": 12, "Ruler": 28, "Ruler + Reference Zones": 56}[style]
    return max(minimum, requested) if style != "None" else 0


def ResolveExportView(baseView, overrides):
    view = copy.deepcopy(baseView)
    view["autoSizingUnitsMode"] = view["unitsMode"]
    for name, value in overrides.items():
        if name == "titleBlock":
            view[name] = copy.deepcopy(value)
        elif isinstance(value, dict):
            if name == "measurementVisibility":
                view[name] = {key: enabled and view["showMeasurements"] for key, enabled in view[name].items()}
            view[name].update(value)
        else:
            view[name] = value
    if "measurementVisibility" in overrides:
        view["showMeasurements"] = any(view["measurementVisibility"].values())
    if "visibility" in overrides:
        view["visibility"]["World"] = any(value for key, value in view["visibility"].items() if key != "World")
    return view


def ExportScalePerMeter(overrides, fileType):
    if overrides.get("scaleMode", "Digital") == "Architectural":
        dpi = overrides.get("dpi", 300) if fileType != "SVG" else 96
        return dpi * 1000 / (25.4 * overrides.get("architecturalScale", 100))
    return overrides.get("scale", 100)


def ExportPixelSize(bounds, scale, borderSize = 0):
    pixelsPerMillimeter = scale / 1000.0
    # Stabilize linked dimensions just above an integer without truncating
    # genuine fractional pixels. Rendering checks allocation limits separately.
    width = max(1, math.ceil(round(bounds[2] * pixelsPerMillimeter, 8)))
    height = max(1, math.ceil(round(bounds[3] * pixelsPerMillimeter, 8)))
    return width + 2 * borderSize, height + 2 * borderSize


def TitleBlockLogoMode(options):
    if "logoMode" in options:
        return options["logoMode"]
    if options.get("logoEnabled") is False:
        return "None"
    return "Custom" if options.get("logo") else "Planner"


def NormalizeTitleBlock(options):
    textFields = ("logo", "logoName", "projectName", "drawingTitle", "address", "date", "preparedBy", "comments", "sheetNumber", "revision")
    if not isinstance(options, dict) or set(options) - {"enabled", "logoEnabled", "logoMode", "position", *textFields}:
        raise ValueError("Invalid title block settings.")
    result = dict(options)
    if TitleBlockLogoMode(result) not in ("None", "Planner", "Custom"):
        raise ValueError("Invalid title block logo mode.")
    for name in ("enabled", "logoEnabled"):
        if name in result:
            ValidateFlags(result, (name,))
    if result.get("position", "Right") not in ("Right", "Bottom"):
        raise ValueError("Invalid title block position.")
    for name in textFields:
        if name in result and (not isinstance(result[name], str) or len(result[name]) > (8_000_000 if name == "logo" else 10000)):
            raise ValueError("Invalid title block text.")
    if result.get("logo"):
        try:
            base64.b64decode(result["logo"], validate = True)
        except ValueError as error:
            raise ValueError("Invalid title block logo.") from error
    return result


