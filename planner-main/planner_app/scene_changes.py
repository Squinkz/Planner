"""Owned scene values report edits, including mutable Qt coordinates/containers."""
import weakref
from PySide6 import QtCore


class SceneChanges:
    def __init__(self):
        self.geometry = self.appearance = self.topology = self.visibility = 0
        self.definitions = {}
        self.definitionOwners = {}

    def Bump(self, kind):
        setattr(self, kind, getattr(self, kind) + 1)

    def Watch(self, obj):
        if isinstance(obj, SceneObject):
            observers = obj.__dict__.setdefault("_renderObservers", weakref.WeakSet())
            observers.add(self)
            definition = getattr(obj, "definition", None)
            if definition is not None:
                identity, definitionIdentity = id(obj), id(definition)
                previous = self.definitionOwners.get(identity)
                if previous is not None and previous[1] != definitionIdentity:
                    oldMembers = self.definitions.get(previous[1])
                    if oldMembers is not None:
                        oldMembers.pop(identity, None)
                        if not oldMembers:
                            del self.definitions[previous[1]]
                members = self.definitions.setdefault(definitionIdentity, weakref.WeakValueDictionary())
                members[identity] = obj
                reference = weakref.ref(self)

                def RemoveOwner(ownerReference):
                    changes = reference()
                    if changes is not None:
                        record = changes.definitionOwners.get(identity)
                        if record is not None and record[0] is ownerReference:
                            del changes.definitionOwners[identity]
                self.definitionOwners[identity] = (weakref.ref(obj, RemoveOwner), definitionIdentity)
            parent = getattr(obj, "parentWall", None)
            if parent is not None:
                self.Watch(parent)

    def DefinitionKeys(self):
        # Catalog dictionaries deliberately retain their shared identity. Check
        # their keys once per distinct definition, never once per scene object.
        keys = []
        for identity, members in list(self.definitions.items()):
            member = next(iter(members.values()), None)
            if member is None:
                del self.definitions[identity]
            else:
                keys.append((identity, member.definition["key"]))
        return tuple(keys)


class ScenePoint(QtCore.QPointF):
    def __init__(self, point, owner):
        super().__init__(point)
        self.owner = weakref.ref(owner)

    def Changed(self):
        owner = self.owner()
        if owner is not None:
            owner.NotifyRender("geometry")

    def setX(self, value):
        if value != self.x():
            super().setX(value)
            self.Changed()

    def setY(self, value):
        if value != self.y():
            super().setY(value)
            self.Changed()

    def __iadd__(self, value):
        result = super().__iadd__(value)
        self.Changed()
        return result

    def __isub__(self, value):
        result = super().__isub__(value)
        self.Changed()
        return result

    def __imul__(self, value):
        result = super().__imul__(value)
        self.Changed()
        return result

    def __itruediv__(self, value):
        result = super().__itruediv__(value)
        self.Changed()
        return result

    def __deepcopy__(self, memo):
        return QtCore.QPointF(self)


geometryFields = frozenset(("firstVertex", "secondVertex", "middleVertex", "textOffset", "width", "firstMiter", "secondMiter", "parentWall", "manualDepth", "manualDepthOffset",
                           "centerFraction", "length", "autosize", "manualStepCount", "manualPostCount",
                           "stepSizeBounds", "spacingBounds", "sillDepth", "directionReversed", "flipHorizontal", "flipVertical"))
appearanceFields = frozenset(("material", "text", "intensity", "measurementFlipped", "measurementHidden", "behindCounters", "geometryIssues", "hingeAtSecond",
                             "swingsOutwards", "panelsFlipped", "solidTip", "tipSize", "definition", "objectId"))


class SceneObject:
    measurementHidden = False

    def __setattr__(self, name, value):
        old = self.__dict__.get(name)
        if name in ("firstVertex", "secondVertex", "middleVertex", "textOffset"):
            value = ScenePoint(value, self)
        elif name in ("stepSizeBounds", "spacingBounds"):
            value = tuple(value)
        object.__setattr__(self, name, value)
        if name not in geometryFields and name not in appearanceFields:
            return
        changed = old is not value if name in ("parentWall", "definition") else old != value
        if name == "definition" and changed:
            for observer in self.__dict__.get("_renderObservers", ()):
                observer.Watch(self)
        if name in geometryFields and changed:
            if name == "parentWall":
                for observer in self.__dict__.get("_renderObservers", ()):
                    observer.Watch(value)
            self.NotifyRender("geometry")
        elif name in appearanceFields and changed:
            self.NotifyRender("appearance")

    def NotifyRender(self, kind):
        for observer in self.__dict__.get("_renderObservers", ()):
            observer.Bump(kind)

    def __getstate__(self):
        return {name: value for name, value in self.__dict__.items() if name != "_renderObservers"}

    def __setstate__(self, state):
        for name, value in state.items():
            setattr(self, name, value)


