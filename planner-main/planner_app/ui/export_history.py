"""Bounded, independent undo for export settings and drag gestures."""
import copy
from PySide6 import QtCore, QtWidgets
from planner_app.history_edits import RetainedBytes


class ExportHistoryMixin:
    def InitializeExportHistory(self):
        self.exportHistoryRestoring = False
        self.exportGestureBefore = None
        self.exportUndoHistory, self.exportRedoHistory = [], []
        self.exportHistoryByteBudget = 16 * 1024 * 1024
        self.exportHistoryState = self.ExportHistoryState()
        for slider in self.findChildren(QtWidgets.QSlider):
            slider.sliderPressed.connect(lambda slider = slider: self.BeginExportGesture(slider))
            slider.sliderReleased.connect(self.EndExportGesture)
        self.folderField.editingFinished.connect(self.FolderEdited)
        self.fileNameField.editingFinished.connect(self.FileNameEdited)

    def ExportHistoryState(self):
        return {"overrides": copy.deepcopy(self.overrides), "type": self.typeField.currentData(),
                "folder": self.folderField.text(), "exportFolder": self.exportFolder,
                "exportFileName": self.exportFileName,
                "filename": self.fileNameField.text(), "automaticPath": self.automaticPath}

    def ResetExportHistory(self):
        self.exportUndoHistory.clear()
        self.exportRedoHistory.clear()
        self.exportGestureBefore = None
        self.exportHistoryState = self.ExportHistoryState()

    def PruneExportHistory(self):
        # Count shared immutable logo strings once across adjacent snapshots.
        while self.exportUndoHistory and (len(self.exportUndoHistory) > 100 or
                RetainedBytes((self.exportUndoHistory, self.exportRedoHistory)) > self.exportHistoryByteBudget):
            self.exportUndoHistory.pop(0)

    def BeginExportGesture(self, control = None):
        if self.exportHistoryRestoring:
            return
        overlay = self.mainWindow.viewport.exportOverlay
        if self.exportGestureBefore is None:
            self.exportGestureBefore = self.ExportHistoryState()
            overlay.previewGesture = True
            overlay.compositeGesture = False
        # The application mouse filter can start the gesture before the
        # slider's pressed signal. Its later, explicit source must still count.
        if control is self.vignetteStrengthSlider or control in self.textureSliders.values():
            overlay.compositeGesture = True

    def EndExportGesture(self):
        self.mainWindow.viewport.exportOverlay.previewGesture = False
        self.mainWindow.viewport.exportOverlay.compositeGesture = False
        self.mainWindow.viewport.update()
        before = self.exportGestureBefore
        self.exportGestureBefore = None
        if before is None or self.exportHistoryRestoring or self.mainWindow.projectLoading:
            return
        after = self.ExportHistoryState()
        if before != after:
            pair = (before, after)
            self.exportUndoHistory.append(pair)
            self.exportRedoHistory.clear()
            self.PruneExportHistory()
            activity = getattr(self.mainWindow, "activityLog", None)
            if activity is not None:
                activity.ExportEdited(pair)
        self.exportHistoryState = after

    def RecordExportHistory(self):
        if self.exportHistoryRestoring or self.mainWindow.projectLoading:
            return
        after = self.ExportHistoryState()
        if self.exportGestureBefore is None and self.exportHistoryState != after:
            pair = (self.exportHistoryState, after)
            self.exportUndoHistory.append(pair)
            self.exportRedoHistory.clear()
            self.PruneExportHistory()
            activity = getattr(self.mainWindow, "activityLog", None)
            if activity is not None:
                activity.ExportEdited(pair)
        self.exportHistoryState = after

    def RestoreExportHistory(self, state):
        self.exportHistoryRestoring = True
        try:
            previousScale = self.overrides.get("architecturalScale", 100)
            previousMode = self.overrides.get("scaleMode")
            self.overrides = copy.deepcopy(state["overrides"])
            blocker = QtCore.QSignalBlocker(self.typeField)
            self.typeField.setCurrentIndex(self.typeField.findData(state["type"]))
            del blocker
            self.SetPathType(state["type"])
            self.folderField.setText(state["folder"])
            self.exportFolder = state["exportFolder"]
            self.exportFileName = state["exportFileName"]
            self.fileNameField.setText(state["filename"])
            self.automaticPath = state["automaticPath"]
            if self.projectView is not None:
                self.ApplyView(self.ResolvedView())
                overlay = self.mainWindow.viewport.exportOverlay
                overlay.scale = self.PreviewScalePerMeter()
                overlay.bounds = tuple(self.overrides.get("bounds", overlay.autoBounds))
                overlay.rulerKey = overlay.svgKey = None
                if previousMode in ("Architectural", "Print") and previousMode == self.overrides.get("scaleMode"):
                    self.UpdatePhysicalScaleView(previousScale)
            self.RefreshControls()
            self.exportHistoryState = self.ExportHistoryState()
            self.mainWindow.ProjectSettingsChanged()
            self.mainWindow.viewport.update()
        finally:
            self.exportHistoryRestoring = False

    def UndoExport(self):
        self.EndExportGesture()
        if self.exportUndoHistory:
            pair = self.exportUndoHistory.pop()
            self.RestoreExportHistory(pair[0])
            self.exportRedoHistory.append(pair)
            activity = getattr(self.mainWindow, "activityLog", None)
            if activity is not None:
                activity.Travel(pair, False, "Export")

    def RedoExport(self):
        self.EndExportGesture()
        if self.exportRedoHistory:
            pair = self.exportRedoHistory.pop()
            self.RestoreExportHistory(pair[1])
            self.exportUndoHistory.append(pair)
            activity = getattr(self.mainWindow, "activityLog", None)
            if activity is not None:
                activity.Travel(pair, True, "Export")
