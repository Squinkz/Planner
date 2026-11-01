"""Frozen GUI project/argument preparation before preview-scene reuse."""

from planner_app.ui.projects import *

from planner_app.ui.export_panel import *

class ReferenceProjectsMixin:
    def BuildProjectData(self, includeHistory = True, includeActivity = True):
        if includeActivity and self.activityLog.settingsTimer.isActive():
            self.activityLog.FlushSettings()
        pan = self.exportPanel.projectPanOffset if self.exportPanel.projectPanOffset is not None else self.viewport.panOffset
        data = {"format": "Planner Project", "version": 1, "scene": EncodeScene(self.viewport),
                "settings": self.ProjectSettings(),
                "view": {"zoom": self.exportPanel.projectZoom if self.exportPanel.projectZoom is not None else self.viewport.zoom,
                         "pan": [pan.x(), pan.y()]},
                "ui": self.ProjectUiState()}
        activity = self.activityLog.Encode() if includeActivity else None
        if activity is not None:
            data["activityLog"] = activity
        if includeHistory:
            data["history"] = self.ProjectHistory()
        embedded = EncodeUsedFurnishings(self.viewport, includeHistory = includeHistory)
        if embedded:
            data["furnishingDefinitions"] = embedded
        return data

class ReferencePanelMixin:
    def RenderArguments(self, outputFormat, preview = False, previewScene = False):
        main = self.mainWindow
        cachedVector = previewScene and outputFormat == "svg" and self.overrides.get("scaleMode") != "Print"

        # Use the unsaved scene and the effective export view, without changing

        # the application's theme. Preview and file output share this path.

        data = main.BuildProjectData(includeHistory = False, includeActivity = False)

        data["settings"].update(self.CaptureView())
        data["settings"]["autoSizingUnitsMode"] = main.viewport.autoSizingUnitsMode or main.viewport.unitsMode

        return dict(planPath = main.projectPath or Path("plan.plan"), scale = self.ScalePerMeter(),

                          bounds = (main.viewport.exportOverlay.vectorBounds or main.viewport.exportOverlay.bounds) if cachedVector else
                                   main.viewport.exportOverlay.PreviewBounds() if previewScene and self.overrides.get("scaleMode") == "Print" else main.viewport.exportOverlay.bounds,
                          ruler = not cachedVector and self.borderField.currentText() == "Ruler",

                          outputFormat = outputFormat, projectData = data, applyTheme = False, preview = preview, previewScene = previewScene,
                          furnishingDefinitions = main.viewport.furnishingDefinitions,
                          clipCache = main.viewport.exportOverlay.svgClipCache if previewScene else None,

                          border = "None" if cachedVector else self.borderField.currentText(), wallStyle = self.wallStyleField.currentText(),
                          solidObjects = self.solidObjectsField.isChecked(),
                          roomStyle = self.roomStyleField.currentText(), solidRooms = self.solidRoomsField.isChecked(),
                          gridOrigin = main.viewport.gridOrigin,

                          borderSize = self.overrides.get("borderSize", 28),

                          titleBlock = self.TitleBlockOptions(),
                          scaleBar = dict(self.overrides.get("scaleBar", {})),

                          texture = self.overrides.get("texture"), textureAngle = self.overrides.get("textureAngle", 0), textureSettings = self.TextureSettings(),

                          vignetteStrength = self.overrides.get("vignetteStrength", .125) if self.overrides.get("vignetteEnabled", False) else 0,

                          dpi = self.overrides.get("dpi", 300) if self.overrides.get("scaleMode") == "Print" or self.overrides.get("scaleMode") == "Architectural" and outputFormat == "png" else None,

                          architecturalScale = self.overrides.get("architecturalScale", 100) if self.overrides.get("scaleMode") in ("Architectural", "Print") else None)
