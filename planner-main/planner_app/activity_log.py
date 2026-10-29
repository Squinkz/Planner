"""Persistent activity descriptions with links to bounded, live undo journals."""
import base64
import copy
import hashlib
import json
import math
import re
import time
import zlib
from datetime import datetime, timezone
from PySide6 import QtCore


from .activity_records import (activityByteLimit, DecodeActivityLog, ActivityRecordFingerprint,
                               DescribeReferenceChange, DescribeRecordChanges, EncodeActivityLog,
                               EncodeActivityStacks, RestoreActivityStacks)


def EditFingerprint(edit):
    from .project_history import EncodeEdit
    return ActivityRecordFingerprint(EncodeEdit(edit))


def DescribeEdit(edit):
    from .history_edits import ReferenceImageEdit
    from .project_history import EncodeEntry
    if isinstance(edit, ReferenceImageEdit):
        return DescribeReferenceChange(edit.referenceChanges)
    changes = []
    for category, oldIndex, newIndex, old, new in edit.changes:
        obj = (old or new)[0]
        name = obj.definition["name"] if hasattr(obj, "definition") else type(obj).__name__
        first = second = None
        if old is not None and new is not None:
            first = EncodeEntry(category, old, old[1].objectId if category == 3 else None)
            second = EncodeEntry(category, new, new[1].objectId if category == 3 else None)
        changes.append((category, type(obj).__name__, name, obj.objectId, old is None, new is None, first, second))
    return DescribeRecordChanges(changes, groups = any(edit.groups), hidden = any(edit.hidden), orders = bool(edit.orders))


