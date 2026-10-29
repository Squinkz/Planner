"""Identity-based group and hiding proposals; opaque objects require no Qt API."""


def ExpandSelectionGroups(entries, groups, sceneIds, enabled):
    if not enabled or not groups:
        return list({(id(obj), index): (obj, index) for obj, index in entries}.values())
    members = {id(obj): group for group in groups for obj in group}
    sceneIds = frozenset(sceneIds)
    expanded = {}
    for obj, index in entries:
        # Control vertices remain independently editable.
        if index is None:
            for member in members.get(id(obj), ()):
                if id(member) in sceneIds and member is not obj:
                    expanded[(id(member), None)] = (member, None)
        expanded[(id(obj), index)] = (obj, index)
    return list(expanded.values())


def FilterObjectGroups(groups, memberIds, keep = True):
    if not groups:
        return []
    memberIds = frozenset(memberIds)
    result = []
    for group in groups:
        members = tuple(obj for obj in group if (id(obj) in memberIds) == keep)
        if len(members) > 1:
            result.append(members)
    return result


def PlanGroupSelection(entries, groups):
    objects = list({id(obj): obj for obj, index in entries}.values())
    if len(objects) < 2:
        return None
    selectedIds = {id(obj) for obj in objects}
    if any({id(obj) for obj in group} == selectedIds for group in groups):
        return None
    return FilterObjectGroups(groups, selectedIds, keep = False) + [tuple(objects)], objects


def PlanUngroupSelection(entries, groups):
    selectedIds = {id(obj) for obj, index in entries}
    if not any(id(obj) in selectedIds for group in groups for obj in group):
        return None
    return FilterObjectGroups(groups, selectedIds, keep = False)


def PlanHideSelection(entries, hiddenObjects, openings):
    """Openings supply (object, parent); attached children follow hidden parents."""
    objects = {id(obj): obj for obj, index in entries}
    if not objects:
        return None
    objects.update((id(obj), obj) for obj, parent in openings if id(parent) in objects)
    objects = {**{id(obj): obj for obj in hiddenObjects}, **objects}
    return list(objects.values()), set(objects)


def PlanHideUnselected(entries, objects, hiddenIds):
    selectedIds = {id(obj) for obj, index in entries}
    if not selectedIds:
        return None
    hidden = [obj for obj in objects if id(obj) not in selectedIds]
    proposedIds = {id(obj) for obj in hidden}
    if proposedIds == hiddenIds:
        return None
    return hidden, proposedIds
