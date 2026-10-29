"""Clipboard membership, bounds and duplication policies for opaque objects."""


def SelectionCopyObjects(selectedIds, walls, openings, furnishings, labels):
    parents = [obj for obj in walls if id(obj) in selectedIds]
    parentIndices = {id(obj): index for index, obj in enumerate(parents)}
    objects = parents + [obj for obj, parent in openings if id(obj) in selectedIds or id(parent) in parentIndices]
    objects.extend(obj for obj in furnishings if id(obj) in selectedIds)
    objects.extend(obj for obj in labels if id(obj) in selectedIds)
    return objects, parentIndices


def BuildSelectionTransport(entries, indices, groups):
    """Consume (record, numeric corner iterable) once, retaining no corner list.

    Records are borrowed from the model encoder. Groups contain identity keys;
    record and group order, including duplicate members, remain unchanged.
    """
    records, hasPoints = [], False
    for record, corners in entries:
        records.append(record)
        for x, y in corners:
            if not hasPoints:
                minX = maxX = x
                minY = maxY = y
                hasPoints = True
            else:
                if x < minX:
                    minX = x
                if x > maxX:
                    maxX = x
                if y < minY:
                    minY = y
                if y > maxY:
                    maxY = y
    if not hasPoints:
        raise ValueError("A selection needs at least one geometry point")
    copiedGroups = [[indices[key] for key in group if key in indices] for group in groups]
    return {"version": 1, "center": [(minX + maxX) / 2, (minY + maxY) / 2], "objects": records,
            "groups": [group for group in copiedGroups if len(group) >= 2]}


def OpeningCopyTargets(openings, copies, selectedIds):
    """A copied host wins; an explicitly selected child may retain its host."""
    for opening, parent in openings:
        if id(parent) in copies or id(opening) in selectedIds:
            yield opening, copies.get(id(parent), parent)


def RemapCopiedGroups(groups, copies):
    for group in groups:
        members = tuple(copies[id(obj)] for obj in group if id(obj) in copies)
        if len(members) >= 2:
            yield members
