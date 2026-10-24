"""Class visibility and undoable hiding of individual scene objects."""
from planner_app.models import Elevator
from planner_app.models import Door, Furnishing, OpenDoorway, PocketDoor, BarnDoor, BifoldDoor, SlidingDoor, MeasurementGuide, Arrow, Counter, Railing, Stair, Window, Label, NorthArrow, Fireplace


class VisibilityMixin:
    def IsObjectVisible(self, obj):
        if not self.visibility["World"] or id(obj) in self.hiddenObjectIds:
            return False
        return self.visibility[self.ObjectVisibilityCategory(obj)]

    def ObjectVisibilityCategory(self, obj):
        if isinstance(obj, Elevator):
            return "Elevators"
        if isinstance(obj, NorthArrow):
            return "North arrows"
        if isinstance(obj, Fireplace):
            return "Fireplaces"
        if isinstance(obj, MeasurementGuide):
            return "Measurement guides"
        if isinstance(obj, Arrow):
            return "Arrows"
        if isinstance(obj, Label):
            return "Labels"
        if isinstance(obj, Furnishing):
            return "Furnishings"
        if isinstance(obj, Railing):
            return "Railings"
        if isinstance(obj, Counter):
            return "Counters"
        if isinstance(obj, Stair):
            return "Stairs"
        if isinstance(obj, Window):
            category = "Doors" if isinstance(obj, (Door, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway)) else "Windows"
            return category
        return "Walls"

    def HideSelection(self):
        self.CancelInteraction()
        objects = {id(obj): obj for obj, index in self.SelectionEntries()}
        if not objects:
            return False
        # Attached openings disappear together with their parent wall.
        objects.update((id(obj), obj) for obj in self.windows if id(obj.parentWall) in objects)
        before = self.CaptureState()
        objects = {**{id(obj): obj for obj in self.hiddenObjects}, **objects}
        self.hiddenObjects = list(objects.values())
        self.hiddenObjectIds = set(objects)
        self.SetSelection([])
        self.RecordEdit(before)
        return True

    def HideUnselected(self):
        self.CancelInteraction()
        selectedIds = {id(obj) for obj, index in self.SelectionEntries()}
        if not selectedIds:
            return False
        objects = self.walls + self.windows + self.furnishings + self.labels
        hidden = [obj for obj in objects if id(obj) not in selectedIds]
        hiddenIds = {id(obj) for obj in hidden}
        if hiddenIds == self.hiddenObjectIds:
            return False
        before = self.CaptureState()
        self.hiddenObjects = hidden
        self.hiddenObjectIds = hiddenIds
        self.RecordEdit(before)
        self.selectionChanged.emit()
        self.update()
        return True

    def UnhideObjects(self):
        self.CancelInteraction()
        if not self.hiddenObjects:
            return False
        before = self.CaptureState()
        self.hiddenObjects = []
        self.hiddenObjectIds = set()
        self.RecordEdit(before)
        self.selectionChanged.emit()
        self.update()
        return True
