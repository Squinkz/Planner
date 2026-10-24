"""Wall fill choices preserve grid visibility and remain isolated to export."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner import MainWindow, Wall
from planner_app.graphics import palette
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.project_codec import DecodeProject


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.show()
    v = main.viewport
    v.walls = [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), 400, material = "Brick")]
    v.EnsureObjectIds()
    v.sceneRevision += 1
    panel = main.exportPanel
    main.sidebarTabs.setCurrentWidget(panel)
    panel.SetOverride("bounds", [-2000, -1000, 4000, 2000])
    v.exportOverlay.bounds = (-2000, -1000, 4000, 2000)
    panel.scaleField.setValue(100)
    panel.borderField.setCurrentText("None")
    panel.SetOverride("measurementVisibility", {key: False for key in v.measurementVisibility})
    panel.showGridField.setChecked(False)
    assert panel.canvasColorLabel.text() == "Background"
    assert panel.wallStyleField.currentText() == "Material" and "wallStyle" not in panel.overrides
    material = panel.Render("png")
    panel.wallStyleField.setCurrentText("Solid")
    solid = panel.Render("png")
    assert solid.pixelColor(220, 100).name() == palette.themeColors["wallOutline"]
    assert solid != material
    panel.wallStyleField.setCurrentText("Outline")
    outline = panel.Render("png")
    assert outline.pixelColor(220, 100).name() == palette.themeColors["canvas"]
    panel.showGridField.setChecked(True)
    grid = panel.Render("png")
    assert grid.pixelColor(220, 100) != outline.pixelColor(220, 100), "Outline hid the grid inside the wall"
    panel.showGridField.setChecked(False)
    for style in ("Material", "Solid", "Outline"):
        panel.wallStyleField.setCurrentText(style)
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        v.grab()
        assert v.exportOverlay.snapshotViewport.wallStyle == style
        assert not v.exportOverlay.previewError
        png = panel.Render("png")
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        svg = panel.Render("svg")
        assert QtSvg.QSvgRenderer(svg).isValid()
        image = QtGui.QImage(png.size(), QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        with QtGui.QPainter(image) as painter:
            QtSvg.QSvgRenderer(svg).render(painter)
        if style != "Material":
            svgColor, pngColor = image.pixelColor(220, 100), png.pixelColor(220, 100)
            assert svgColor == pngColor, (style, svgColor.getRgb(), pngColor.getRgb())
        v.grab()
        assert not v.exportOverlay.previewError
        saved = main.BuildProjectData(includeHistory = False)
        decoded = DecodeProject(saved, v.furnishingDefinitions)
        assert decoded[5]["exportSettings"]["wallStyle"] == style
    main.sidebarTabs.setCurrentIndex(0)
    assert v.wallStyle == "Material", "Export fill leaked into the normal viewport"
    main.sidebarTabs.setCurrentWidget(panel)
    assert v.wallStyle == "Outline"
    main.ApplyProject(decoded, None)
    main.sidebarTabs.setCurrentWidget(panel)
    assert panel.wallStyleField.currentText() == "Outline"
    main.close()
    print("PASS: Wall fill modes, grid visibility, PNG/SVG, previews and project isolation")


if __name__ == "__main__":
    Main()
