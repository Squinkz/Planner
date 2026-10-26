"""File operations and event-driven saved/dirty project tracking."""
import hashlib
import copy
import json
import os
import uuid
from pathlib import Path
from PySide6 import QtCore, QtWidgets
from planner_app.project_codec import DecodeProject, EncodeScene, EncodeUsedFurnishings, projectFileLimit, ReadProjectBytes
from planner_app.project_history import EncodeEdit
from planner_app.paths import appDirectory
from planner_app.geometry_recovery import GeometryLoadCancelled
from planner_app.models import Furnishing, RoomLabel
from planner_app.furnishing_assets import FurnishingAssetProblems


class ProjectsMixin:
    def InitializeProject(self):
        self.projectPath = None
        self.recoverySourcePath = None
        self.recoveryBackupPath = None
        self.projectDirty = False
        self.projectLoading = False
        self.projectSceneNeedsCheck = True
        self.projectTimer = QtCore.QTimer(self)
        self.projectTimer.setSingleShot(True)
        self.projectTimer.timeout.connect(self.RefreshProjectDirty)
        self.defaultProjectData = self.BuildProjectData(includeHistory = False)
        # Before the first show, splitter sizes reflect temporary widget bounds.
        # Preserve the authored layout proportions for factory startup instead.
        self.defaultProjectData["ui"]["mainSplitter"] = [948, 460]
        self.defaultProjectData["ui"]["propertiesSplitter"] = [600, 300]
        self.startupPath = Path(os.environ.get("PLANNER_STARTUP_PATH", str(appDirectory / "startup.plan")))
        self.startupRestored = False
        self.MarkProjectClean()
        self.viewport.sceneChanged.connect(self.ProjectSceneChanged)
        self.viewport.settingsChanged.connect(self.ProjectSettingsChanged)

    def ProjectSettings(self):
        v = self.viewport
        snap = {name: button.isChecked() for name, button in self.snapOptions.items()}
        settings = {"wallWidth": v.newWallWidth, "wallMaterial": v.newWallMaterial, "wallShape": v.wallShape,
                "doorType": v.openingPlacementTypes["Door"][v.openingPlacementIndices["Door"]].__name__,
                "windowType": v.openingPlacementTypes["Window"][v.openingPlacementIndices["Window"]].__name__,
                "snapEnabled": self.snapButton.isChecked() and any(snap.values()), "snap": snap,
                "connectedVertices": v.connectedVerticesEnabled, "connectedObjects": v.connectedObjectsEnabled,
                "groupMode": v.groupModeEnabled, "localTransforms": v.localTransforms, "visibility": dict(v.visibility),
                "ignoredPotentialIssues": list(v.ignoredPotentialIssues),
                "showGrid": v.showGrid, "showMeasurements": v.showMeasurements, "measurementPrecision": v.measurementPrecision,
                "buildSettings": {"wallWidths": list(v.wallPresetWidths), "openingSizes": dict(v.openingDefaultSizes),
                                  "miscSizes": dict(v.miscDefaultSizes),
                                  **({"imperialSizes": dict(v.imperialDefaultSizes)} if v.imperialDefaultSizes else {})},
                "viewportSettings": dict(v.gridIntensities), "lineworkSettings": dict(v.lineworkSettings), "measurementSettings": dict(v.measurementSettings),
                "measurementVisibility": dict(v.measurementVisibility),
                "collisionSettings": dict(v.collisionSettings),
                "railingSpacings": dict(v.railingSpacings), "stairStepSizes": dict(v.stairStepSizes), "unitsMode": v.unitsMode}
        if self.referenceImage.state is not None:
            settings["referenceImage"] = self.referenceImage.Snapshot()
        if v.imperialAutoSizes:
            settings["imperialAutoSizes"] = {kind: dict(values) for kind, values in v.imperialAutoSizes.items()}
        if self.exportPanel.projectView is not None:
            settings.update(copy.deepcopy(self.exportPanel.projectView))
            settings.pop("canvasTheme", None)
        if self.exportPanel.overrides:
            settings["exportSettings"] = copy.deepcopy(self.exportPanel.overrides)
        if self.exportPanel.exportFolder:
            settings["exportFolder"] = self.exportPanel.exportFolder
        if self.exportPanel.exportFileName:
            settings["exportFileName"] = self.exportPanel.exportFileName
        mode = self.exportPanel.projectView["wallMeasurementMode"] if self.exportPanel.projectView is not None else v.wallMeasurementMode
        if mode != "All":
            settings["wallMeasurementMode"] = mode
        else:
            settings.pop("wallMeasurementMode", None)
        reference = self.exportPanel.projectView["wallMeasurementReference"] if self.exportPanel.projectView is not None else v.wallMeasurementReference
        if reference != "Wall faces":
            settings["wallMeasurementReference"] = reference
        else:
            settings.pop("wallMeasurementReference", None)
        return settings

    def ProjectUiState(self):
        return {"mainSplitter": self.savedSplitterSizes if self.viewportOnlyMode else self.mainSplitter.sizes(),
                "propertiesSplitter": self.propertiesExportSizes if self.propertiesExportSizes is not None else self.sidebarContentSplitter.sizes(),
                "propertiesCollapsed": self.propertiesCollapsed, "propertiesRestoreHeight": self.propertiesRestoreHeight,
                "exportSections": {name: button.isChecked() for name, button in self.exportPanel.sectionButtons.items()}}

    def ProjectHistory(self):
        # Cache keys must not keep pruned edits or deleted models alive.
        key = (tuple(edit.token for edit in self.viewport.undoHistory),
               tuple(edit.token for edit in self.viewport.redoHistory))
        if getattr(self, "encodedHistoryKey", None) != key:
            self.encodedHistory = {"format": "Planner Changes", "version": 1,
                                   "undo": [EncodeEdit(edit) for edit in self.viewport.undoHistory],
                                   "redo": [EncodeEdit(edit) for edit in self.viewport.redoHistory]}
            self.encodedHistoryKey = key
        return self.encodedHistory

    def BuildProjectData(self, includeHistory = True):
        pan = self.exportPanel.projectPanOffset if self.exportPanel.projectPanOffset is not None else self.viewport.panOffset
        data = {"format": "Planner Project", "version": 1, "scene": EncodeScene(self.viewport),
                "settings": self.ProjectSettings(),
                "view": {"zoom": self.exportPanel.projectZoom if self.exportPanel.projectZoom is not None else self.viewport.zoom,
                         "pan": [pan.x(), pan.y()]},
                "ui": self.ProjectUiState()}
        if includeHistory:
            data["history"] = self.ProjectHistory()
        embedded = EncodeUsedFurnishings(self.viewport, includeHistory = includeHistory)
        if embedded:
            data["furnishingDefinitions"] = embedded
        return data

    def LoadStartupProject(self):
        self.startupRestored = False
        data = self.defaultProjectData
        if self.startupPath.exists():
            try:
                originalBytes = ReadProjectBytes(self.startupPath)
                candidate = json.loads(originalBytes.decode("utf-8-sig"))
                from planner_app.project_recovery import RecoverProject
                decoded, repairs = RecoverProject(candidate, self.viewport.localFurnishingDefinitions if self.viewport.projectFurnishingDefinitions
                                                 else self.viewport.furnishingDefinitions, self.defaultProjectData, self.ShowGeometryIssue)
                if originalBytes.startswith(b"\xef\xbb\xbf"):
                    repairs.insert(0, "Accepted UTF-8 text containing a byte-order mark.")
                backupPath = self.BackupProjectForRecovery(self.startupPath, originalBytes) if repairs else None
            except GeometryLoadCancelled:
                return False
            except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError, RecursionError):
                self.viewport.ShowClipboardError("Startup file could not be loaded. Using factory defaults.")
            else:
                decoded[5].pop("history", None)
                self.ApplyProject(decoded, None)
                if repairs:
                    self.ReportRecoveredProject(self.startupPath, backupPath, repairs)
                self.startupRestored = True
                return True
        self.ApplyProject(DecodeProject(data, self.viewport.localFurnishingDefinitions if self.viewport.projectFurnishingDefinitions
                                       else self.viewport.furnishingDefinitions), None)
        return True

    def SaveStartupFile(self):
        choice = self.ShowAppMessage("Save Startup File",
                    "Use the current scene as the default for new projects?", "warning",
                    informativeText = "This will replace the startup file with the current scene, settings, and panel layout.",
                    standardButtons = QtWidgets.QMessageBox.StandardButton.Save | QtWidgets.QMessageBox.StandardButton.Cancel,
                    defaultButton = QtWidgets.QMessageBox.StandardButton.Cancel,
                    buttonLabels = {QtWidgets.QMessageBox.StandardButton.Save: "Save startup file"})
        if choice != QtWidgets.QMessageBox.StandardButton.Save:
            return False
        self.FinishProjectInteraction()
        self.viewport.EnsureObjectIds()
        from .session import WriteSessionFile
        error = WriteSessionFile(self.startupPath, self.BuildProjectData(includeHistory = False))
        if error:
            self.ShowAppMessage("Cannot Save Startup File", "Could not save startup.plan.", "error", informativeText = error)
            return False
        self.viewport.ShowClipboardError("Startup file saved.")
        return True

    def ProjectSceneChanged(self):
        if self.projectLoading:
            return
        self.projectSceneNeedsCheck = True
        self.projectTimer.start(0)

    def ProjectSettingsChanged(self):
        if not self.projectLoading:
            self.exportPanel.RecordExportHistory()
            self.exportPanel.CaptureProjectChanges()
            self.projectTimer.start(0)

    def RefreshProjectDirty(self):
        if self.projectLoading:
            return
        if self.projectSceneNeedsCheck:
            self.projectSceneData = EncodeScene(self.viewport)
            scene = json.dumps(self.projectSceneData, sort_keys = True, separators = (",", ":"), allow_nan = False)
            self.projectSceneSignature = hashlib.sha256(scene.encode("utf-8")).digest()
            self.projectSceneNeedsCheck = False
        settings = json.dumps(self.ProjectSettings(), sort_keys = True, separators = (",", ":"), allow_nan = False)
        self.projectSettingsSignature = hashlib.sha256(settings.encode("utf-8")).digest()
        self.projectDirty = (self.projectSceneSignature != self.savedSceneSignature or
                             self.projectSettingsSignature != self.savedSettingsSignature)
        name = self.projectPath.stem if self.projectPath is not None else (
            self.recoverySourcePath.stem + " (Recovered)" if self.recoverySourcePath is not None else "New Project")
        self.setWindowTitle(f"{name}{'*' if self.projectDirty else ''} - Planner")
        if hasattr(self, "menuButtons") and "Revert" in self.menuButtons:
            self.menuButtons["Revert"].setEnabled(self.projectPath is not None)
        if hasattr(self, "sessionTimer") and not self.sessionTimer.isActive():
            self.sessionTimer.start(500)

    def MarkProjectClean(self):
        self.projectTimer.stop()
        self.projectSceneNeedsCheck = True
        # Compare immutable signatures, not mutable scene objects or undo indices.
        self.savedSceneSignature = self.savedSettingsSignature = None
        self.RefreshProjectDirty()
        self.savedSceneSignature = self.projectSceneSignature
        self.savedSettingsSignature = self.projectSettingsSignature
        self.RefreshProjectDirty()

    def FinishProjectInteraction(self):
        self.referenceImage.CancelDrag()
        focused = QtWidgets.QApplication.focusWidget()
        propertyFields = list(self.propertyFields.values()) + list(self.referenceImage.fields.values())
        propertyFields += [self.exportPanel.folderField, self.exportPanel.fileNameField]
        if focused is not None and any(field is focused or field.isAncestorOf(focused)
                                       for field in propertyFields):
            # Focus loss commits text even when keyboard tracking is disabled.
            focused.clearFocus()
        self.referenceImage.FinishPropertyDrag(True)
        if self.propertyDragBefore is not None:
            self.FinishPropertyDrag(True)
            for field in self.propertyFields.values():
                field.dragging = False
                field.pressPosition = None
                field.lineEdit().unsetCursor()
        self.viewport.CancelInteraction()

    def ConfirmProjectReplacement(self):
        self.FinishProjectInteraction()
        self.RefreshProjectDirty()
        if not self.projectDirty:
            return True
        name = self.projectPath.stem if self.projectPath is not None else (
            self.recoverySourcePath.stem + " (Recovered)" if self.recoverySourcePath is not None else "New Project")
        choice = self.ShowAppMessage("Unsaved Project", f"Save changes to {name} before continuing?", "warning",
                    standardButtons = QtWidgets.QMessageBox.StandardButton.Save | QtWidgets.QMessageBox.StandardButton.Discard |
                    QtWidgets.QMessageBox.StandardButton.Cancel, defaultButton = QtWidgets.QMessageBox.StandardButton.Save)
        if choice == QtWidgets.QMessageBox.StandardButton.Save:
            return self.SaveProject()
        return choice == QtWidgets.QMessageBox.StandardButton.Discard

    def NewProject(self):
        if not self.ConfirmProjectReplacement():
            return False
        previousData = self.BuildProjectData()
        previousPath = self.projectPath
        previousSaved = self.savedSceneSignature, self.savedSettingsSignature
        previousRecovery = self.recoverySourcePath, self.recoveryBackupPath
        definitions = self.viewport.localFurnishingDefinitions if self.viewport.projectFurnishingDefinitions else self.viewport.furnishingDefinitions
        emptyProject = DecodeProject(self.defaultProjectData, definitions)
        emptyProject[5].pop("editorUi", None)
        self.ApplyProject(emptyProject, None)
        if self.LoadStartupProject():
            return True
        self.ApplyProject(DecodeProject(previousData, definitions), previousPath)
        self.savedSceneSignature, self.savedSettingsSignature = previousSaved
        self.recoverySourcePath, self.recoveryBackupPath = previousRecovery
        self.RefreshProjectDirty()
        return False

    def CloseProject(self):
        if not self.ConfirmProjectReplacement():
            return False
        settings = self.ProjectSettings()
        defaults = self.defaultProjectData
        for name in ("visibility", "showMeasurements", "measurementVisibility"):
            settings[name] = copy.deepcopy(defaults["settings"][name])
        settings.pop("referenceImage", None)
        settings.pop("exportSettings", None)
        settings.pop("exportFolder", None)
        settings.pop("exportFileName", None)
        settings.pop("ignoredPotentialIssues", None)
        data = {"format": "Planner Project", "version": 1,
                "scene": copy.deepcopy(defaults["scene"]), "settings": settings,
                "view": copy.deepcopy(defaults["view"]), "ui": self.ProjectUiState()}
        definitions = self.viewport.localFurnishingDefinitions if self.viewport.projectFurnishingDefinitions else self.viewport.furnishingDefinitions
        self.ApplyProject(DecodeProject(data, definitions), None)
        return True

    def BackupProjectForRecovery(self, path, originalBytes):
        recoveryFolder = self.sessionPath.parent / "project-recovery"
        recoveryFolder.mkdir(parents = True, exist_ok = True)
        timestamp = QtCore.QDateTime.currentDateTimeUtc().toString("yyyyMMdd-HHmmss-zzz")
        backupPath = recoveryFolder / f"{path.stem}-{timestamp}-{uuid.uuid4().hex[:8]}.plan"
        with backupPath.open("xb") as backup:
            backup.write(originalBytes)
        return backupPath

    def ReportRecoveredProject(self, path, backupPath, repairs):
        self.recoverySourcePath, self.recoveryBackupPath = path, backupPath
        self.savedSceneSignature = self.savedSettingsSignature = bytes(32)
        self.RefreshProjectDirty()
        missingAssets = [repair for repair in repairs if repair.startswith(("Missing furnishing ", "Missing compound child ", "Unavailable furnishing artwork "))]
        locateEntries = self.RecoveryObjectEntries()
        missingSummary = ""
        if missingAssets:
            missingSummary = "\n\nMissing assets when opened:\n" + "\n".join(missingAssets[:3])
            if len(missingAssets) > 3:
                missingSummary += "\nSee Details for other missing assets."
            missingSummary += "\nMissing assets will be reported again until their references are removed or their definitions are restored."
        self.ShowAppMessage("Project Recovered", f"Opened a recovered copy of {path.name}.", "warning",
                            informativeText = f"{len(repairs)} recovery actions were taken. Save to keep the repairs. You can replace the original file or choose another name. The recovery label clears after saving.{missingSummary}\n\nOriginal backup:\n{backupPath}",
                            detailedText = "\n".join("• " + repair for repair in repairs), locateEntries = locateEntries)

    def RecoveryObjectEntries(self):
        locateEntries = {}
        for obj in self.viewport.furnishings:
            # Built-in annotations share the furnishing collection but do not
            # resolve their graphics through the furnishing catalog.
            if type(obj) is not Furnishing:
                continue
            missingKeys = FurnishingAssetProblems(getattr(obj, "definitionKey", obj.definition["key"]),
                                                  self.viewport.furnishingDefinitions, obj.definition)
            for key in sorted(missingKeys):
                locateEntries.setdefault(key, []).append(obj)
        return locateEntries

    def LocateRecoveryObjects(self, objects, expandGroups = True):
        v = self.viewport
        self.exportPanel.SetActive(False)
        if self.referenceImage.active:
            self.referenceImage.Hide()
        v.CancelInteraction()
        sceneObjects = v.walls + v.windows + v.furnishings + v.labels
        objects = list({id(obj): obj for obj in objects if any(obj is candidate for candidate in sceneObjects)}.values())
        if not objects:
            return
        selectedIds = {id(obj) for obj in objects}
        if selectedIds & v.hiddenObjectIds:
            before = v.CaptureState()
            v.hiddenObjects = [obj for obj in v.hiddenObjects if id(obj) not in selectedIds]
            v.hiddenObjectIds = {id(obj) for obj in v.hiddenObjects}
            v.RecordEdit(before)
        for category in {v.ObjectVisibilityCategory(obj) for obj in objects}:
            node = self.visibilityItems[category]
            blocker = QtCore.QSignalBlocker(self.visibilityTree)
            node.setCheckState(0, QtCore.Qt.CheckState.Checked)
            del blocker
            self.SetVisibility(node, 0)
        groupMode = v.groupModeEnabled
        if not expandGroups:
            v.groupModeEnabled = False
        try:
            v.SetSelection([(obj, None) for obj in objects])
        finally:
            v.groupModeEnabled = groupMode
        selected = [obj for obj, index in v.SelectionEntries()]
        if not selected:
            return
        bounds = v.ObjectFootprint(selected[0])[0]
        for obj in selected[1:]:
            bounds = bounds.united(v.ObjectFootprint(obj)[0])
        drawing = v.DrawingRect().adjusted(48, 48, -48, -48)
        v.zoom = max(.02, min(100.0, drawing.width() / (max(6000, bounds.width() * 3) * v.basePixelsPerMillimeter),
                            drawing.height() / (max(6000, bounds.height() * 3) * v.basePixelsPerMillimeter)))
        scale = v.basePixelsPerMillimeter * v.zoom
        center = bounds.center()
        v.panOffset = QtCore.QPointF(-center.x() * scale, center.y() * scale)
        v.update()
        v.setFocus()

    def OpenProject(self, path = None):
        if path is None:
            filename, chosenFilter = QtWidgets.QFileDialog.getOpenFileName(self, "Open Project", str(self.BrowseDirectory()),
                                                                          "Planner Projects (*.plan);;All Files (*)")
            if not filename:
                return False
            path = filename
        path = Path(path).resolve()
        self.RememberBrowseFolder(path)
        if not self.ConfirmProjectReplacement():
            return False
        previousData = self.BuildProjectData()
        previousPath = self.projectPath
        previousSaved = self.savedSceneSignature, self.savedSettingsSignature
        previousRecovery = self.recoverySourcePath, self.recoveryBackupPath
        definitions = self.viewport.localFurnishingDefinitions if self.viewport.projectFurnishingDefinitions else self.viewport.furnishingDefinitions

        def RestorePreviousProject():
            try:
                self.ApplyProject(DecodeProject(previousData, definitions), previousPath)
                self.savedSceneSignature, self.savedSettingsSignature = previousSaved
                self.recoverySourcePath, self.recoveryBackupPath = previousRecovery
                self.RefreshProjectDirty()
            except Exception as restoreError:
                self.ShowAppMessage("Project Restore Failed", "The previous project could not be restored.", "error",
                                    informativeText = str(restoreError))

        try:
            emptyProject = DecodeProject(self.defaultProjectData, definitions)
            emptyProject[5].pop("editorUi", None)
            self.ApplyProject(emptyProject, None)
        except Exception as error:
            self.ShowAppMessage("Cannot Open Project", "Could not close the current project before opening the new one.", "error",
                                informativeText = str(error))
            RestorePreviousProject()
            return False
        try:
            originalBytes = ReadProjectBytes(path)
            data = json.loads(originalBytes.decode("utf-8-sig"))
            from planner_app.project_recovery import RecoverProject
            decoded, repairs = RecoverProject(data, definitions, self.defaultProjectData, self.ShowGeometryIssue)
            if originalBytes.startswith(b"\xef\xbb\xbf"):
                repairs.insert(0, "Accepted UTF-8 text containing a byte-order mark.")
        except GeometryLoadCancelled:
            RestorePreviousProject()
            return False
        except (OSError, ValueError, KeyError, TypeError, IndexError, OverflowError, RecursionError) as error:
            self.ShowAppMessage("Cannot Open Project", f"Could not open {path.name}.", "error", informativeText = str(error))
            RestorePreviousProject()
            return False
        backupPath = None
        if repairs:
            try:
                backupPath = self.BackupProjectForRecovery(path, originalBytes)
            except OSError as error:
                self.ShowAppMessage("Cannot Preserve Project", "The original project could not be backed up.", "error", informativeText = str(error))
                RestorePreviousProject()
                return False
        try:
            self.ApplyProject(decoded, None if repairs else path)
        except Exception as error:
            self.ShowAppMessage("Cannot Open Project", f"Could not apply {path.name}. The previous project will be restored.", "error", informativeText = str(error))
            RestorePreviousProject()
            return False
        if repairs:
            self.ReportRecoveredProject(path, backupPath, repairs)
        self.RememberRecentProject(path)
        return True

    def RevertProject(self):
        if self.projectPath is None:
            return False
        self.RefreshProjectDirty()
        if not self.projectDirty:
            return True
        return self.OpenProject(self.projectPath)

    def SaveProject(self, path = None):
        if path is None and self.projectPath is None:
            return self.SaveProjectAs()
        path = Path(path).resolve() if path is not None else self.projectPath
        self.FinishProjectInteraction()
        try:
            self.viewport.EnsureObjectIds()
            data = json.dumps(self.BuildProjectData(), ensure_ascii = False, separators = (",", ":"), allow_nan = False).encode("utf-8")
            if len(data) > projectFileLimit:
                raise ValueError("The project, including undo history, exceeds the 64 MB file limit.")
            file = QtCore.QSaveFile(str(path))
            if not file.open(QtCore.QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(file.errorString())
            if file.write(data) != len(data):
                message = file.errorString()
                file.cancelWriting()
                raise OSError(message)
            if not file.commit():
                raise OSError(file.errorString())
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.ShowAppMessage("Cannot Save Project", f"Could not save {path.name}.", "error", informativeText = str(error))
            return False
        self.projectPath = path
        self.recoverySourcePath = self.recoveryBackupPath = None
        self.RememberRecentProject(path)
        self.exportPanel.PopulatePath()
        self.MarkProjectClean()
        return True

    def SaveProjectAs(self, path = None):
        if path is None:
            suggestedName = self.projectPath.name if self.projectPath is not None else "New Project.plan"
            suggested = self.BrowseDirectory() / suggestedName
            if self.projectPath is None and self.recoverySourcePath is not None:
                suggested = self.recoverySourcePath
            filename, chosenFilter = QtWidgets.QFileDialog.getSaveFileName(self, "Save Project As", str(suggested),
                                                                          "Planner Projects (*.plan);;All Files (*)")
            if not filename:
                return False
            path = filename
        path = Path(path)
        if not path.suffix:
            path = path.with_suffix(".plan")
        self.RememberBrowseFolder(path)
        return self.SaveProject(path)

    def ApplyProject(self, decoded, path):
        recoveryWindow = getattr(self, "recoveryWindow", None)
        if recoveryWindow is not None:
            recoveryWindow.close()
        if getattr(self, "furnishingQuickSearch", None) is not None:
            self.furnishingQuickSearch.hide()
        walls, windows, furnishings, groups, hidden, settings, view, labels = decoded
        self.projectLoading = True
        self.recoverySourcePath = self.recoveryBackupPath = None
        try:
            self.exportPanel.SetActive(False)
            self.exportPanel.exportZoom = self.exportPanel.exportPanOffset = None
            self.exportPanel.overrides = {}
            self.SetViewportOnlyMode(False)
            v = self.viewport
            v.CancelInteraction()
            if v.projectFurnishingDefinitions or settings.get("embeddedFurnishings"):
                if not v.projectFurnishingDefinitions:
                    v.localFurnishingDefinitions = dict(v.furnishingDefinitions)
                v.projectFurnishingDefinitions = dict(settings.get("embeddedFurnishings", {}))
                v.furnishingDefinitions = {**v.localFurnishingDefinitions, **v.projectFurnishingDefinitions}
                self.RefreshFurnishingRenderers()
                self.BuildFurnishTab(refresh = True)
            v.walls, v.windows, v.furnishings = walls, windows, furnishings
            v.ignoredPotentialIssues = list(settings["ignoredPotentialIssues"])
            v.labels = labels
            v.objectGroups, v.hiddenObjects = groups, hidden
            v.hiddenObjectIds = {id(obj) for obj in hidden}
            v.undoHistory.clear()
            v.redoHistory.clear()
            v.lastInteractionPosition = v.hoverPosition = None
            v.EnsureObjectIds()
            v.zoom, v.panOffset = view["zoom"], QtCore.QPointF(view["pan"])
            v.newWallWidth, v.newWallMaterial = settings["wallWidth"], settings["wallMaterial"]
            v.wallShape = settings["wallShape"]
            self.wallToolButtons[v.wallShape].setChecked(True)
            v.wallPresetWidths = list(settings["buildSettings"]["wallWidths"])
            v.openingDefaultSizes = dict(settings["buildSettings"]["openingSizes"])
            v.miscDefaultSizes = dict(settings["buildSettings"]["miscSizes"])
            v.imperialDefaultSizes = dict(settings["buildSettings"].get("imperialSizes", {}))
            self.SetLinework(settings["lineworkSettings"], notify = False)
            v.gridIntensities = dict(settings["viewportSettings"])
            v.measurementSettings = dict(settings["measurementSettings"])
            v.wallMeasurementMode = settings["wallMeasurementMode"]
            v.wallMeasurementReference = settings["wallMeasurementReference"]
            v.collisionSettings = dict(settings["collisionSettings"])
            v.stairStepSizes = dict(settings["stairStepSizes"])
            v.railingSpacings = dict(settings["railingSpacings"])
            v.imperialAutoSizes = {kind: dict(values) for kind, values in settings["imperialAutoSizes"].items()}
            v.autoSizingUnitsMode = None
            v.unitsMode = settings["unitsMode"]
            self.referenceImage.Restore(settings.get("referenceImage"))
            v.measurementPrecision = settings["measurementPrecision"]
            self.UpdateFurnishingSearch()
            self.wallWidthSelector.unitsMode = v.unitsMode
            v.EnsureObjectIds()
            self.wallWidthSelector.widths = tuple(v.DefaultPlacementSize(index) / 10 for index in range(4))
            self.wallWidthSelector.update()
            if self.settingsWindow is not None:
                panel = self.settingsWindow
                precisionBlocker = QtCore.QSignalBlocker(panel.precisionField)
                panel.precisionField.setCurrentText(v.measurementPrecision)
                del precisionBlocker
                panel.RefreshSizeUnits()
                for key, value in v.gridIntensities.items():
                    panel.SetGridIntensity(key, value)
                for key, value in v.measurementSettings.items():
                    panel.SetMeasurementMode(key, value)
                panel.RefreshStepSizing()
                panel.RefreshCollisions()
                blocker = QtCore.QSignalBlocker(panel.unitsField)
                panel.unitsField.setCurrentText(v.unitsMode)
                del blocker
                # Field synchronization can update the active preset; preserve the project's exact width.
                v.newWallWidth = settings["wallWidth"]
            v.showGrid, v.showMeasurements = settings["showGrid"], settings["showMeasurements"]
            v.measurementVisibility = dict(settings["measurementVisibility"])
            if self.settingsWindow is not None:
                self.settingsWindow.RefreshMeasurementVisibility()
            self.altHeld = False
            widgets = [self.wallWidthSelector.slider, self.newWallMaterialField, self.snapButton, self.groupModeButton,
                       self.visibilityTree] + list(self.snapOptions.values()) + list(self.connectedOptions.values())
            blockers = [QtCore.QSignalBlocker(widget) for widget in widgets]
            self.wallWidthSelector.slider.setValue(min(range(4), key = lambda index:
                abs(self.wallWidthSelector.widths[index] * 10 - settings["wallWidth"])))
            self.newWallMaterialField.setCurrentText(settings["wallMaterial"])
            v.snapEnabled = settings["snapEnabled"]
            self.snapButton.setChecked(settings["snapEnabled"])
            for name, button in self.snapOptions.items():
                button.setChecked(settings["snap"][name])
            self.SetSnapOptions()
            for name, key in (("vertices", "connectedVertices"), ("objects", "connectedObjects")):
                self.connectedOptions[name].setChecked(settings[key])
            self.SetConnectedOptions()
            v.groupModeEnabled = settings["groupMode"]
            self.groupModeButton.setChecked(settings["groupMode"])
            self.SetTransformOrientation(settings["localTransforms"], notify = False)
            for name, item in self.visibilityItems.items():
                item.setCheckState(0, QtCore.Qt.CheckState.Checked if settings["visibility"][name] else QtCore.Qt.CheckState.Unchecked)
            self.SetVisibility(None, 0)
            for mode, key in (("Door", "doorType"), ("Window", "windowType")):
                names = [cls.__name__ for cls in v.openingPlacementTypes[mode]]
                v.openingPlacementIndices[mode] = names.index(settings[key])
            del blockers
            v.SetSelection([])
            if any(isinstance(label, RoomLabel) for label in v.labels):
                v.roomDetection.Refresh(force = True)
            v.sceneRevision += 1
            v.sceneChanged.emit()
            self.RefreshOpeningToolHighlight(None)
            self.projectPath = path
            self.exportPanel.exportFolder = settings.get("exportFolder")
            self.exportPanel.exportFileName = settings.get("exportFileName")
            self.exportPanel.PopulatePath(force = True)
            history = settings.get("history", {"undo": [], "redo": []})
            v.undoHistory, v.redoHistory = history["undo"], history["redo"]
            ui = settings.get("editorUi")
            self.exportPanel.RestoreSectionStates(ui.get("exportSections", {}) if ui is not None else {})
            if ui is not None:
                self.mainSplitter.setSizes(ui["mainSplitter"])
                self.SetPropertiesCollapsed(ui["propertiesCollapsed"], rememberHeight = False)
                self.propertiesRestoreHeight = ui.get("propertiesRestoreHeight")
                self.SetPropertiesSplitterSizes(ui["propertiesSplitter"])
            self.exportPanel.overrides = settings.get("exportSettings", {})
            self.exportPanel.ResetExportHistory()
            self.exportPanel.SetActive(self.sidebarTabs.currentWidget() is self.exportPanel)
        finally:
            self.projectLoading = False
        self.MarkProjectClean()
        self.viewport.update()

    def closeEvent(self, event):
        if self.settingsWindow is not None:
            self.settingsWindow.close()
        self.FinishProjectInteraction()
        self.projectTimer.stop()
        self.RefreshProjectDirty()
        self.sessionTimer.stop()
        self.sessionPollTimer.stop()
        if not self.WriteSession(wait = True):
            self.sessionPollTimer.start()
            self.ShowAppMessage("Recovery Save Failed", "The current session could not be preserved.", kind = "error",
                                informativeText = (self.sessionError + "\n\n" if self.sessionError else "") +
                                "The application will remain open. Save the project with Save As, or retry closing after resolving the error.")
            event.ignore()
            return
        if self.sessionExecutor is not None:
            self.sessionExecutor.shutdown(wait = True)
        event.accept()
