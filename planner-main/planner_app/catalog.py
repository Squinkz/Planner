"""Furnishing definition loading, inheritance and asset resolution."""

import json
import math
import warnings
from pathlib import Path
from planner_app.paths import furnishingsDirectory as furnishingsFolder
from planner_app.graphics.furnishings import CompoundFurnishingSvg


def FurnishingCategories(value):
    """Accept a single category or a list, preserving order without duplicates."""
    if value is None:
        value = []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or any(not isinstance(category, str) for category in value):
        raise ValueError("Categories must be text or a list of text")
    categories, seen = [], set()
    for category in value:
        category = category.strip()
        if category and category.casefold() not in seen:
            categories.append(category)
            seen.add(category.casefold())
    return categories or ["Miscellaneous"]


def LoadFurnishings(folder = furnishingsFolder, definitionOverrides = None):
    folder = Path(folder)
    definitions = {}
    sources = {}
    builtInKeys = {path.stem.casefold() for path in (folder / "definitions").glob("*.json")}
    paths = sorted((folder / "definitions").glob("*.json")) + sorted((folder / "definitions_user").glob("*.json"))
    for path in paths:
        try:
            definition = json.loads(path.read_text(encoding = "utf-8"))
            if not isinstance(definition, dict):
                raise ValueError("A definition must be a JSON object")
            isUser = path.parent.name == "definitions_user"
            if isUser and path.stem.casefold() in builtInKeys:
                raise ValueError("User furnishings cannot replace built-in definitions")
            if not isUser:
                builtInKeys.add(path.stem.casefold())
            definitions[path.stem] = definition
            sources[path.stem] = path
        except (ValueError, OSError, UnicodeError) as error:
            warnings.warn(f"Cannot load furnishing {path.name}: {error}")
    for key, definition in (definitionOverrides or {}).items():
        if key.casefold() in builtInKeys:
            raise ValueError("User furnishings cannot replace built-in definitions")
        definitions[key] = definition
        sources[key] = folder / "definitions_user" / (key + ".json")
    defaults = definitions.get("null")
    fields = {"name", "image", "width", "length", "icon", "category", "inherits"}
    if defaults is None or not fields.issubset(defaults):
        warnings.warn("The Null furnishing definition must provide every default field.")
        return []
    resolved = {}

    def Resolve(key, ancestors):
        if key in resolved:
            return resolved[key]
        if key in ancestors:
            raise ValueError(f"Circular furnishing inheritance or compound reference: {' -> '.join(ancestors + [key])}")
        if len(ancestors) >= 64:
            raise ValueError(f"Furnishing references are nested too deeply: {key}")
        if key not in definitions:
            raise ValueError(f"Unknown parent furnishing: {key}")
        definition = definitions[key]
        parent = definition.get("inherits") if key != "null" else None
        values = dict(defaults)
        if parent:
            values.update(Resolve(parent, ancestors + [key]))
        values.update(definition)
        values.pop("graphicData", None)
        values.pop("components", None)
        values.pop("compoundCenter", None)
        children = values.get("children", [])
        if not isinstance(children, list):
            raise ValueError(f"Children must be a list for {key}")
        if children:
            components = []
            portable = {}
            if "embeddedFurnishings" in definition:
                from .project_codec import DecodeFurnishingDefinitions
                portable = DecodeFurnishingDefinitions(definition["embeddedFurnishings"],
                                                       {"null": Resolve("null", ancestors + [key])})
            for child in children:
                if not isinstance(child, dict) or not isinstance(child.get("furnishing"), str):
                    raise ValueError(f"A child of {key} needs a furnishing reference")
                reference = child["furnishing"]
                childDefinition = (portable[reference] if reference in portable else
                                   Resolve(reference if reference in definitions else "null", ancestors + [key]))
                if "scale" in child and ("width" in child or "length" in child):
                    raise ValueError(f"A child of {key} cannot combine scale and explicit dimensions")
                component = {"definition": childDefinition, "definitionKey": reference}
                for field in ("flipHorizontal", "flipVertical", "fixedSize"):
                    value = child.get(field, False)
                    if type(value) is not bool:
                        raise ValueError(f"Invalid child {field} for {key}")
                    component[field] = value
                for field, default in (("x", 0), ("y", 0), ("angle", 0), ("scale", 1),
                                       ("width", childDefinition["width"]), ("length", childDefinition["length"]),
                                       ("zIndex", 0)):
                    value = float(child.get(field, default))
                    if not math.isfinite(value) or (field in ("scale", "width", "length") and value <= 0):
                        raise ValueError(f"Invalid child {field} for {key}")
                    component[field] = value
                component["width"] *= component["scale"]
                component["length"] *= component["scale"]
                components.append(component)
            values["graphicData"], values["width"], values["length"], values["compoundCenter"] = CompoundFurnishingSvg(components)
            values["components"] = components
        else:
            for dimension in ("width", "length"):
                value = float(values[dimension])
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(f"Invalid {dimension} for {key}")
                values[dimension] = value
        values["categories"] = FurnishingCategories(definition.get("category", values.get("categories", values.get("category"))))
        values["category"] = values["categories"][0]
        values["name"] = str(values.get("name") or key.title())
        keywords = values.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [keywords]
        if not isinstance(keywords, list) or any(not isinstance(term, str) for term in keywords):
            raise ValueError(f"Keywords must be text or a list of text for {key}")
        values["keywords"] = list(keywords)
        values["searchText"] = " ".join([values["name"]] + values["categories"] + keywords).casefold()
        values["key"] = key
        values["sourcePath"] = sources[key]
        values["isUser"] = sources[key].parent.name == "definitions_user"
        for field in ("image", "icon"):
            name = values.get(field)
            asset = folder / "images" / f"{Path(str(name)).stem}.svg" if name else None
            values[field + "Path"] = asset if asset and asset.is_file() else None
        values.pop("assetError", None)
        if not children and values["imagePath"] is None and key != "null":
            values["assetError"] = "Missing furnishing image"
        values["imagePath"] = values["imagePath"] or folder / "images" / f"{Path(str(defaults['image'])).stem}.svg"
        values["iconPath"] = values["iconPath"] or values["imagePath"]
        resolved[key] = values
        return values

    for key in definitions:
        try:
            Resolve(key, [])
        except (ValueError, TypeError, OverflowError, OSError, SyntaxError) as error:
            warnings.warn(f"Cannot load furnishing {key}: {error}")
    return sorted(resolved.values(), key = lambda item: (item["category"].casefold(), item["name"].casefold()))
