"""Canvas font changes refresh furnishings, compounds and export overrides."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtWidgets
from planner import MainWindow
from planner_app.graphics import palette
from planner_app.models import Furnishing
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from planner_app.graphics.furnishings import CompoundFurnishingSvg, FurnishingRenderer


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v, panel = main.viewport, main.exportPanel
    originalTheme = palette.activeCanvasTheme
    fontTheme = "Furnishing Font Check"
    palette.themeDefinitions[fontTheme] = {**palette.themeDefinitions[originalTheme], "labelFont": "Courier New"}
    try:
        original = v.furnishingRenderers["washer"]
        main.SetThemes(canvasTheme = fontTheme)
        themed = v.furnishingRenderers["washer"]
        assert themed is not original and themed.letteringFont == "Courier New"
        assert v.selectedFurnishingRenderers["washer"].letteringFont == "Courier New"
        component = {"definition": v.furnishingDefinitions["washer"], "width": 600, "length": 600,
                     "x": 0, "y": 0, "angle": 35, "zIndex": 0}
        compound = FurnishingRenderer(CompoundFurnishingSvg([component])[0])
        assert compound.lettering and compound.letteringFont == "Courier New"
        v.furnishings = [Furnishing(v.furnishingDefinitions["washer"])]
        main.SetThemes(canvasTheme = originalTheme)
        originalFont = palette.labelFont
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetOverride("canvasTheme", fontTheme)
        assert palette.labelFont == "Courier New"
        assert v.furnishingRenderers["washer"].letteringFont == "Courier New"
        assert not panel.Render("png").isNull()
        assert SvgPreviewRenderer(panel.Render("svg")).isValid()
        main.sidebarTabs.setCurrentIndex(0)
        assert palette.activeCanvasTheme == originalTheme and palette.labelFont == originalFont
        assert v.furnishingRenderers["washer"].letteringFont == originalFont
    finally:
        main.SetThemes(canvasTheme = originalTheme)
        del palette.themeDefinitions[fontTheme]
        main.close()
    print("PASS: furnishing fonts refresh with canvas themes, selected/compound graphics and PNG/SVG export overrides")


if __name__ == "__main__":
    Main()
