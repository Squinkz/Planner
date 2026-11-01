"""Aggregate budgets for historical geometry, separate from live scene results."""
from collections import OrderedDict
import sys
import weakref
from PySide6 import QtCore, QtGui

missingEntry = object()


class GeometryCacheKey(tuple):
    """Reuse a compound key's hash across lookup, LRU and accounting tables."""
    def __new__(cls, value):
        if not isinstance(value, tuple) or isinstance(value, cls):
            return value
        # Single-wall keys are cheaper to hash directly than to wrap. Large
        # contour/blocker tuples benefit from reuse across the three tables.
        if (len(value) == 3 and isinstance(value[0], (int, float))
                and isinstance(value[2], tuple) and len(value[2]) <= 4):
            return value
        if len(value) <= 32 and not any(isinstance(part, tuple) and len(part) > 32 for part in value):
            return value
        key = super().__new__(cls, value)
        key.cachedHash = tuple.__hash__(key)
        return key

    def __hash__(self):
        return self.cachedHash


def GeometryCacheCost(key, value, sharedIds = ()):
    """Estimate Python storage and native elements, without following model graphs."""
    pending, seen = [key, value], set(sharedIds)
    byteCount, pointCount = 512, 0
    if isinstance(key, GeometryCacheKey):
        byteCount += sys.getsizeof(key.__dict__) + sys.getsizeof(key.cachedHash)
    getSize = sys.getsizeof
    floatSize = getSize(0.0)
    scalarTypes = (int, bool, str, bytes, complex, type(None))
    while pending:
        item = pending.pop()
        identity = id(item)
        if identity in seen:
            continue
        seen.add(identity)
        itemType = type(item)
        # Coordinate keys are mostly exact built-in floats and tuples. Keep
        # identity deduplication, but avoid probing every scalar as a Qt object.
        # Subclasses still take the original dynamic-size/type path below.
        if itemType is float:
            byteCount += floatSize
            continue
        byteCount += getSize(item)
        if itemType in scalarTypes:
            continue
        if itemType is tuple or itemType is list:
            pending.extend(item)
        elif itemType is dict:
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, QtGui.QPainterPath):
            points = item.elementCount()
            pointCount += points
            byteCount += 256 + points * 32
        elif isinstance(item, QtGui.QPolygonF):
            points = len(item)
            pointCount += points
            byteCount += 64 + points * 16
        elif isinstance(item, QtCore.QPointF):
            pointCount += 1
            byteCount += 16
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, (tuple, list, set, frozenset)):
            pending.extend(item)
    return byteCount, pointCount


class NativeGeometryBudget:
    """One history budget shared by a viewport and its geometry workspaces."""
    def __init__(self, byteLimit = 16 * 1024 * 1024, pointLimit = 262144):
        self.byteLimit, self.pointLimit = byteLimit, pointLimit
        self.byteCount = self.pointCount = self.counter = 0
        self.entries = OrderedDict()
        self.shared = {}  # Identity -> [object, estimated bytes, points, entry references].

    def Remove(self, token):
        entry = self.entries.pop(token, None)
        if entry is not None:
            self.byteCount -= entry[2]
            self.pointCount -= entry[3]
            for identity in entry[4]:
                record = self.shared[identity]
                record[3] -= 1
                if record[3] == 0:
                    self.byteCount -= record[1]
                    self.pointCount -= record[2]
                    del self.shared[identity]

    def Trim(self):
        while self.entries and (self.byteCount > self.byteLimit or self.pointCount > self.pointLimit):
            token = next(iter(self.entries))
            reference, key, size, points, sharedIds = self.entries[token]
            cache = reference()
            if cache is None:
                self.Remove(token)
            else:
                cache.pop(key)

    def Clear(self):
        seen = set()
        for reference, key, size, points, sharedIds in list(self.entries.values()):
            cache = reference()
            if cache is not None and id(cache) not in seen:
                seen.add(id(cache))
                cache.clear()


class NativeGeometryCache(OrderedDict):
    """Account immutable geometry results at insertion, preserving ordinary values."""
    def __init__(self, budget):
        super().__init__()
        self.budget = budget
        self.costs = {}
        budgetReference = weakref.ref(budget)

        def Forget(reference):
            owner = budgetReference()
            if owner is not None:
                for token, entry in list(owner.entries.items()):
                    if entry[0] is reference:
                        owner.Remove(token)
        self.reference = weakref.ref(self, Forget)

    def get(self, key, default = None):
        key = GeometryCacheKey(key)
        value = super().get(key, missingEntry)
        if value is missingEntry:
            return default
        self.move_to_end(key)
        self.budget.entries.move_to_end(self.costs[key][0])
        return value

    def __setitem__(self, key, value):
        self.Store(key, value)

    def Store(self, key, value, shared = ()):
        key = GeometryCacheKey(key)
        if key in self:
            if super().__getitem__(key) is value:
                self.move_to_end(key)
                self.budget.entries.move_to_end(self.costs[key][0])
                return
            self.pop(key)
        records = {}
        for item in shared:
            identity = id(item)
            record = self.budget.shared.get(identity)
            if record is None:
                size, points = GeometryCacheCost(item, None)
                record = [item, size, points, 0]
            records[identity] = record
        identities = tuple(records)
        size, points = GeometryCacheCost(key, value, identities)
        if (size + sum(record[1] for record in records.values()) > self.budget.byteLimit
                or points + sum(record[2] for record in records.values()) > self.budget.pointLimit):
            return
        super().__setitem__(key, value)
        self.budget.counter += 1
        token = self.budget.counter
        self.costs[key] = token, size, points, identities
        self.budget.entries[token] = self.reference, key, size, points, identities
        self.budget.byteCount += size
        self.budget.pointCount += points
        for identity, record in records.items():
            if record[3] == 0:
                self.budget.shared[identity] = record
                self.budget.byteCount += record[1]
                self.budget.pointCount += record[2]
            record[3] += 1
        self.budget.Trim()

    def pop(self, key, default = missingEntry):
        key = GeometryCacheKey(key)
        value = super().pop(key, missingEntry)
        if value is missingEntry:
            if default is not missingEntry:
                return default
            raise KeyError(key)
        token, size, points, sharedIds = self.costs.pop(key)
        self.budget.Remove(token)
        return value

    def popitem(self, last = True):
        key, value = super().popitem(last = last)
        token, size, points, sharedIds = self.costs.pop(key)
        self.budget.Remove(token)
        return key, value

    def __delitem__(self, key):
        self.pop(key)

    def clear(self):
        for token, size, points, sharedIds in self.costs.values():
            self.budget.Remove(token)
        self.costs.clear()
        super().clear()
