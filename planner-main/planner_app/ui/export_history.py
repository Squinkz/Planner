"""Bounded, independent undo for export settings and drag gestures."""
import copy
from PySide6 import QtCore, QtWidgets


class ExportHistoryMixin:
    def InitializeExportHistory(self):
        self.exportHistoryRestoring = False
        self.exportGestureBefore = None
        self.exportUndoHistory, self.exportRedoHistory = [], []
        self.exportHistoryState = self.ExportHistoryState()
        for slider in self.findChildren(QtWidgets.QSlider):
            slider.sliderPressed.connect(self.BeginExportGesture)
            slider.sliderReleased.connect(self.EndExportGesture)
        self.folderField.editingFinished.connect(self.PopulatePath)
        self.folderField.editingFinished.connect(self.RecordExportHistory)
        self.fileNameField.editingFinished.connect(self.FileNameEdited)

    def ExportHistoryState(self):
        return {"overrides": copy.deepcopy(self.overrides), "type": self.typeField.currentData(),
                "folder": self.folderField.text(), "filename": self.fileNameField.text(), "automaticPath": self.automaticPath}

    def ResetExportHistory(self):
        self.exportUndoHistory.clear()
        self.exportRedoHistory.clear()
        self.exportGestureBefore = None
        self.exportHistoryState = self.ExportHistoryState()

    def BeginExportGesture(self):
        if self.exportGestureBefore is None and not self.exportHistoryRestoring:
            self.exportGestureBefore = self.ExportHistoryState()

    def EndExportGesture(self):
        before = self.exportGestureBefore
        self.exportGestureBefore = None
        if before is None or self.exportHistoryRestoring or self.mainWindow.projectLoading:
            return
        after = self.ExportHistoryState()
        if before != after:
            self.exportUndoHistory.append((before, after))
            del self.exportUndoHistory[:-100]
            self.exportRedoHistory.clear()
        self.exportHistoryState = after

    def RecordExportHistory(self):
        if self.exportHistoryRestoring or self.mainWindow.projectLoading:
            return
        after = self.ExportHistoryState()
        if self.exportGestureBefore is None and self.exportHistoryState != after:
            self.exportUndoHistory.append((self.exportHistoryState, after))
            del self.exportUndoHistory[:-100]
            self.exportRedoHistory.clear()
        self.exportHistoryState = after

    def RestoreExportHistory(self, state):
        self.exportHistoryRestoring = True
        try:
            self.overrides = copy.deepcopy(state["overrides"])
            blocker = QtCore.QSignalBlocker(self.typeField)
            self.typeField.setCurrentIndex(self.typeField.findData(state["type"]))
            del blocker
            self.SetPathType(state["type"])
            self.folderField.setText(state["folder"])
            self.fileNameField.setText(state["filename"])
            self.automaticPath = state["automaticPath"]
            if self.projectView is not None:
                self.ApplyView(self.ResolvedView())
                overlay = self.mainWindow.viewport.exportOverlay
                overlay.scale = self.ScalePerMeter()
                overlay.bounds = tuple(self.overrides.get("bounds", overlay.autoBounds))
                overlay.rulerKey = overlay.svgKey = None
            self.RefreshControls()
            self.exportHistoryState = self.ExportHistoryState()
            self.mainWindow.ProjectSettingsChanged()
            self.mainWindow.viewport.update()
        finally:
            self.exportHistoryRestoring = False

    def UndoExport(self):
        self.EndExportGesture()
        if self.exportUndoHistory:
            before, after = self.exportUndoHistory.pop()
            self.RestoreExportHistory(before)
            self.exportRedoHistory.append((before, after))

    def RedoExport(self):
        self.EndExportGesture()
        if self.exportRedoHistory:
            before, after = self.exportRedoHistory.pop()
            self.RestoreExportHistory(after)
            self.exportUndoHistory.append((before, after))
