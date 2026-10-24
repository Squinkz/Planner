"""External semantic palettes. Eight-digit paints use Qt's #AARRGGBB order."""
import json
import re
import warnings
from planner_app.paths import appDirectory
from .fonts import fontFamily

themeRoles = (
    "windowBackground", "text", "controlBackground", "fieldBackground", "hoverBackground",
    "pressedBackground", "activeBackground", "activeHoverBackground", "disabledBackground",
    "disabled", "border", "menuBorder", "mutedText", "activeText", "sliderHandle",
    "scrollbarHandle", "treeDisabledText", "treeEmptyText", "canvas", "objectOutline",
    "wallOutline", "invalidOutline", "selectionOutline", "groupSelectionOutline",
    "selectionFill", "groupSelectionFill", "wallFill", "materialPattern", "warningFill",
    "warningOutline", "stairSelectionFill", "stairGroupSelectionFill", "measurementLine",
    "rulerBackground", "rulerMajorTick", "rulerMinorTick", "rulerText", "performanceText",
    "grid", "selectionBoxFill", "overlayFill", "exportOutsideShade", "errorBorder", "errorFill", "errorText",
    "icon", "iconDisabled", "shadow", "missing", "warning", "error", "info",
    "warningTitle", "errorTitle", "infoTitle",
)
themeDefinitions = {}
themeColors = {}
canvasRoles = (
    "canvas", "grid", "objectOutline", "wallOutline", "wallFill", "materialPattern",
    "selectionOutline", "selectionFill", "groupSelectionOutline", "groupSelectionFill",
    "stairSelectionFill", "stairGroupSelectionFill", "selectionBoxFill", "measurementLine",
    "rulerBackground", "rulerMajorTick", "rulerMinorTick", "rulerText", "overlayFill", "exportOutsideShade",
    "performanceText", "invalidOutline", "warningFill", "warningOutline", "errorBorder",
    "errorFill", "errorText", "missing",
)
uiRoles = tuple(role for role in themeRoles if role not in canvasRoles)
activeUITheme = "Heather UI"
activeCanvasTheme = "Magnetite Canvas"
labelFont = fontFamily


