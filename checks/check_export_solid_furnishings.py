"""Transparent furnishing backgrounds in preview/export without changing outlines."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner import MainWindow
from furnishings import Furnishing
from planner_app.graphics.furnishings import FurnishingRenderer
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.project_codec import DecodeProject


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    graphic = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect x="5" y="5" width="90" height="90" fill="white" stroke="black"/></svg>'
    colors = {"background": "#ffffff", "outline": "#000000", "missing": "#ff0000"}
    for solid in (True, False):
        image = QtGui.QImage(100, 100, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor("#12ab34"))
        renderer = FurnishingRenderer(graphic, palette = colors, lineWidth = 2, solidBackground = solid)
        with QtGui.QPainter(image) as painter:
            renderer.render(painter)
        assert image.pixelColor(50, 50).name() == ("#ffffff" if solid else "#12ab34")
        assert image.pixelColor(5, 50).name() == "#000000", "Background toggle removed outline ink"
    main = MainWindow()
    main.show()
    v = main.viewport
    v.walls = []
    v.furnishings = [Furnishing(v.furnishingDefinitions["desk"])]
    v.EnsureObjectIds()
    v.sceneRevision += 1
    panel = main.exportPanel
    normalSettings = main.ProjectSettings()
    main.sidebarTabs.setCurrentWidget(panel)
    assert panel.solidObjectsField.isChecked() and "solidObjects" not in panel.overrides
    panel.borderField.setCurrentText("None")
    panel.showGridField.setChecked(True)
    panel.SetOverride("measurementVisibility", {key: False for key in v.measurementVisibility})
    solidPng = panel.Render("png")
    solidSvg = panel.Render("svg")
    v.grab()
    solidKey = v.exportOverlay.snapshotKey
    panel.solidObjectsField.setChecked(False)
    assert not v.solidObjects
    v.grab()
    assert v.exportOverlay.snapshotKey != solidKey
    assert not v.exportOverlay.snapshotViewport.solidObjects
    assert panel.Render("png") != solidPng, "Furnishing background still obscures grid"
    transparentSvg = panel.Render("svg")
    assert transparentSvg != solidSvg and QtSvg.QSvgRenderer(transparentSvg).isValid()
    panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
    v.grab()
    assert not v.exportOverlay.previewError
    saved = main.BuildProjectData(includeHistory = False)
    decoded = DecodeProject(saved, v.furnishingDefinitions)
    assert decoded[5]["exportSettings"]["solidObjects"] is False
    main.sidebarTabs.setCurrentIndex(0)
    assert v.solidObjects
    assert main.ProjectSettings().get("solidObjects") == normalSettings.get("solidObjects")
    main.sidebarTabs.setCurrentWidget(panel)
    assert not v.solidObjects
    panel.SetOverride("canvasColor", "#abcdef")
    assert not v.solidObjects, "Changing color discarded transparency"
    main.ApplyProject(decoded, None)
    main.sidebarTabs.setCurrentWidget(panel)
    assert not panel.solidObjectsField.isChecked() and not v.solidObjects
    main.close()
    print("PASS: Solid furnishing toggle, outlines, PNG/SVG, snapshot refresh and persistence")


if __name__ == "__main__":
    Main()
