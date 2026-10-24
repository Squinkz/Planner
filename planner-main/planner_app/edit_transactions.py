"""Sparse reversible record edits; opaque values and explicit model validation.

No GUI/model imports. Identity is live object identity, not structural equality or
serialized project IDs. Value comparison belongs to supplied record values (e.g.
the desktop adapter retains QPointF equality). This engine never mutates models.
"""
from abc import ABC, abstractmethod

stateCategories = (0, 3, 5, 8)


class SparseSceneEdit(ABC):
    __slots__ = ("changes", "groups", "hidden", "orders", "selection")

    def __init__(self, changes, groups, hidden, orders, selection = ((None, None, ()), (None, None, ()))):
        self.changes = tuple(changes)
        self.groups, self.hidden, self.orders, self.selection = groups, hidden, orders, selection

    @abstractmethod
    def ValidateState(self, state):
        """Validate model-specific memberships/attachments after record replay."""
        raise NotImplementedError

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
            self.ValidateState(result)
        return tuple(result)