def LoadThemes(directory = None):
    definitions = {}
    sources = {}
    themeDirectory = directory or appDirectory / "themes"
    for path in sorted([*themeDirectory.glob("*.json"), *themeDirectory.glob("*.jsonc")]):
        try:
            # Strip line comments while preserving quoted strings, including
            # escaped quotes and literal // inside theme names.
            source = path.read_text(encoding = "utf-8-sig")
            source = re.sub(r'"(?:\\.|[^"\\])*"|//[^\r\n]*',
                            lambda match: "" if match.group().startswith("//") else match.group(), source)
            data = json.loads(source)
            name, colors = data["name"], data.get("colors", {})
            if not isinstance(name, str) or not name.strip() or name in sources:
                raise ValueError("Theme names must be nonempty and unique")
            if not isinstance(colors, dict) or set(colors) - set(themeRoles):
                raise ValueError("Colors must contain only known semantic color roles")
            if any(not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?", value) for value in colors.values()):
                raise ValueError("Colors must be #RRGGBB or #AARRGGBB")
            labelFontName = data.get("labelFont")
            if "labelFont" in data and (not isinstance(labelFontName, str) or not labelFontName.strip()):
                raise ValueError("Label font must be a nonempty font family name")
            parents = data.get("extends", [])
            if isinstance(parents, str):
                parents = [parents]
            if not isinstance(parents, list) or any(not isinstance(parent, str) or not parent.strip() for parent in parents):
                raise ValueError("Extends must be a theme name or a list of theme names")
            if type(data.get("abstract", False)) is not bool:
                raise ValueError("Abstract must be true or false")
            themeType = data.get("type")
            if themeType not in ("ui", "canvas"):
                raise ValueError('Theme type must be "ui" or "canvas"')
            allowedRoles = uiRoles if themeType == "ui" else canvasRoles
            if set(colors) - set(allowedRoles):
                raise ValueError(f"{themeType} theme contains colors belonging to the other theme type")
            if themeType == "ui" and labelFontName is not None:
                raise ValueError("Label font belongs in a canvas theme")
            sources[name] = {"path": path, "colors": colors, "parents": parents,
                             "type": themeType,
                             "abstract": data.get("abstract", False),
                             "labelFont": labelFontName.strip() if labelFontName is not None else None}
        except (OSError, ValueError, KeyError, TypeError) as error:
            warnings.warn(f"Skipping theme {path.name}: {error}")

    resolved = {}

    def ResolveTheme(name, chain):
        if name in chain:
            raise ValueError("Circular theme inheritance: " + " -> ".join((*chain, name)))
        if name not in sources:
            raise ValueError(f"Missing or invalid parent theme: {name}")
        if name in resolved:
            return resolved[name]
        source = sources[name]
        result = {"colors": {}}
        for parent in source["parents"]:
            inherited = ResolveTheme(parent, (*chain, name))
            if sources[parent]["type"] != source["type"]:
                raise ValueError(f"Theme {name} cannot inherit from a different theme type: {parent}")
            result["colors"].update(inherited["colors"])
            if "labelFont" in inherited:
                result["labelFont"] = inherited["labelFont"]
        result["colors"].update(source["colors"])
        if source["labelFont"] is not None:
            result["labelFont"] = source["labelFont"]
        if source["type"] == "canvas" and not source["abstract"]:
            # Older custom canvas themes retain the original export dimming.
            result["colors"].setdefault("exportOutsideShade", "#41000000")
        requiredRoles = uiRoles if source["type"] == "ui" else canvasRoles
        missing = set(requiredRoles) - set(result["colors"])
        if missing and not source["abstract"]:
            raise ValueError(f"Resolved theme {name} is missing color roles: " + ", ".join(sorted(missing)))
        resolved[name] = result
        return result

    for name, source in sources.items():
        try:
            result = ResolveTheme(name, ())
            if source["abstract"]:
                continue
            definitions[name] = {"type": source["type"], "colors": dict(result["colors"])}
            if source["type"] == "canvas":
                definitions[name]["labelFont"] = result.get("labelFont", fontFamily)
        except (ValueError, RecursionError) as error:
            warnings.warn(f"Skipping theme {source['path'].name}: {error}")
    if not definitions:
        raise ValueError("No valid selectable theme files found in the themes folder")
    return definitions


def SetThemes(uiTheme = None, canvasTheme = None):
    global activeUITheme, activeCanvasTheme, labelFont
    selected = []
    for themeType, requested, current, default in (("ui", uiTheme, activeUITheme, "Heather UI"),
                                                 ("canvas", canvasTheme, activeCanvasTheme, "Magnetite Canvas")):
        available = [name for name, definition in themeDefinitions.items() if definition["type"] == themeType]
        if not available:
            raise ValueError(f"No valid selectable {themeType} themes found")
        name = current if requested is None else requested
        selected.append(name if name in available else default if default in available else available[0])
    activeUITheme, activeCanvasTheme = selected
    themeColors.clear()
    themeColors.update(themeDefinitions[activeUITheme]["colors"])
    themeColors.update(themeDefinitions[activeCanvasTheme]["colors"])
    labelFont = themeDefinitions[activeCanvasTheme]["labelFont"]



themeDefinitions.update(LoadThemes())
SetThemes()

# These identify neutral SVG input paints and older furnishing artwork; they
# are format conventions, not colors to render directly in the application.
svgBackgroundPaints = {"white", "#fff", "#ffffff", "rgb(255,255,255)", "#0e0e0e", "rgb(14,14,14)"}
svgOutlinePaints = {"black", "#000", "#000000", "rgb(0,0,0)", "#d1d8dd"}
