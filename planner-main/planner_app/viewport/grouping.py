"""Persistent object groups and optional expansion of object selections."""

from planner_app.graphics.palette import themeColors


class GroupingMixin:
    def SelectionColor(self, obj):
        if any(member is obj for group in self.objectGroups for member in group):
            return themeColors["groupSelectionOutline"]
        return themeColors["selectionOutline"]

    def ExpandGroupedSelection(self, entries):
        members = {id(obj): group for group in self.objectGroups for obj in group}
        sceneIds = {id(obj) for obj in self.walls + self.windows + self.furnishings + self.labels}
        expanded = {}
        for obj, index in entries:
            # Control vertices remain individually editable.
            if self.groupModeEnabled and index is None:
                for member in members.get(id(obj), ()):
                    if id(member) in sceneIds and self.IsObjectVisible(member) and member is not obj:
                        expanded[(id(member), None)] = (member, None)
            if self.IsObjectVisible(obj):
                expanded[(id(obj), index)] = (obj, index)
        return list(expanded.values())

    def SetGroupMode(self, enabled):
        self.groupModeEnabled = enabled
        if enabled:
            self.SetSelection(self.SelectionEntries())
        self.settingsChanged.emit()

    def PruneObjectGroups(self):
        sceneIds = {id(obj) for obj in self.walls + self.windows + self.furnishings + self.labels}
        groups = [tuple(obj for obj in group if id(obj) in sceneIds) for group in self.objectGroups]
        self.objectGroups = [group for group in groups if len(group) > 1]

    def GroupSelection(self):
        self.CancelInteraction()
        objects = list({id(obj): obj for obj, index in self.SelectionEntries()}.values())
        if len(objects) < 2:
            return False
        selectedIds = {id(obj) for obj in objects}
        if any({id(obj) for obj in group} == selectedIds for group in self.objectGroups):
            return False
        before = self.CaptureState()
        groups = [tuple(obj for obj in group if id(obj) not in selectedIds) for group in self.objectGroups]
        self.objectGroups = [group for group in groups if len(group) > 1] + [tuple(objects)]
        self.SetSelection([(obj, None) for obj in objects])
        self.RecordEdit(before)
        return True

    def UngroupSelection(self):
        self.CancelInteraction()
        selectedIds = {id(obj) for obj, index in self.SelectionEntries()}
        if not any(id(obj) in selectedIds for group in self.objectGroups for obj in group):
            return False
        before = self.CaptureState()
        groups = [tuple(obj for obj in group if id(obj) not in selectedIds) for group in self.objectGroups]
        self.objectGroups = [group for group in groups if len(group) > 1]
        self.RecordEdit(before)
        self.selectionChanged.emit()
        self.update()
        return True
