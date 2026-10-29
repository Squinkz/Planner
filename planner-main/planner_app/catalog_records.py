"""Furnishing inheritance, component policies and asset paths without Qt."""
import json
import math
import warnings
from pathlib import Path
from .catalog_metadata import FurnishingCategories


def ReadFurnishingCatalog(folder, compoundSvg, decodeEmbedded, definitionOverrides = None, builtInFolder = None):
    folder = Path(folder)
    builtInFolder = Path(builtInFolder) if builtInFolder is not None else folder
    definitions = {}
    sources = {}
    canonicalKeys = {}
    paths = sorted((builtInFolder / "definitions").glob("*.json")) + sorted((folder / "definitions_user").glob("*.json"))
    for path in paths:
        try:
            definition = json.loads(path.read_text(encoding = "utf-8"))
            if not isinstance(definition, dict):
                raise ValueError("A definition must be a JSON object")
            key = canonicalKeys.setdefault(path.stem.casefold(), path.stem)
            definitions[key] = definition
            sources[key] = path
        except (ValueError, OSError, UnicodeError) as error:
            warnings.warn(f"Cannot load furnishing {path.name}: {error}")
    for key, definition in (definitionOverrides or {}).items():
        key = canonicalKeys.setdefault(key.casefold(), key)
        definitions[key] = definition
        sources[key] = folder / "definitions_user" / (key + ".json")
    imagePaths = {}
    for directory in (builtInFolder / "images", folder / "images_user"):
        if directory.is_dir():
            imagePaths.update((path.stem.casefold(), path) for path in sorted(directory.iterdir())
                              if path.is_file() and path.suffix.casefold() == ".svg")
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
                portable = decodeEmbedded(definition["embeddedFurnishings"],
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
            values["graphicData"], values["width"], values["length"], values["compoundCenter"] = compoundSvg(components)
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
            values[field + "Path"] = imagePaths.get(Path(str(name)).stem.casefold()) if name else None
        values.pop("assetError", None)
        if not children and values["imagePath"] is None and key != "null":
            values["assetError"] = "Missing furnishing image"
        values["imagePath"] = values["imagePath"] or imagePaths.get(Path(str(defaults["image"])).stem.casefold(),
            builtInFolder / "images" / f"{Path(str(defaults['image'])).stem}.svg")
        values["iconPath"] = values["iconPath"] or values["imagePath"]
        # User artwork and inherited/component overrides also need to travel
        # with saved plans, even when their top-level definition is built in.
        values["isUser"] = (values["isUser"] or bool(parent and resolved[parent]["isUser"])
            or any(component["definition"].get("isUser", False) for component in values.get("components", []))
            or any(values[field].parent == folder / "images_user" for field in ("imagePath", "iconPath")))
        resolved[key] = values
        return values

    for key in definitions:
        try:
            Resolve(key, [])
        except (ValueError, TypeError, OverflowError, OSError, SyntaxError) as error:
            warnings.warn(f"Cannot load furnishing {key}: {error}")
    return sorted(resolved.values(), key = lambda item: (item["category"].casefold(), item["name"].casefold()))
