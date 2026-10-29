"""Persistent object groups and optional expansion of object selections."""

from planner_app.graphics.palette import themeColors
from itertools import chain
from planner_app.selection_policy import ExpandSelectionGroups, FilterObjectGroups, PlanGroupSelection, PlanUngroupSelection


class GroupingMixin:
    def SelectionColor(self, obj):
        if any(member is obj for group in self.objectGroups for member in group):
            return themeColors["groupSelectionOutline"]
        return themeColors["selectionOutline"]

    def ExpandGroupedSelection(self, entries):
        sceneIds = (id(obj) for obj in chain(self.walls, self.windows, self.furnishings, self.labels))
        expanded = ExpandSelectionGroups(entries, self.objectGroups, sceneIds, self.groupModeEnabled)
        return [(obj, index) for obj, index in expanded if self.IsObjectVisible(obj)]

    def SetGroupMode(self, enabled):
        self.groupModeEnabled = enabled
        if enabled:
            self.SetSelection(self.SelectionEntries())
        self.settingsChanged.emit()

    def PruneObjectGroups(self):
        sceneIds = (id(obj) for obj in chain(self.walls, self.windows, self.furnishings, self.labels))
        self.objectGroups = FilterObjectGroups(self.objectGroups, sceneIds)

    def GroupSelection(self):
        self.CancelInteraction()
        proposal = PlanGroupSelection(self.SelectionEntries(), self.objectGroups)
        if proposal is None:
            return False
        before = self.CaptureState()
        self.objectGroups, objects = proposal
        self.SetSelection([(obj, None) for obj in objects])
        self.RecordEdit(before)
        return True

    def UngroupSelection(self):
        self.CancelInteraction()
        groups = PlanUngroupSelection(self.SelectionEntries(), self.objectGroups)
        if groups is None:
            return False
        before = self.CaptureState()
        self.objectGroups = groups
        self.RecordEdit(before)
        self.selectionChanged.emit()
        self.update()
        return True
