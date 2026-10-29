"""Pure planning of portable asset keys and dependencies; no models or I/O."""
import copy


def PlanFurnishingImports(embedded, existing, availableKeys, suffix = "imported"):
    availableKeys = frozenset(availableKeys)
    remapped = {}
    usedKeys = {key.casefold() for key in availableKeys} | {key.casefold() for key in embedded}
    # Resolve children first so parent comparisons use the final
    # destination keys. Repeated pastes reuse identical imports.
    pending = dict(embedded)
    while pending:
        previousCount = len(pending)
        for key, record in list(pending.items()):
            if any(child["definition"] in pending for child in record.get("components", [])):
                continue
            expected = copy.deepcopy(record)
            for component in expected.get("components", []):
                component["definition"] = remapped.get(component["definition"], component["definition"])
            if key in availableKeys and existing.get(key) != expected:
                base, number = key[:80] + "_" + suffix, 2
                target = base
                while target.casefold() in usedKeys:
                    if target in availableKeys:
                        if existing.get(target) == expected:
                            break
                    target = base + "_" + str(number)
                    number += 1
                usedKeys.add(target.casefold())
                remapped[key] = target
            del pending[key]
        if len(pending) == previousCount:
            raise ValueError("Furnishing dependencies contain a cycle.")
    portable = {}
    for key, record in embedded.items():
        record = copy.deepcopy(record)
        for component in record.get("components", []):
            component["definition"] = remapped.get(component["definition"], component["definition"])
        portable[remapped.get(key, key)] = record
    return portable, remapped
