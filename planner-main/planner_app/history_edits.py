"""Desktop history adapter; portable record algorithms live in edit_transactions.

Qt value semantics, retained-size estimates and model identity resolution stay here.
See docs/EDITING_PORTS.md for capture/gesture/signal responsibilities intentionally
left in the desktop layer. Full captures remain temporary interaction state.
"""
import sys
from itertools import count
from PySide6 import QtCore
from .edit_transactions import SparseSceneEdit, stateCategories, ValidateSceneMemberships
from .history_records import ApplyReferenceChanges, historyLimit, historyByteBudget

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
        members = (id(entry[0]) for category in stateCategories for entry in result[category])
        walls = (id(entry[0]) for entry in result[0] if type(entry[0]).__name__ == "Wall")
        openingParents = (id(entry[1]) for entry in result[3])
        groups = (tuple(id(obj) for obj in group) for group in result[6])
        ValidateSceneMemberships(members, walls, openingParents, groups, (id(obj) for obj in result[7]))


class ReferenceImageEdit(SceneEdit):
    """Reference deltas share the scene journal without retaining whole images per move."""
    __slots__ = ("referenceChanges", "pivots")

    def __init__(self, changes, pivots = (None, None)):
        super().__init__((), ((), ()), ((), ()), {})
        self.referenceChanges = changes
        self.pivots = pivots
        self.byteSize = RetainedBytes((changes, pivots)) + 128

    def Apply(self, state, forward, validate = False):
        return state

    def ApplyReference(self, record, forward, validate = False):
        return ApplyReferenceChanges(record, self.referenceChanges, forward, validate = validate)
