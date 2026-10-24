"""Desktop history adapter; portable record algorithms live in edit_transactions.

Qt value semantics, retained-size estimates and model validation stay here.
See docs/EDITING_PORTS.md for capture/gesture/signal responsibilities intentionally
left in the desktop layer. Full captures remain temporary interaction state.
"""
import sys
from itertools import count
from PySide6 import QtCore
from .edit_transactions import SparseSceneEdit, stateCategories

historyLimit = 200
historyByteBudget = 16 * 1024 * 1024
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


class SceneEdit(SparseSceneEdit):
    """Desktop adapter: retained-size policy, edit tokens and model validation."""
    __slots__ = ("byteSize", "token")

    def __init__(self, changes, groups, hidden, orders, selection = ((None, None, ()), (None, None, ()))):
        super().__init__(changes, groups, hidden, orders, selection)
        self.token = next(editTokens)
        self.byteSize = RetainedBytes((self.changes, groups, hidden, orders, selection)) + 128

    def ValidateState(self, result):
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
