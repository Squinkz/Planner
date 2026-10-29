"""Refresh theme-dependent widget artwork and scene paint without rebuilding UI."""
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics import palette
from planner_app.graphics.icons import iconSources, pixmapSources
from planner_app.graphics.theme import ApplyApplicationTheme, BuildCanvasStyle, BuildWallBrush, WallPresetIcon, MaterialIcon, wallMaterials
from planner_app.graphics.furnishings import FurnishingRendererMap
from .widgets import FurnishingButton, WindowButton


class AppearanceMixin:
    def SetLinework(self, settings, notify = True):
        panel = getattr(self, "exportPanel", None)
        if notify and panel is not None and panel.projectView is not None and not panel.applying:
            panel.EditProjectSettings(lambda: self.SetLinework(settings, notify))
            return
        v = self.viewport
        oldFurnishingWidth = v.lineWidths["furnishings"]
        v.lineworkSettings = dict(settings)
        v.lineWidths = {key: settings["baseWidth"] * value for key, value in settings.items() if key != "baseWidth"}
        if v.lineWidths["furnishings"] != oldFurnishingWidth:
            self.RefreshFurnishingRenderers()
        if self.settingsWindow is not None:
            self.settingsWindow.RefreshLinework()
        if notify:
            v.settingsChanged.emit()
        v.update()

    def RefreshFurnishingRenderers(self):
        v = self.viewport
        width = v.lineWidths["furnishings"]
        v.furnishingRenderers = FurnishingRendererMap(v.furnishingDefinitions, lineWidth = width, solidBackground = v.solidObjects)
        v.selectedFurnishingRenderers = FurnishingRendererMap(v.furnishingDefinitions, selected = True, lineWidth = width, solidBackground = v.solidObjects)
        v.groupedFurnishingRenderers.clear()

    def SetThemes(self, uiTheme = None, canvasTheme = None, notify = True):
        panel = getattr(self, "exportPanel", None)
        if notify and panel is not None and panel.projectView is not None and not panel.applying:
            panel.EditProjectSettings(lambda: self.SetThemes(uiTheme, canvasTheme, notify))
            return
        previous = (palette.activeUITheme, palette.activeCanvasTheme)
        palette.SetThemes(uiTheme, canvasTheme)
        if notify:
            self.appPreferences.update(uiTheme = palette.activeUITheme, canvasTheme = palette.activeCanvasTheme)
            self.SaveAppPreferences()
        if previous == (palette.activeUITheme, palette.activeCanvasTheme):
            return
        uiChanged = previous[0] != palette.activeUITheme
        canvasChanged = previous[1] != palette.activeCanvasTheme
        if uiChanged:
            app = QtWidgets.QApplication.instance()
            ApplyApplicationTheme(app)
            # Qt copies QIcons internally. Source registries also cover static label pixmaps.
            for widget in app.allWidgets():
                factory = iconSources.get(widget.windowIcon().cacheKey())
                if factory:
                    widget.setWindowIcon(factory())
                if hasattr(widget, "icon") and hasattr(widget, "setIcon"):
                    factory = iconSources.get(widget.icon().cacheKey())
                    if factory:
                        widget.setIcon(factory())
                if isinstance(widget, QtWidgets.QLabel):
                    pixmap = widget.pixmap()
                    source = pixmapSources.get(pixmap.cacheKey()) if pixmap and not pixmap.isNull() else None
                    if source:
                        factory, args = source
                        widget.setPixmap(factory().pixmap(*args))
                if isinstance(widget, QtWidgets.QComboBox):
                    for index in range(widget.count()):
                        factory = iconSources.get(widget.itemIcon(index).cacheKey())
                        if factory:
                            widget.setItemIcon(index, factory())
                if isinstance(widget, QtWidgets.QTabWidget):
                    for index in range(widget.count()):
                        factory = iconSources.get(widget.tabIcon(index).cacheKey())
                        if factory:
                            widget.setTabIcon(index, factory())
                for action in widget.actions():
                    factory = iconSources.get(action.icon().cacheKey())
                    if factory:
                        action.setIcon(factory())
                widget.update()
            if getattr(self, "helpWindow", None) is not None:
                self.helpWindow.RefreshTheme()
        if canvasChanged:
            canvasStyle = BuildCanvasStyle()
            for tree in self.findChildren(QtWidgets.QTreeWidget):
                if tree.objectName() == "visibilityTree":
                    tree.setStyleSheet(canvasStyle)
            for button in self.findChildren(QtWidgets.QPushButton):
                if button.objectName() == "openingIconButton":
                    button.setStyleSheet(canvasStyle)
                if isinstance(button, WindowButton):
                    factory = iconSources.get(button.icon().cacheKey())
                    if factory:
                        button.setIcon(factory())
            v = self.viewport
            # A canvas font change may leave every color unchanged.
            v.viewportSceneKey = None
            v.materialBrushes = {(material, selected): BuildWallBrush(selected = selected, material = material)
                                 for material in wallMaterials for selected in (False, True)}
            v.warningMaterialBrushes = {material: BuildWallBrush(material = material, warning = True) for material in wallMaterials}
            v.groupedMaterialBrushes = {material: BuildWallBrush(selected = True, material = material, grouped = True) for material in wallMaterials}
            self.RefreshFurnishingRenderers()
        for widget in self.findChildren(FurnishingButton):
            widget.RefreshIcon()
        if uiChanged:
            for grid in (*self.furnishingCategoryGrids.values(), self.furnishingResultsGrid):
                grid.RefreshMetrics()
        else:
            for grid in (*self.furnishingCategoryGrids.values(), self.furnishingResultsGrid):
                grid.viewport().update()
        self.furnishingList.RefreshIcons()
        quickSearch = getattr(self, "furnishingQuickSearch", None)
        if quickSearch is not None:
            for row in range(quickSearch.results.count()):
                item = quickSearch.results.item(row)
                definition = self.viewport.furnishingDefinitions.get(item.data(QtCore.Qt.ItemDataRole.UserRole))
                if definition is not None:
                    icon = self.furnishingThumbnails.Icon(definition)
                    if item.icon().cacheKey() != icon.cacheKey():
                        item.setIcon(icon)
        self.wallWidthSelector.icons = [WallPresetIcon(index) for index in range(4)]
        self.wallWidthSelector.update()
        self.materialIcons = {material: MaterialIcon(material) for material in wallMaterials}
        # Material swatches depend on the canvas even though their fields are UI.
        for field in (self.newWallMaterialField, self.materialField):
            for index in range(field.count()):
                material = field.itemText(index)
                if material in self.materialIcons:
                    field.setItemIcon(index, self.materialIcons[material])
        v = self.viewport
        self.RefreshVisibilityCounts()
        if self.settingsWindow is not None:
            normalView = self.exportPanel.projectView
            for field, name in ((self.settingsWindow.uiThemeField, palette.activeUITheme),
                                (self.settingsWindow.canvasThemeField, normalView["canvasTheme"] if normalView is not None else palette.activeCanvasTheme)):
                blocker = QtCore.QSignalBlocker(field)
                field.setCurrentText(name)
                del blocker
            self.settingsWindow.RefreshMeasurementVisibility()
        if notify:
            v.settingsChanged.emit()
        v.update()
