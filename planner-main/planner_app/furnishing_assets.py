"""Shared unresolved furnishing and fallback-artwork status, including children."""
import re


def FurnishingAssetProblems(key, definitions, definition = None, allowNull = True):
    """Map faulty original asset keys to missing-definition or artwork problems.

    The actual Null catalog entry is an available placeholder, not a missing
    definition. Clipboard policy can still prohibit copying that placeholder.
    """
    problems = {}
    pending = [(key, definition if definition is not None else definitions.get(key))]
    visited = set()
    while pending:
        key, definition = pending.pop()
        if key in visited:
            continue
        visited.add(key)
        if key == "null" and not allowNull:
            problems[key] = "artwork"
        if key not in definitions or definition is None or definition.get("key") == "null" and key != "null":
            problems[key] = "missing"
        if definition is None:
            continue
        components = definition.get("components", [])
        graphic = (definition.get("graphicData") or b"").replace(b"'", b'"')
        nullRoot = re.search(rb'<(?:[\w.-]+:)?svg\b[^>]*\bdata-theme-outline\s*=\s*"missing"', graphic)
        if key != "null" and (definition.get("assetError") or nullRoot or not components and b'data-theme-outline="missing"' in graphic):
            problems.setdefault(key, "artwork")
        for component in components:
            child = component["definition"]
            pending.append((component.get("definitionKey", child["key"]), child))
    return problems
