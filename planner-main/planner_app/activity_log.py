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


activityByteLimit = 64 * 1024 * 1024


def DecodeActivityLog(record):
    if record is None:
        return None
    try:
        if (not isinstance(record, dict) or set(record) != {"version", "encoding", "data"}
                or type(record["version"]) is not int or record["version"] != 1 or record["encoding"] != "zlib-base64"):
            raise ValueError()
        if not isinstance(record["data"], str) or len(record["data"]) > activityByteLimit:
            raise ValueError()
        decoder = zlib.decompressobj()
        payload = decoder.decompress(base64.b64decode(record["data"], validate = True), activityByteLimit + 1)
        if len(payload) > activityByteLimit or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError()
        data = json.loads(payload)
        if not isinstance(data, dict) or set(data) != {"entries", "undo", "redo", "issues", "gridStep"}:
            raise ValueError()
        entries = data["entries"]
        if not isinstance(entries, list):
            raise ValueError()
        ids = set()
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"id", "time", "kind", "summary", "details", "objects", "anchor"}:
                raise ValueError()
            if type(entry["id"]) is not int or entry["id"] <= 0 or entry["id"] in ids:
                raise ValueError()
            ids.add(entry["id"])
            for key, limit in (("kind", 32), ("summary", 4096), ("details", 65536)):
                if not isinstance(entry[key], str) or len(entry[key]) > limit:
                    raise ValueError()
            if entry["time"] is not None:
                if not isinstance(entry["time"], str) or len(entry["time"]) > 40:
                    raise ValueError()
                timestamp = datetime.fromisoformat(entry["time"])
                if timestamp.tzinfo is None or not 1900 <= timestamp.year <= 9998:
                    raise ValueError()
            if not isinstance(entry["objects"], list) or any(type(value) is not int or value <= 0 for value in entry["objects"]):
                raise ValueError()
            anchor = entry["anchor"]
            if anchor is not None and (not isinstance(anchor, dict) or set(anchor) != {"scope", "edit", "side"}
                    or anchor["scope"] not in ("Scene", "Export") or type(anchor["edit"]) is not int
                    or anchor["edit"] <= 0 or anchor["side"] not in ("before", "after")):
                raise ValueError()
        for name in ("undo", "redo"):
            if not isinstance(data[name], list) or len(data[name]) > 200:
                raise ValueError()
            for link in data[name]:
                if link is not None and (not isinstance(link, list) or len(link) != 2
                        or type(link[0]) is not int or link[0] not in ids or not isinstance(link[1], str)
                        or len(link[1]) != 64 or any(char not in "0123456789abcdef" for char in link[1])):
                    raise ValueError()
        if any(entry["anchor"] and entry["anchor"]["edit"] not in ids for entry in entries):
            raise ValueError()
        if not isinstance(data["issues"], dict) or len(data["issues"]) > 100000:
            raise ValueError()
        for key, issue in data["issues"].items():
            if not isinstance(key, str) or not isinstance(issue, dict) or set(issue) != {"object", "label", "fingerprint"}:
                raise ValueError()
            if type(issue["object"]) is not int or issue["object"] <= 0 or not isinstance(issue["label"], str) or len(issue["label"]) > 4096:
                raise ValueError()
            if issue["fingerprint"] is not None and (not isinstance(issue["fingerprint"], str) or len(issue["fingerprint"]) > 128):
                raise ValueError()
        if type(data["gridStep"]) not in (int, float) or not 0 < data["gridStep"] <= 1e12:
            raise ValueError()
        return data
    except (ValueError, TypeError, KeyError, OverflowError, zlib.error, RecursionError) as error:
        raise ValueError("Invalid activity log.") from error


def EditFingerprint(edit):
    from .project_history import EncodeEdit
    # Project decoding normalizes numeric fields to floats. Equivalent 200 and
    # 200.0 values must identify the same retained edit after reopening.
    record = json.loads(json.dumps(EncodeEdit(edit)), parse_int = float)
    return hashlib.sha256(json.dumps(record, sort_keys = True, separators = (",", ":"),
                                    ensure_ascii = False, allow_nan = False).encode("utf-8")).hexdigest()