class ActivityLog(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.entries, self.sceneLinks, self.exportLinks, self.issues = [], {}, {}, {}
        self.nextId, self.revision, self.generation = 1, 0, 0
        self.restoring = False
        self.persisted = False
        self.window = None
        self.cache = None
        self.digests = {}
        self.lastMessages = {}
        self.gridStep = 100
        self.settingsBaseline = None
        self.settingsTimer = QtCore.QTimer(self)
        self.settingsTimer.setSingleShot(True)
        self.settingsTimer.setInterval(300)
        self.settingsTimer.timeout.connect(self.FlushSettings)
        self.issueTimer = QtCore.QTimer(self)
        self.issueTimer.setSingleShot(True)
        self.issueTimer.setInterval(150)
        self.issueTimer.timeout.connect(self.RecheckIssues)
        main.viewport.sceneChanged.connect(self.QueueIssues)
        main.viewport.settingsChanged.connect(self.QueueIssues)

    def Add(self, kind, summary, details = "", objects = (), anchor = None, timestamp = True, linkScene = False):
        if self.main.projectLoading or self.restoring:
            return None
        if linkScene and self.main.viewport.undoHistory:
            editId = self.sceneLinks.get(self.main.viewport.undoHistory[-1].token)
            if editId is not None:
                anchor = dict(scope = "Scene", edit = editId, side = "after")
        entry = dict(id = self.nextId, time = datetime.now(timezone.utc).isoformat(timespec = "seconds") if timestamp else None,
                     kind = kind, summary = summary[:4096], details = details[:65536],
                     objects = sorted(set(objects)), anchor = anchor)
        self.entries.append(entry)
        self.persisted = True
        self.nextId += 1
        self.Touch()
        return entry

    def Touch(self):
        self.revision += 1
        self.cache = None
        self.changed.emit()
        if hasattr(self.main, "projectTimer") and not self.main.projectLoading:
            self.main.projectTimer.start(0)

    def Message(self, message, isError = True, kind = None, details = ""):
        if not message or self.main.projectLoading:
            return
        key = (message, isError, kind)
        now = time.monotonic()
        if now - self.lastMessages.get(key, -100) < 5:
            return
        # Bound only the deduplication cache, never the project log itself.
        self.lastMessages = {key: value for key, value in self.lastMessages.items() if now - value < 5}
        self.lastMessages[key] = now
        if kind is None:
            kind = "Application" if isError and message.startswith(("Startup", "Session", "Recovery", "Previous recovery")) else "Blocked action" if isError else "Notice"
        self.Add(kind, message, details)

    def SettingsSnapshot(self):
        from .graphics import palette
        values = self.main.ProjectSettings()
        # Reference geometry and Export already have dedicated edit journals.
        reference = values.pop("referenceImage", None)
        for name in ("exportSettings", "exportFolder", "exportFileName", "ignoredPotentialIssues"):
            values.pop(name, None)
        values["referenceImageVisible"] = bool(reference and reference["visible"])
        view = self.main.exportPanel.projectView
        values["canvasTheme"] = view["canvasTheme"] if view is not None else palette.activeCanvasTheme
        values["uiTheme"] = palette.activeUITheme
        return copy.deepcopy(values)

    def SettingsChanged(self):
        if not self.main.projectLoading and not self.restoring:
            self.settingsTimer.start()

    def FlushSettings(self):
        if self.main.projectLoading:
            return
        self.settingsTimer.stop()
        current = self.SettingsSnapshot()
        if self.settingsBaseline is not None:
            changed = sorted(key for key in current if current[key] != self.settingsBaseline.get(key))
            if changed:
                labels = {"unitsMode": "units", "measurementPrecision": "canvas precision",
                          "canvasTheme": "canvas theme", "uiTheme": "UI theme", "buildSettings": "Build defaults",
                          "showMeasurements": "dimension visibility", "measurementVisibility": "dimension categories",
                          "measurementSettings": "dimension splitting", "wallMeasurementMode": "wall dimension mode",
                          "wallMeasurementReference": "wall reference", "showGrid": "grid visibility",
                          "viewportSettings": "grid appearance", "lineworkSettings": "line weights",
                          "referenceImageVisible": "reference image visibility", "visibility": "object visibility"}
                self.Add("Settings", "Changed " + ", ".join(labels.get(key, re.sub(r"(?<=[a-z])(?=[A-Z])", " ", key).lower()) for key in changed))
        self.settingsBaseline = current

    def SceneEdited(self, edit, replaced = None):
        if edit is None or self.main.projectLoading:
            self.changed.emit()
            return
        summary, details, objects = DescribeEdit(edit)
        existing = self.sceneLinks.pop(replaced.token, None) if replaced is not None else None
        entry = next((entry for entry in reversed(self.entries) if entry["id"] == existing), None) if existing else None
        if entry is None:
            entry = self.Add("Edit", summary, details, objects)
        else:
            entry.update(summary = summary, details = details[:65536], objects = objects,
                         time = datetime.now(timezone.utc).isoformat(timespec = "seconds"))
            self.Touch()
        if entry is not None:
            entry["anchor"] = dict(scope = "Scene", edit = entry["id"], side = "after")
            self.sceneLinks[edit.token] = entry["id"]
            self.PruneLinks()
            self.cache = None
            self.changed.emit()

    def PruneLinks(self):
        v, panel = self.main.viewport, self.main.exportPanel
        tokens = {edit.token for edit in v.undoHistory + v.redoHistory}
        self.sceneLinks = {token: value for token, value in self.sceneLinks.items() if token in tokens}
        self.digests = {token: value for token, value in self.digests.items() if token in tokens}
        pairs = {id(pair) for pair in panel.exportUndoHistory + panel.exportRedoHistory}
        self.exportLinks = {token: value for token, value in self.exportLinks.items() if token in pairs}

    def ExportEdited(self, pair):
        if self.main.projectLoading or self.restoring:
            return
        before, after = pair
        keys = sorted(key for key in set(before["overrides"]) | set(after["overrides"])
                      if before["overrides"].get(key) != after["overrides"].get(key))
        labels = {"fileType": "file type", "unitsMode": "units", "bounds": "crop", "scale": "scale",
                  "solidObjects": "solid objects", "floors": "room style", "roomStyle": "room style", "solidRooms": "solid rooms", "wallStyle": "wall style",
                  "canvasTheme": "theme", "showGrid": "grid visibility", "gridOrigin": "grid origin",
                  "measurementVisibility": "dimensions", "wallMeasurementMode": "wall dimension mode",
                  "wallMeasurementReference": "wall reference", "visibility": "object visibility",
                  "viewportSettings": "grid appearance", "lineworkSettings": "line weights"}
        fields = [labels.get(key, re.sub(r"(?<=[a-z])(?=[A-Z])", " ", key).lower()) for key in keys]
        if before["exportFolder"] != after["exportFolder"]:
            fields.append("folder")
        if before["exportFileName"] != after["exportFileName"]:
            fields.append("filename")
        entry = self.Add("Export", "Changed export " + (", ".join(fields) or "settings"))
        if entry is not None:
            entry["anchor"] = dict(scope = "Export", edit = entry["id"], side = "after")
            self.exportLinks[id(pair)] = entry["id"]
            self.PruneLinks()
            self.changed.emit()

    def Travel(self, edit, forward, scope = "Scene"):
        link = (self.sceneLinks.get(edit.token) if scope == "Scene" else self.exportLinks.get(id(edit)))
        original = next((entry for entry in reversed(self.entries) if entry["id"] == link), None)
        summary = DescribeEdit(edit)[0] if scope == "Scene" else (
            original["summary"].removeprefix("Undid: ").removeprefix("Redid: ") if original else "Changed export settings")
        entry = self.Add("History", ("Redid: " if forward else "Undid: ") + summary,
                         anchor = dict(scope = scope, edit = link, side = "after" if forward else "before") if link else None)
        if entry is not None and link is None:
            entry["anchor"] = dict(scope = scope, edit = entry["id"], side = "after" if forward else "before")
            if scope == "Scene":
                self.sceneLinks[edit.token] = entry["id"]
            else:
                self.exportLinks[id(edit)] = entry["id"]
        self.cache = None
        self.changed.emit()

    def Position(self, entry):
        anchor = entry.get("anchor")
        if not anchor:
            return None
        if anchor["scope"] == "Scene":
            undo, redo = self.main.viewport.undoHistory, self.main.viewport.redoHistory
            links = [self.sceneLinks.get(edit.token) for edit in undo + list(reversed(redo))]
        else:
            panel = self.main.exportPanel
            undo, redo = panel.exportUndoHistory, panel.exportRedoHistory
            links = [self.exportLinks.get(id(pair)) for pair in undo + list(reversed(redo))]
        if anchor["edit"] not in links:
            return None
        return anchor["scope"], len(undo), links.index(anchor["edit"]) + (anchor["side"] == "after")

    def Restore(self, entry):
        self.main.FinishProjectInteraction()
        self.main.exportPanel.EndExportGesture()
        position = self.Position(entry)
        if position is None or position[1] == position[2]:
            return False
        scope, current, target = position
        v, panel = self.main.viewport, self.main.exportPanel
        if scope == "Scene":
            # Validate the complete route before changing anything.
            from .history_edits import ReferenceImageEdit
            state, reference = v.CaptureState(), self.main.referenceImage.Snapshot()
            edits = list(reversed(v.undoHistory))[:current - target] if target < current else list(reversed(v.redoHistory))[:target - current]
            for edit in edits:
                state = edit.Apply(state, target > current, validate = True)
                if isinstance(edit, ReferenceImageEdit):
                    reference = edit.ApplyReference(reference, target > current, validate = True)
            if panel.projectView is not None:
                self.main.sidebarTabs.setCurrentIndex(0)
                panel.SetActive(False)
        else:
            self.main.sidebarTabs.setCurrentWidget(panel)
            panel.SetActive(True)
        self.restoring = True
        try:
            for unused in range(abs(target - current)):
                if scope == "Scene":
                    v.Undo() if target < current else v.Redo()
                else:
                    panel.UndoExport() if target < current else panel.RedoExport()
        finally:
            self.restoring = False
        self.Add("History", f"Restored {scope.lower()} to: {entry['summary']}", anchor = dict(entry["anchor"]))
        return True

    def QueueIssues(self):
        problems = getattr(self.main, "problemsWindow", None)
        if not self.main.projectLoading and (problems is None or not problems.isVisible()):
            self.issueTimer.start()

    def RecheckIssues(self):
        from .scene_problems import FindSceneProblems
        if self.main.projectLoading:
            return
        v = self.main.viewport
        if v.dragStart is not None or v.isDragging or v.isPanning or self.main.referenceImage.drag is not None:
            self.issueTimer.start()
            return
        includePotential = any(key.endswith(":True") for key in self.issues)
        self.ObserveIssues(FindSceneProblems(v, includePotential = includePotential, gridStep = self.gridStep), self.gridStep)

    def ObserveIssues(self, issues, gridStep):
        if self.main.projectLoading:
            return
        self.gridStep = gridStep
        current = {}
        for issue in issues:
            obj = issue["object"]
            key = f"{obj.objectId}:{issue['code']}:{bool(issue.get('potential'))}"
            current[key] = dict(object = obj.objectId, label = issue["label"][:4096], fingerprint = issue.get("fingerprint"))
            if key not in self.issues:
                self.Add("Potential issue" if issue.get("potential") else "Problem",
                         f"Detected: {issue['label']} — Object #{obj.objectId:04d}", issue["description"], [obj.objectId])
        liveIds = {obj.objectId for obj in self.main.viewport.walls + self.main.viewport.windows + self.main.viewport.furnishings + self.main.viewport.labels}
        ignored = set(self.main.viewport.ignoredPotentialIssues)
        for key, issue in self.issues.items():
            if key not in current:
                verb = "Ignored" if issue["fingerprint"] in ignored else "Removed with object" if issue["object"] not in liveIds else "Resolved"
                self.Add("Resolution", f"{verb}: {issue['label']} — Object #{issue['object']:04d}", objects = [issue["object"]])
        if current != self.issues:
            self.issues = current
            self.cache = None
            self.Touch()

    def Encode(self):
        v = self.main.viewport
        key = (self.revision, tuple(edit.token for edit in v.undoHistory), tuple(edit.token for edit in v.redoHistory))
        if self.cache is not None and self.cache[0] == key:
            return self.cache[1]
        if not self.entries and not self.persisted:
            return None
        stacks = {name: [(edit.token, edit) for edit in stack] for name, stack in (("undo", v.undoHistory), ("redo", v.redoHistory))}
        links = EncodeActivityStacks(stacks, self.sceneLinks, self.digests, EditFingerprint)
        data = dict(entries = self.entries, issues = self.issues, gridStep = self.gridStep, **links)
        record = EncodeActivityLog(data)
        self.cache = key, record
        return record

    def Load(self, data):
        self.issueTimer.stop()
        self.settingsTimer.stop()
        self.entries, self.sceneLinks, self.exportLinks, self.issues = [], {}, {}, {}
        self.digests, self.lastMessages = {}, {}
        self.cache = None
        self.generation += 1
        self.nextId = 1
        self.persisted = data is not None
        if data is not None:
            self.entries = data["entries"]
            self.nextId = max((entry["id"] for entry in self.entries), default = 0) + 1
            self.issues, self.gridStep = data["issues"], data["gridStep"]
            stacks = {name: [(edit.token, edit) for edit in stack] for name, stack in (
                ("undo", self.main.viewport.undoHistory), ("redo", self.main.viewport.redoHistory))}
            self.sceneLinks, self.digests = RestoreActivityStacks(data, stacks, EditFingerprint)
        else:
            # Old projects retain descriptions and restoration for their existing
            # journal, without inventing timestamps or earlier application events.
            for edit in self.main.viewport.undoHistory + list(reversed(self.main.viewport.redoHistory)):
                summary, details, objects = DescribeEdit(edit)
                entry = dict(id = self.nextId, time = None, kind = "Earlier edit", summary = summary,
                             details = details, objects = objects,
                             anchor = dict(scope = "Scene", edit = self.nextId, side = "after"))
                self.entries.append(entry)
                self.sceneLinks[edit.token] = self.nextId
                self.nextId += 1
        self.revision = 0
        self.settingsBaseline = self.SettingsSnapshot()
        self.changed.emit()

    def Clear(self):
        self.FlushSettings()
        self.persisted = True
        self.entries, self.sceneLinks, self.exportLinks, self.issues = [], {}, {}, {}
        self.lastMessages, self.digests = {}, {}
        self.issueTimer.stop()
        self.generation += 1
        self.Touch()

    def Show(self):
        if self.window is None:
            from .ui.activity_log import ActivityLogWindow
            self.window = ActivityLogWindow(self.main)
            self.main.RefreshControlCursors(self.window)
        if self.window.isMinimized():
            self.window.setWindowState(self.window.windowState() & ~QtCore.Qt.WindowState.WindowMinimized)
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
