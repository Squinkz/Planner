"""Canvas-only themes refresh dependent artwork without repolishing the application."""
import json
import os
from pathlib import Path
from statistics import median
import sys
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow
from planner_app.models import Wall
from planner_app.graphics import palette
from planner_app.graphics.theme import ApplyApplicationTheme, BuildCanvasStyle
from planner_app.ui.settings import SettingsWindow
from planner_app.ui.widgets import FurnishingButton, WindowButton


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.show()
    main.settingsWindow = SettingsWindow(main)
    app.processEvents()
    viewport = main.viewport
    viewport.walls = [Wall(QtCore.QPointF(-500, 0), QtCore.QPointF(500, 0))]
    originalStyle, originalPalette, originalFont = app.styleSheet(), app.palette(), app.font()
    originalHeader = main.fullscreenButton.icon().cacheKey()
    definition = main.viewport.furnishingDefinitions["desk"]
    counter = next(button for button in main.findChildren(WindowButton) if button.objectType == "counter")
    durations = []
    with patch.object(app, "setStyleSheet", wraps = app.setStyleSheet) as styles, \
         patch.object(app, "allWidgets", wraps = app.allWidgets) as allWidgets:
        for canvasTheme in ("Light Canvas", "Dark Canvas") * 3:
            oldRenderer = viewport.furnishingRenderers
            oldFurnishingIcon, oldCounterIcon = main.furnishingThumbnails.Icon(definition).cacheKey(), counter.icon().cacheKey()
            oldMaterialIcon = main.newWallMaterialField.itemIcon(0).cacheKey()
            started = perf_counter()
            main.SetThemes(canvasTheme = canvasTheme)
            durations.append((perf_counter() - started) * 1000)
            assert not styles.called and not allWidgets.called
            assert app.styleSheet() == originalStyle and app.palette() == originalPalette and app.font() == originalFont
            assert main.fullscreenButton.icon().cacheKey() == originalHeader
            assert viewport.furnishingRenderers is not oldRenderer
            assert main.furnishingThumbnails.Icon(definition).cacheKey() == oldFurnishingIcon and counter.icon().cacheKey() != oldCounterIcon
            assert main.newWallMaterialField.itemIcon(0).cacheKey() != oldMaterialIcon
            assert viewport.materialBrushes[("Generic", False)].color().name() == palette.themeColors["wallFill"]
            for tree in main.findChildren(QtWidgets.QTreeWidget):
                if tree.objectName() == "visibilityTree":
                    assert tree.styleSheet() == BuildCanvasStyle()
            assert palette.themeColors["selectionOutline"] in counter.styleSheet()

        # Export can select a different canvas, then restore the project's
        # theme. Repeated entry/exit must not trigger global UI refreshes.
        panel = main.exportPanel
        main.sidebarTabs.setCurrentWidget(panel)
        panel.canvasThemeField.setCurrentText("Light Canvas")
        assert palette.activeCanvasTheme == "Light Canvas"
        for repeat in range(3):
            main.sidebarTabs.setCurrentIndex(0)
            assert palette.activeCanvasTheme == "Dark Canvas"
            main.sidebarTabs.setCurrentWidget(panel)
            assert palette.activeCanvasTheme == "Light Canvas"
        main.sidebarTabs.setCurrentIndex(0)
        assert not styles.called and not allWidgets.called

        # A font-only canvas change still invalidates retained scene content.
        palette.themeDefinitions["Font-only Canvas"] = {
            **palette.themeDefinitions["Dark Canvas"], "labelFont": "Courier New"}
        try:
            viewport.grab()
            assert viewport.viewportSceneKey is not None
            main.SetThemes(canvasTheme = "Font-only Canvas")
            assert palette.labelFont == "Courier New" and viewport.viewportSceneKey is None
            assert not styles.called and not allWidgets.called
        finally:
            main.SetThemes(canvasTheme = "Dark Canvas")
            del palette.themeDefinitions["Font-only Canvas"]

        # UI changes still update the application; unchanged canvas renderers
        # and material brushes do not need rebuilding for that transition.
        renderer, brush = viewport.furnishingRenderers, viewport.materialBrushes
        main.SetThemes(uiTheme = "Light UI")
        assert styles.call_count == allWidgets.call_count == 1
        assert app.styleSheet() != originalStyle
        assert viewport.furnishingRenderers is renderer and viewport.materialBrushes is brush
        main.SetThemes(uiTheme = "Light UI")
        assert styles.call_count == 1, "An unchanged theme pair refreshed the application"

    main.close()
    report = {"canvasSwitches": len(durations), "medianCanvasSwitchMs": round(median(durations), 3),
              "maximumCanvasSwitchMs": round(max(durations), 3), "globalStylesheetCallsForCanvasSwitches": 0}
    (Path(__file__).resolve().parent.parent / "diagnostics/canvas-theme-performance-20261008.json").write_text(
        json.dumps(report, indent = 2) + "\n", encoding = "utf-8")
    print("PASS: local canvas refreshes, unchanged UI, export transitions, font-only invalidation and UI refresh.")
    print(json.dumps(report))


if __name__ == "__main__":
    Main()