def DescribeEdit(edit):
    from .history_edits import ReferenceImageEdit
    from .project_history import EncodeEntry
    if isinstance(edit, ReferenceImageEdit):
        names = set(edit.referenceChanges)
        verb = ("Loaded" if "data" in names else "Resized" if names & {"width", "height"} else
                "Rotated" if "angle" in names else "Moved" if "center" in names else "Changed")
        return verb + " Reference Image", ", ".join(sorted(names)) or "Rotation pivot", []
    descriptions, objects = [], []
    for category, oldIndex, newIndex, old, new in edit.changes:
        obj = (old or new)[0]
        name = obj.definition["name"] if hasattr(obj, "definition") else type(obj).__name__
        if type(obj).__name__ == "Furnishing":
            name = "Furnishing"
        elif name == "MeasurementGuide":
            name = "Dimension Guide"
        else:
            name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
        verb = "Created" if old is None else "Deleted" if new is None else "Changed"
        if old is not None and new is not None:
            first = EncodeEntry(category, old, old[1].objectId if category == 3 else None)
            second = EncodeEntry(category, new, new[1].objectId if category == 3 else None)
            changed = {key for key in first if first[key] != second.get(key)}
            if "text" in changed:
                verb = "Renamed" if type(obj).__name__ == "RoomLabel" else "Edited text of"
            elif changed <= {"first", "second", "middle", "center"}:
                if category == 3:
                    verb = "Moved"
                else:
                    delta = [second["first"][axis] - first["first"][axis] for axis in (0, 1)]
                    other = [second["second"][axis] - first["second"][axis] for axis in (0, 1)]
                    verb = "Moved" if all(abs(a - b) < 1e-6 for a, b in zip(delta, other)) else "Reshaped"
                    if verb == "Reshaped" and category in (5, 8):
                        oldLength = math.dist(first["first"], first["second"])
                        newLength = math.dist(second["first"], second["second"])
                        verb = "Rotated" if math.isclose(oldLength, newLength, abs_tol = 1e-6) else "Resized"
            elif changed & {"width", "length"}:
                verb = "Resized"
            elif "material" in changed:
                verb = "Changed material of"
            elif "intensity" in changed:
                verb = "Changed opacity of"
            elif changed & {"hingeAtSecond", "swingsOutwards", "panelsFlipped", "flipHorizontal", "flipVertical"}:
                verb = "Flipped"
            elif "directionReversed" in changed:
                verb = "Reversed"
            elif "measurementFlipped" in changed:
                verb = "Flipped dimensions of"
        descriptions.append(f"{verb} {name} #{obj.objectId:04d}")
        objects.append(obj.objectId)
    if not descriptions:
        if any(edit.groups):
            descriptions.append("Changed object groups")
        elif any(edit.hidden):
            descriptions.append("Changed object visibility")
        elif edit.orders:
            descriptions.append("Changed object order")
        else:
            descriptions.append("Edited scene")
    summary = descriptions[0] if len(descriptions) == 1 else f"{descriptions[0]} (+{len(descriptions) - 1} objects)"
    return summary, "\n".join(descriptions), sorted(set(objects))


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
                  "solidObjects": "solid objects", "floors": "floors", "wallStyle": "wall style",
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
        links = {}
        for name, stack in (("undo", v.undoHistory), ("redo", v.redoHistory)):
            links[name] = []
            for edit in stack:
                entryId = self.sceneLinks.get(edit.token)
                if entryId is not None and edit.token not in self.digests:
                    self.digests[edit.token] = EditFingerprint(edit)
                links[name].append([entryId, self.digests[edit.token]] if entryId is not None else None)
        data = dict(entries = self.entries, issues = self.issues, gridStep = self.gridStep, **links)
        raw = json.dumps(data, ensure_ascii = False, separators = (",", ":"), allow_nan = False).encode("utf-8")
        if len(raw) > activityByteLimit:
            raise ValueError("The activity log exceeds the 64 MiB limit. Clear the log before saving.")
        record = dict(version = 1, encoding = "zlib-base64", data = base64.b64encode(zlib.compress(raw)).decode("ascii"))
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
            for name, stack in (("undo", self.main.viewport.undoHistory), ("redo", self.main.viewport.redoHistory)):
                if len(stack) != len(data[name]):
                    continue
                for edit, link in zip(stack, data[name]):
                    if link is not None and EditFingerprint(edit) == link[1]:
                        self.sceneLinks[edit.token] = link[0]
                        self.digests[edit.token] = link[1]
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
