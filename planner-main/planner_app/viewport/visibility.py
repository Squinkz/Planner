"""Class visibility and undoable hiding of individual scene objects."""
from itertools import chain
from planner_app.selection_policy import PlanHideSelection, PlanHideUnselected
from planner_app.models import Elevator
from planner_app.models import Door, SwingingDoor, DoubleDoor, Furnishing, OpenDoorway, PocketDoor, BarnDoor, BifoldDoor, SlidingDoor, MeasurementGuide, BoundaryLine, DashedLine, SolidLine, Arrow, Counter, Railing, Stair, Window, Label, NorthArrow, Fireplace


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
        if isinstance(obj, SolidLine):
            return "Solid lines"
        if isinstance(obj, DashedLine):
            return "Dashed lines"
        if isinstance(obj, BoundaryLine):
            return "Boundary lines"
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
            category = "Doors" if isinstance(obj, (Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway)) else "Windows"
            return category
        return "Walls"

    def HideSelection(self):
        self.CancelInteraction()
        proposal = PlanHideSelection(self.SelectionEntries(), self.hiddenObjects,
                                     ((obj, obj.parentWall) for obj in self.windows))
        if proposal is None:
            return False
        before = self.CaptureState()
        self.hiddenObjects, self.hiddenObjectIds = proposal
        self.SetSelection([])
        self.RecordEdit(before)
        return True

    def HideUnselected(self):
        self.CancelInteraction()
        proposal = PlanHideUnselected(self.SelectionEntries(), chain(self.walls, self.windows, self.furnishings, self.labels),
                                      self.hiddenObjectIds)
        if proposal is None:
            return False
        before = self.CaptureState()
        self.hiddenObjects, self.hiddenObjectIds = proposal
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
