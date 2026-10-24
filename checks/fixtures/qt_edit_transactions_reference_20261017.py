"""Sparse reversible edits; full captures are only temporary interaction state."""
import sys
from itertools import count
from PySide6 import QtCore

historyLimit = 200
historyByteBudget = 16 * 1024 * 1024
stateCategories = (0, 3, 5, 8)
editTokens = count(1)


def RetainedBytes(value, seen = None):
    """Conservative payload estimate, without traversing shared models/assets."""
    if seen is None:
        seen = set()
    if id(value) in seen:
        return 0
    seen.add(id(value))
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        return size + sum(RetainedBytes(key, seen) + RetainedBytes(item, seen) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return size + sum(RetainedBytes(item, seen) for item in value)
    if isinstance(value, QtCore.QPointF):
        return size + 32
    if hasattr(value, "objectId"):
        # Deleted objects stay alive for undo. Their graphic definitions are shared.
        return size + 1024
    return size


class SceneEdit:
    __slots__ = ("changes", "groups", "hidden", "orders", "selection", "byteSize", "token")

    def __init__(self, changes, groups, hidden, orders, selection = ((None, None, ()), (None, None, ()))):
        self.changes = tuple(changes)
        self.groups = groups
        self.hidden = hidden
        self.orders = orders
        self.selection = selection
        self.token = next(editTokens)
        self.byteSize = RetainedBytes((self.changes, groups, hidden, orders, selection)) + 128

    @classmethod
    def Between(cls, before, after):
        changes, orders = [], {}
        for category in stateCategories:
            old = {id(entry[0]): (index, entry) for index, entry in enumerate(before[category])}
            new = {id(entry[0]): (index, entry) for index, entry in enumerate(after[category])}
            for key in dict.fromkeys((*old, *new)):
                oldIndex, oldEntry = old.get(key, (None, None))
                newIndex, newEntry = new.get(key, (None, None))
                different = oldEntry is None or newEntry is None or oldEntry[1:] != newEntry[1:]
                if category == 3 and oldEntry is not None and newEntry is not None:
                    different = different or oldEntry[1] is not newEntry[1]
                if different:
                    changes.append((category, oldIndex, newIndex, oldEntry, newEntry))
            # Insertions/deletions shift indices without changing relative order.
            # Only an actual reordering needs an order vector.
            if [key for key in old if key in new] != [key for key in new if key in old]:
                orders[category] = (tuple(entry[0] for entry in before[category]),
                                    tuple(entry[0] for entry in after[category]))
        memberships = []
        for index in (6, 7):
            old = {tuple(sorted(id(obj) for obj in group)) if index == 6 else id(group): (position, group)
                   for position, group in enumerate(before[index])}
            new = {tuple(sorted(id(obj) for obj in group)) if index == 6 else id(group): (position, group)
                   for position, group in enumerate(after[index])}
            memberships.append((tuple(value for key, value in old.items() if key not in new),
                                tuple(value for key, value in new.items() if key not in old)))
        if not changes and not orders and not any(any(side) for side in memberships):
            return None
        return cls(changes, *memberships, orders,
                   ((before[1], before[2], before[4]), (after[1], after[2], after[4])))

    def Apply(self, state, forward, validate = False):
        """Build one transient state, preserving unchanged objects and list order."""
        result = list(state)
        sourceSide, targetSide = (0, 1) if forward else (1, 0)
        for category in stateCategories:
            changes = [change for change in self.changes if change[0] == category]
            entries = list(state[category])
            affected = set()
            insertions = []
            for _, oldIndex, newIndex, old, new in changes:
                source, target = (old, new) if forward else (new, old)
                sourceIndex, targetIndex = (oldIndex, newIndex) if forward else (newIndex, oldIndex)
                obj = (old or new)[0]
                affected.add(id(obj))
                if validate:
                    if source is None:
                        if any(entry[0] is obj for entry in entries):
                            raise ValueError("History adds an existing object.")
                    elif (sourceIndex >= len(entries) or entries[sourceIndex][0] is not obj
                          or entries[sourceIndex][1:] != source[1:]
                          or (category == 3 and entries[sourceIndex][1] is not source[1])):
                        raise ValueError("History does not match the current scene.")
                if target is not None:
                    insertions.append((targetIndex, target))
            entries = [entry for entry in entries if id(entry[0]) not in affected]
            for index, entry in sorted(insertions, key = lambda item: item[0]):
                if validate and index > len(entries):
                    raise ValueError("Invalid history object position.")
                entries.insert(index, entry)
            if category in self.orders:
                sourceOrder, targetOrder = self.orders[category][sourceSide], self.orders[category][targetSide]
                if validate and [id(entry[0]) for entry in state[category]] != [id(obj) for obj in sourceOrder]:
                    raise ValueError("History order does not match the scene.")
                byId = {id(entry[0]): entry for entry in entries}
                if len(targetOrder) != len(byId) or {id(obj) for obj in targetOrder} != set(byId):
                    raise ValueError("Invalid history object order.")
                entries = [byId[id(obj)] for obj in targetOrder]
            result[category] = tuple(entries)
        for index, changes in ((6, self.groups), (7, self.hidden)):
            removed, added = changes[sourceSide], changes[targetSide]
            entries = list(state[index])
            for position, value in removed:
                key = tuple(sorted(id(obj) for obj in value)) if index == 6 else id(value)
                matching = [offset for offset, entry in enumerate(entries)
                            if (tuple(sorted(id(obj) for obj in entry)) if index == 6 else id(entry)) == key]
                if not matching:
                    raise ValueError("History membership does not match the scene.")
                entries.pop(matching[0])
            for position, value in sorted(added, key = lambda item: item[0]):
                if validate and position > len(entries):
                    raise ValueError("Invalid history membership position.")
                entries.insert(position, value)
            result[index] = tuple(entries)
        result[1], result[2], result[4] = self.selection[targetSide]
        if validate:
            members = {id(entry[0]) for category in stateCategories for entry in result[category]}
            walls = {id(entry[0]) for entry in result[0] if type(entry[0]).__name__ == "Wall"}
            if any(id(entry[1]) not in walls for entry in result[3]):
                raise ValueError("History opening has no parent wall.")
            grouped = set()
            for group in result[6]:
                ids = {id(obj) for obj in group}
                if len(ids) < 2 or len(ids) != len(group) or ids - members or ids & grouped:
                    raise ValueError("Invalid history group.")
                grouped.update(ids)
            hiddenIds = {id(obj) for obj in result[7]}
            if hiddenIds - members or len(hiddenIds) != len(result[7]):
                raise ValueError("Invalid hidden history objects.")
        return tuple(result)