class SceneList(list):
    def __init__(self, values, changes, nested = False):
        self.changes, self.nested = changes, nested
        super().__init__(self.Prepare(value) for value in values)

    def Prepare(self, value):
        if self.nested:
            if isinstance(value, tuple):
                for obj in value:
                    self.changes.Watch(obj)
                return value
            return SceneList(value, self.changes)
        self.changes.Watch(value)
        return value

    def __setitem__(self, index, value):
        super().__setitem__(index, [self.Prepare(item) for item in value] if isinstance(index, slice) else self.Prepare(value))
        self.changes.Bump("topology")

    def __delitem__(self, index):
        super().__delitem__(index)
        self.changes.Bump("topology")

    def append(self, value):
        super().append(self.Prepare(value))
        self.changes.Bump("topology")

    def extend(self, values):
        if values is self:
            values = list(values)
        try:
            super().extend(self.Prepare(value) for value in values)
        finally:
            self.changes.Bump("topology")

    def insert(self, index, value):
        super().insert(index, self.Prepare(value))
        self.changes.Bump("topology")

    def pop(self, index = -1):
        value = super().pop(index)
        self.changes.Bump("topology")
        return value

    def remove(self, value):
        super().remove(value)
        self.changes.Bump("topology")

    def clear(self):
        super().clear()
        self.changes.Bump("topology")

    def reverse(self):
        super().reverse()
        self.changes.Bump("topology")

    def sort(self, *args, **kwargs):
        try:
            super().sort(*args, **kwargs)
        finally:
            self.changes.Bump("topology")

    def __iadd__(self, values):
        self.extend(values)
        return self

    def __imul__(self, count):
        super().__imul__(count)
        self.changes.Bump("topology")
        return self

    def __deepcopy__(self, memo):
        from copy import deepcopy
        return [deepcopy(value, memo) for value in self]


class SceneDict(dict):
    def __init__(self, values, changed):
        super().__init__(values)
        self.changed = changed

    def __setitem__(self, name, value):
        super().__setitem__(name, value)
        self.changed()

    def __delitem__(self, name):
        super().__delitem__(name)
        self.changed()

    def clear(self):
        super().clear()
        self.changed()

    def pop(self, *args):
        value = super().pop(*args)
        self.changed()
        return value

    def popitem(self):
        value = super().popitem()
        self.changed()
        return value

    def update(self, *args, **kwargs):
        try:
            super().update(*args, **kwargs)
        finally:
            self.changed()

    def setdefault(self, key, default = None):
        if key not in self:
            self[key] = default
        return self[key]

    def __ior__(self, values):
        self.update(values)
        return self

    def __deepcopy__(self, memo):
        from copy import deepcopy
        return {deepcopy(key, memo): deepcopy(value, memo) for key, value in self.items()}


class SceneSet(set):
    def __init__(self, values, changes):
        super().__init__(values)
        self.changes = changes

    def add(self, value):
        super().add(value)
        self.changes.Bump("visibility")

    def discard(self, value):
        super().discard(value)
        self.changes.Bump("visibility")

    def remove(self, value):
        super().remove(value)
        self.changes.Bump("visibility")

    def pop(self):
        value = super().pop()
        self.changes.Bump("visibility")
        return value

    def clear(self):
        super().clear()
        self.changes.Bump("visibility")

    def update(self, *values):
        try:
            super().update(*values)
        finally:
            self.changes.Bump("visibility")

    def difference_update(self, *values):
        super().difference_update(*values)
        self.changes.Bump("visibility")

    def intersection_update(self, *values):
        super().intersection_update(*values)
        self.changes.Bump("visibility")

    def symmetric_difference_update(self, values):
        super().symmetric_difference_update(values)
        self.changes.Bump("visibility")

    def __ior__(self, values):
        self.update(values)
        return self

    def __iand__(self, values):
        self.intersection_update(values)
        return self

    def __isub__(self, values):
        self.difference_update(values)
        return self

    def __ixor__(self, values):
        self.symmetric_difference_update(values)
        return self

    def __deepcopy__(self, memo):
        return set(self)
