"""Atomic background recovery checkpoints for the current canvas and editor UI."""
import json
import os
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from PySide6 import QtCore, QtWidgets
from planner_app.project_codec import DecodeProject, EncodeUsedFurnishings, ValidateNumber, ValidateEditorUi, projectFileLimit
from planner_app.graphics.theme import gridIntensityDefaults
from planner_app.viewport.diagnostics import MeasureRecoveryWrite, MeasureRecoveryCheckpoint


def SessionFilePath():
    override = os.environ.get("PLANNER_SESSION_PATH")
    return (Path(override) if override else
            Path(QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.GenericDataLocation)) /
            "Planner" / "session.json")


def AcquireSessionLock():
    """Hold one process owner for a recovery file, including explicit overrides."""
    path = SessionFilePath()
    path.parent.mkdir(parents = True, exist_ok = True)
    lock = QtCore.QLockFile(str(path) + ".lock")
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        raise OSError("Another Planner instance is using this recovery session. Close it before starting Planner again.")
    return lock


def WriteSessionFile(path, data, payload = None, previousPayload = None):
    try:
        if payload is None:
            payload = json.dumps(data, ensure_ascii = False, separators = (",", ":"), allow_nan = False).encode("utf-8")
        if len(payload) > projectFileLimit:
            raise ValueError("The checkpoint, including undo history, exceeds the 64 MB file limit. The previous checkpoint has been kept.")
        path.parent.mkdir(parents = True, exist_ok = True)
        if path.exists():
            previous = path.read_bytes()
            try:
                if previousPayload is not None and previous == previousPayload:
                    validPrevious = True
                else:
                    previousData = json.loads(previous)
                    validPrevious = previousData.get("format") == "Planner Session" and previousData.get("version") == 1
            except (ValueError, AttributeError):
                validPrevious = False
            if validPrevious and previous != payload:
                backup = QtCore.QSaveFile(str(path.with_name(path.name + ".bak")))
                if not backup.open(QtCore.QIODevice.OpenModeFlag.WriteOnly):
                    raise OSError(backup.errorString())
                if backup.write(previous) != len(previous):
                    error = backup.errorString()
                    backup.cancelWriting()
                    raise OSError(error)
                if not backup.commit():
                    raise OSError(backup.errorString())
        file = QtCore.QSaveFile(str(path))
        if not file.open(QtCore.QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(file.errorString())
        if file.write(payload) != len(payload):
            error = file.errorString()
            file.cancelWriting()
            raise OSError(error)
        if not file.commit():
            raise OSError(file.errorString())
    except (OSError, ValueError, TypeError) as error:
        return str(error)
    return None


class SessionWriter:
    """Reuse immutable encoded scene/history chunks on the single recovery worker."""
    def __init__(self):
        self.chunks = {}
        self.previousPayload = None
        self.previousPath = None

    @MeasureRecoveryWrite
    def Write(self, path, data):
        try:
            project = dict(data["project"])
            chunks = []
            for name in ("scene", "history"):
                source = project.pop(name)
                cached = self.chunks.get(name)
                # ProjectSceneData and ProjectHistory replace their encoded containers
                # on edits/restores; camera/UI changes keep the same immutable objects.
                if cached is None or cached[0] is not source:
                    cached = (source, json.dumps(source, ensure_ascii = False, separators = (",", ":"), allow_nan = False).encode("utf-8"))
                    self.chunks[name] = cached
                chunks.append(b',"' + name.encode("ascii") + b'":' + cached[1])
            projectPayload = json.dumps(project, ensure_ascii = False, separators = (",", ":"), allow_nan = False).encode("utf-8")
            projectPayload = b"".join([projectPayload[:-1], *chunks, b"}"])
            envelope = {name: value for name, value in data.items() if name != "project"}
            payload = json.dumps(envelope, ensure_ascii = False, separators = (",", ":"), allow_nan = False).encode("utf-8")
            payload = b"".join([payload[:-1], b',"project":', projectPayload, b"}"])
        except (ValueError, TypeError, KeyError) as error:
            return str(error)
        previous = self.previousPayload if path == self.previousPath else None
        error = WriteSessionFile(path, data, payload = payload, previousPayload = previous)
        if error is None:
            self.previousPayload, self.previousPath = payload, path
        return error


class SessionMixin:
    def InitializeSession(self):
        self.sessionPath = SessionFilePath()
        self.sessionExecutor = None
        self.sessionWriter = SessionWriter()
        self.sessionPanDeferredAt = None
        self.sessionFuture = None
        self.sessionSignature = None
        self.sessionError = None
        self.sessionRestored = False
        self.sessionRecoveryBlocked = False
        self.sessionTimer = QtCore.QTimer(self)
        self.sessionTimer.setSingleShot(True)
        self.sessionTimer.timeout.connect(self.WriteSession)
        self.sessionPollTimer = QtCore.QTimer(self)
        self.sessionPollTimer.setInterval(1000)
        self.sessionPollTimer.timeout.connect(self.WriteSession)
        self.RestoreSession()
        if not self.sessionRestored:
            self.LoadStartupProject()
        self.sessionPollTimer.start()

    def SessionUiState(self):
        v = self.viewport
        return {"geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
                "maximized": self.isMaximized(),
                "size": [self.width(), self.height()],
                "mainSplitter": self.savedSplitterSizes if self.viewportOnlyMode else self.mainSplitter.sizes(),
                "propertiesSplitter": self.propertiesExportSizes if self.propertiesExportSizes is not None else self.sidebarContentSplitter.sizes(),
                "propertiesCollapsed": self.propertiesCollapsed, "propertiesRestoreHeight": self.propertiesRestoreHeight,
                "tab": self.sidebarTabs.currentIndex(),
                "treeScroll": self.visibilityTree.verticalScrollBar().value(),
                "scroll": [area.verticalScrollBar().value() for area in self.findChildren(QtWidgets.QScrollArea)],
                "expanded": {name: item.isExpanded() for name, item in self.visibilityItems.items()},
                "selection": [[obj.objectId, index] for obj, index in v.SelectionEntries()],
                "rotationObject": getattr(v.furnishingRotationObject, "objectId", None)}

    @MeasureRecoveryCheckpoint
    def WriteSession(self, wait = False):
        if self.sessionRecoveryBlocked:
            return False
        v = self.viewport
        if not wait and (v.dragStart is not None or v.pendingWall is not None or
                         v.furnishingHandleDrag is not None or self.propertyDragBefore is not None
                         or self.referenceImage.drag is not None or self.referenceImage.fieldBefore is not None):
            return False
        if self.sessionFuture is not None:
            if not wait and not self.sessionFuture.done():
                return False
            error = self.sessionFuture.result()
            self.sessionFuture = None
            if error:
                self.sessionSignature = None
                if error != self.sessionError:
                    warnings.warn(f"Planner session recovery could not be saved: {error}", RuntimeWarning)
                    v.ShowClipboardError("Session recovery could not be saved.")
                self.sessionError = error
            else:
                self.sessionError = None
        if not wait and v.isPanning:
            now = monotonic()
            if self.sessionPanDeferredAt is None:
                self.sessionPanDeferredAt = now
            # Keep recovery bounded even if a middle-button gesture lasts minutes.
            if now - self.sessionPanDeferredAt < 10:
                return False
            self.sessionPanDeferredAt = now
        else:
            self.sessionPanDeferredAt = None
        if self.projectTimer.isActive():
            self.projectTimer.stop()
            self.RefreshProjectDirty()
        ui = self.SessionUiState()
        pan = self.exportPanel.projectPanOffset if self.exportPanel.projectPanOffset is not None else v.panOffset
        view = {"zoom": self.exportPanel.projectZoom if self.exportPanel.projectZoom is not None else v.zoom,
                "pan": [pan.x(), pan.y()]}
        signature = (self.projectSceneSignature, self.projectSettingsSignature, self.savedSceneSignature,
                     self.savedSettingsSignature, v.sceneRevision, str(self.projectPath), json.dumps(ui, sort_keys = True),
                     view["zoom"], tuple(view["pan"]), tuple(sorted(v.gridIntensities.items())),
                     tuple(v.wallPresetWidths), tuple(sorted(v.openingDefaultSizes.items())),
                     str(self.recoverySourcePath), str(self.recoveryBackupPath))
        if signature == self.sessionSignature and self.sessionPath.exists():
            return True
        data = {"format": "Planner Session", "version": 1, "projectPath": str(self.projectPath) if self.projectPath else None,
                "savedScene": self.savedSceneSignature.hex(), "savedSettings": self.savedSettingsSignature.hex(),
                "viewportSettings": dict(v.gridIntensities),
                "gridIntensityVersion": 2,
                "buildSettings": {"wallWidths": list(v.wallPresetWidths), "openingSizes": dict(v.openingDefaultSizes),
                                  "miscSizes": dict(v.miscDefaultSizes),
                                  **({"imperialSizes": dict(v.imperialDefaultSizes)} if v.imperialDefaultSizes else {})},
                "project": {"format": "Planner Project", "version": 1, "scene": self.projectSceneData,
                            "settings": self.ProjectSettings(), "view": view,
                            "history": self.ProjectHistory(), "ui": self.ProjectUiState()}, "ui": ui}
        embedded = EncodeUsedFurnishings(v)
        if embedded:
            data["project"]["furnishingDefinitions"] = embedded
        if self.recoverySourcePath is not None:
            data["projectRecovery"] = {"source": str(self.recoverySourcePath), "backup": str(self.recoveryBackupPath)}
        diagnostics = v.renderDiagnostics
        writeOptions = {}
        if diagnostics is not None and diagnostics.enabled:
            writeOptions = {"diagnostics": diagnostics, "jobId": diagnostics.BeginRecovery(wait)}
        if wait:
            error = self.sessionWriter.Write(self.sessionPath, data, **writeOptions)
            if error:
                self.sessionSignature = None
                self.sessionError = error
                warnings.warn(f"Planner session recovery could not be saved: {error}", RuntimeWarning)
                return False
            self.sessionError = None
        else:
            if self.sessionExecutor is None:
                self.sessionExecutor = ThreadPoolExecutor(max_workers = 1, thread_name_prefix = "PlannerRecovery")
            self.sessionFuture = self.sessionExecutor.submit(self.sessionWriter.Write, self.sessionPath, data, **writeOptions)
        self.sessionSignature = signature
        return True

    def RestoreSession(self, recoveryPath = None):
        primary = recoveryPath is None
        recoveryPath = self.sessionPath if primary else recoveryPath
        backupPath = self.sessionPath.with_name(self.sessionPath.name + ".bak")
        if not recoveryPath.exists():
            if primary and backupPath.exists():
                self.RestoreSession(backupPath)
            return
        try:
            if recoveryPath.stat().st_size > projectFileLimit:
                raise ValueError("The recovery file is too large.")
            data = json.loads(recoveryPath.read_text(encoding = "utf-8"))
            if data["format"] != "Planner Session" or type(data["version"]) is not int or data["version"] != 1:
                raise ValueError("Unsupported session recovery format.")
            # Recovery preserves editable scene data even when a placement is obstructed.
            # Interactive placement and ordinary project imports retain strict validation.
            decoded = DecodeProject(data["project"], self.viewport.localFurnishingDefinitions if self.viewport.projectFurnishingDefinitions
                                    else self.viewport.furnishingDefinitions, validatePlacement = False)
            build = data.get("buildSettings", {"wallWidths": self.viewport.wallPresetWidths,
                                               "openingSizes": self.viewport.openingDefaultSizes})
            if not isinstance(build["wallWidths"], list) or len(build["wallWidths"]) != 4:
                raise ValueError("Invalid recovered wall presets.")
            wallWidths = [ValidateNumber(width, minimum = .1, maximum = 10000) for width in build["wallWidths"]]
            openingSizes = {key: ValidateNumber(build["openingSizes"].get(key, self.viewport.openingDefaultSizes[key]) if key in ("BarnDoor", "BifoldDoor", "CasementWindow", "AwningWindow", "DoubleCasementWindow", "SwingingDoor", "DoubleDoor") else build["openingSizes"][key], minimum = .1, maximum = 10000)
                            for key in self.viewport.openingDefaultSizes}
            grid = data.get("viewportSettings", self.viewport.gridIntensities)
            grid = {key: ValidateNumber(grid[key], minimum = 0, maximum = 2 if key == "overall" else 1)
                    for key in self.viewport.gridIntensities}
            if "viewportSettings" in data and data.get("gridIntensityVersion", 1) == 1:
                # Older checkpoints stored opacity multipliers over dim grid colors.
                grid = {key: round(value * gridIntensityDefaults[key], 3) for key, value in grid.items()}
            path = data["projectPath"]
            if path is not None and not isinstance(path, str):
                raise ValueError("Invalid recovered project filename.")
            savedScene, savedSettings = bytes.fromhex(data["savedScene"]), bytes.fromhex(data["savedSettings"])
            if len(savedScene) != 32 or len(savedSettings) != 32:
                raise ValueError("Invalid recovered saved state.")
            ui = data["ui"]
            recoveredObjects = {obj.objectId: obj for obj in decoded[0] + decoded[1] + decoded[2] + decoded[7]}
            ValidateEditorUi(ui, recovery = True, tabCount = self.sidebarTabs.count(), objectsById = recoveredObjects)
            restoreHeight = ui.get("propertiesRestoreHeight")
            geometry = QtCore.QByteArray.fromBase64(ui["geometry"].encode("ascii"))
        except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError, RecursionError, AttributeError) as error:
            warnings.warn(f"Planner could not restore its previous session: {error}", RuntimeWarning)
            timestamp = QtCore.QDateTime.currentDateTimeUtc().toString("yyyyMMdd-HHmmss-zzz")
            failedPath = recoveryPath.with_name(recoveryPath.name + ".failed-" + timestamp)
            try:
                recoveryPath.replace(failedPath)
            except OSError as preservationError:
                self.sessionRecoveryBlocked = True
                warnings.warn(f"Planner could not preserve the failed recovery file: {preservationError}", RuntimeWarning)
            if primary and backupPath.exists():
                self.RestoreSession(backupPath)
            self.viewport.ShowClipboardError("Previous recovery failed; its file has been preserved."
                                            if not self.sessionRecoveryBlocked else
                                            "Recovery failed. Its file could not be preserved; automatic saving is paused.")
            return
        if "buildSettings" not in data["project"]["settings"]:
            decoded[5]["buildSettings"].update(wallWidths = wallWidths, openingSizes = openingSizes)
        if "viewportSettings" not in data["project"]["settings"]:
            decoded[5]["viewportSettings"] = grid
        self.ApplyProject(decoded, Path(path) if path else None)
        recovery = data.get("projectRecovery")
        if (path is None and isinstance(recovery, dict) and isinstance(recovery.get("source"), str)
                and isinstance(recovery.get("backup"), str)):
            self.recoverySourcePath = Path(recovery["source"])
            self.recoveryBackupPath = Path(recovery["backup"])
        self.savedSceneSignature, self.savedSettingsSignature = savedScene, savedSettings
        self.RefreshProjectDirty()
        self.restoreGeometry(geometry)
        if "size" in ui and not self.isMaximized() and not self.isFullScreen():
            self.resize(*ui["size"])
        if "maximized" in ui:
            state = self.windowState() & ~QtCore.Qt.WindowState.WindowMinimized
            if ui["maximized"]:
                state |= QtCore.Qt.WindowState.WindowMaximized
            else:
                state &= ~QtCore.Qt.WindowState.WindowMaximized
            if state != self.windowState():
                self.setWindowState(state)
        self.mainSplitter.setSizes(ui["mainSplitter"])
        self.SetPropertiesCollapsed(ui.get("propertiesCollapsed", False), rememberHeight = False)
        self.propertiesRestoreHeight = restoreHeight
        self.SetPropertiesSplitterSizes(ui["propertiesSplitter"])
        self.sidebarTabs.setCurrentIndex(ui["tab"])
        for name, item in self.visibilityItems.items():
            item.setExpanded(ui["expanded"].get(name, True))
        v = self.viewport
        objects = {obj.objectId: obj for obj in v.walls + v.windows + v.furnishings + v.labels}
        v.SetSelection([(objects[objectId], index) for objectId, index in ui["selection"] if objectId in objects])
        rotation = objects.get(ui.get("rotationObject"))
        v.furnishingRotationObject = rotation if any(rotation is obj for obj in v.furnishings + v.labels) else None
        areas = self.findChildren(QtWidgets.QScrollArea)

        def RestoreLayout():
            # Layout dimensions settle after the restored window is shown.
            self.mainSplitter.setSizes(ui["mainSplitter"])
            self.SetPropertiesSplitterSizes(ui["propertiesSplitter"])
            for area, value in zip(areas, ui["scroll"]):
                area.verticalScrollBar().setValue(value)
            self.visibilityTree.verticalScrollBar().setValue(ui.get("treeScroll", 0))

        QtCore.QTimer.singleShot(0, self, RestoreLayout)
        self.sessionRestored = True
        locateEntries = self.RecoveryObjectEntries()
        if locateEntries:
            self.ShowAppMessage("Missing Assets", "The restored session contains unavailable furnishing assets.", "warning",
                                informativeText = "Restore the assets or remove their references. Click an entry to locate affected objects.",
                                locateEntries = locateEntries)
        if not v.OpeningsValid():
            v.ShowClipboardError("Session recovered with invalid placements. Move or remove obstructing objects to resolve them.")
