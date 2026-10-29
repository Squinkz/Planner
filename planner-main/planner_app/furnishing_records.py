"""Portable embedded furnishing records and component graph resolution."""
from pathlib import Path
from xml.etree import ElementTree
from .record_validation import ValidateNumber, ValidateCoordinates, ValidateFlags
from .catalog_metadata import FurnishingCategories


def WriteEmbeddedFurnishings(definitions, validateSvg, includeBuiltIns = False):
    embedded = {}
    pending = [(definition["key"], definition) for definition in definitions]
    while pending:
        key, definition = pending.pop()
        if key in embedded:
            continue
        graphic = definition.get("graphicData") or Path(definition["imagePath"]).read_bytes()
        validateSvg(graphic)
        categories = definition.get("categories", [definition["category"]])
        embedded[key] = {"name": definition["name"], "category": categories if len(categories) > 1 else categories[0],
                         "keywords": list(definition.get("keywords", [])),
                         "width": definition["width"], "length": definition["length"],
                         "svg": bytes(graphic).decode("utf-8-sig")}
        if definition.get("components"):
            embedded[key]["compoundCenter"] = list(definition["compoundCenter"])
            embedded[key]["components"] = []
            for component in definition["components"]:
                child = component["definition"]
                embedded[key]["components"].append({"definition": component.get("definitionKey", child["key"]),
                    **{field: component[field] for field in ("x", "y", "angle", "width", "length", "zIndex")},
                    **{field: component.get(field, False) for field in ("flipHorizontal", "flipVertical")},
                    **({"fixedSize": True} if component.get("fixedSize", False) else {})})
                if includeBuiltIns or child.get("isUser", False):
                    pending.append((child["key"], child))
    return embedded



def ReadEmbeddedFurnishings(embedded, definitions, validateSvg):
    if not isinstance(embedded, dict) or len(embedded) > 100000:
        raise ValueError("Invalid embedded furnishing definitions.")
    projectDefinitions = {}
    for key, record in embedded.items():
        if not isinstance(key, str) or not key or not isinstance(record, dict):
            raise ValueError("Invalid embedded furnishing key.")
        if (any(not isinstance(record.get(field), str) or not record[field] for field in ("name", "svg"))
                or not isinstance(record.get("category"), (str, list)) or not record["category"]):
            raise ValueError("Invalid embedded furnishing metadata.")
        categories = FurnishingCategories(record["category"])
        keywords = record.get("keywords", [])
        if not isinstance(keywords, list) or any(not isinstance(word, str) for word in keywords):
            raise ValueError("Invalid embedded furnishing keywords.")
        try:
            root = validateSvg(record["svg"])
        except (ElementTree.ParseError, ValueError) as error:
            raise ValueError("Invalid embedded furnishing SVG.") from error
        if root.tag not in ("svg", "{http://www.w3.org/2000/svg}svg"):
            raise ValueError("An embedded furnishing graphic must be SVG.")
        definition = {"key": key, "name": record["name"], "category": categories[0], "categories": categories, "keywords": list(keywords),
                      "width": ValidateNumber(record.get("width"), minimum = 1e-8, maximum = 1e12),
                      "length": ValidateNumber(record.get("length"), minimum = 1e-8, maximum = 1e12),
                      "graphicData": record["svg"].encode("utf-8"), "imagePath": None, "iconPath": None,
                      "image": None, "icon": None, "inherits": None, "sourcePath": None, "isUser": True,
                      "isEmbedded": True}
        definition["searchText"] = " ".join([definition["name"]] + categories + keywords).casefold()
        projectDefinitions[key] = definition
    # Embedded artwork is authoritative for this project, including keys that
    # have since become built-in. Keep the installation's catalogue unchanged.
    definitions = {**definitions, **projectDefinitions}

    def ResolveComponents(key, ancestors):
        if key in ancestors or len(ancestors) >= 64:
            raise ValueError("Embedded furnishing components contain circular or excessively nested references.")
        definition = projectDefinitions[key]
        if "components" in definition or "components" not in embedded[key]:
            return
        components = embedded[key]["components"]
        if not isinstance(components, list) or not components or len(components) > 100000:
            raise ValueError("Invalid embedded furnishing components.")
        center = ValidateCoordinates(embedded[key].get("compoundCenter"))
        resolved = []
        for component in components:
            if not isinstance(component, dict) or not isinstance(component.get("definition"), str):
                raise ValueError("Invalid embedded furnishing component reference.")
            childKey = component["definition"]
            if childKey in projectDefinitions:
                ResolveComponents(childKey, ancestors + [key])
            resolved.append({"definition": definitions.get(childKey, definitions["null"]), "definitionKey": childKey,
                **{field: ValidateNumber(component.get(field), minimum = 1e-8 if field in ("width", "length") else -1e12)
                   for field in ("x", "y", "angle", "width", "length", "zIndex")},
                **ValidateFlags({"flipHorizontal": False, "flipVertical": False, "fixedSize": False, **component},
                                ("flipHorizontal", "flipVertical", "fixedSize"))})
        definition["compoundCenter"] = center
        definition["components"] = resolved

    for key in projectDefinitions:
        ResolveComponents(key, [])
    from .furnishing_limits import FurnishingExpansionSizes
    FurnishingExpansionSizes(projectDefinitions.values())
    return projectDefinitions

