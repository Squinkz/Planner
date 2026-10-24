"""Bound expanded compound work without enumerating a shared definition graph."""
compoundExpansionLimit = 10000
sceneExpansionLimit = 100000


def FurnishingExpansionSizes(definitions):
    sizes = {}
    depths = {}

    def Count(definition, ancestors):
        identity = id(definition)
        if identity in ancestors or len(ancestors) >= 64:
            raise ValueError("Circular or excessively nested furnishing components.")
        if identity in sizes:
            return sizes[identity]
        size = depth = 1
        for component in definition.get("components", ()):
            child = component["definition"]
            size += Count(child, ancestors + (identity,))
            depth = max(depth, depths[id(child)] + 1)
            if size > compoundExpansionLimit:
                raise ValueError("A compound furnishing expands to more than 10,000 objects.")
            # Memoized children may have been visited from a shallower root.
            # Their complete depth still contributes to this root's budget.
            if depth > 64:
                raise ValueError("Circular or excessively nested furnishing components.")
        sizes[identity] = size
        depths[identity] = depth
        return size

    for definition in definitions:
        Count(definition, ())
    return sizes
