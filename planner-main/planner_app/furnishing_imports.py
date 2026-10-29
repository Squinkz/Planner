"""Adapt furnishing models and SVG validation to the pure import planner."""
from .project_codec import EncodeFurnishingDefinitions, DecodeFurnishingDefinitions
from .furnishing_import_plan import PlanFurnishingImports


def ResolveFurnishingImports(embedded, definitions, suffix = "imported"):
    # Serialize only keys the planner may compare. File reads and SVG safety
    # checks belong here, rather than in dependency/key allocation decisions.
    bases = [key[:80] + "_" + suffix for key in embedded if key in definitions]
    existing = {}
    for key, definition in definitions.items():
        if key not in embedded and not any(key == base or key.startswith(base + "_") for base in bases):
            continue
        try:
            existing[key] = EncodeFurnishingDefinitions([definition], includeBuiltIns = True).get(key)
        except (OSError, ValueError, TypeError, KeyError):
            existing[key] = None
    portable, remapped = PlanFurnishingImports(embedded, existing, definitions.keys(), suffix = suffix)
    decoded = DecodeFurnishingDefinitions(portable, definitions)
    imported = {key: definition for key, definition in decoded.items() if key not in definitions}
    for definition in imported.values():
        for component in definition.get("components", []):
            key = component["definitionKey"]
            if key in definitions:
                component["definition"] = definitions[key]
    definitions = {**definitions, **imported}
    return definitions, imported, remapped
