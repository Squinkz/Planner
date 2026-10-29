"""Border width, text-free markings, preview layout and project persistence."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner_app.graphics import palette
from planner_app.ui.color_picker import ColorPickerDialog
from planner import MainWindow, Wall
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.project_codec import DecodeProject
from planner_app.viewport.widget import DrawingViewport
from planner_app.graphics.export_border import DrawExportBorder


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.show()
    v = main.viewport
    v.walls = [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), 240)]
    v.EnsureObjectIds()
    v.sceneRevision += 1
    panel = main.exportPanel
    main.sidebarTabs.setCurrentWidget(panel)
    panel.scaleField.setValue(100)
    panel.borderField.setCurrentText("None")
    canvasSize = panel.Render("png").size()
    assert not panel.borderSizeOptions.isEnabled()
    assert not panel.borderColorLabel.isEnabled() and not panel.borderColorButton.isEnabled()
    assert not panel.borderColorReset.isEnabled()

    panel.borderField.setCurrentText("Plain")
    assert panel.borderColorLabel.isEnabled() and panel.borderColorButton.isEnabled()
    panel.borderSizeSlider.setValue(5)
    assert panel.borderSizeField.value() == 5 and v.exportOverlay.borderSize == 5
    assert panel.Render("png").size() == canvasSize + QtCore.QSize(10, 10)
    panel.borderField.setCurrentText("Ruler")
    assert panel.borderSizeSlider.minimum() == 28 and panel.borderSizeField.value() == 28
    assert panel.overrides["borderSize"] == 5, "Changing styles erased the requested width"
    panel.borderField.setCurrentText("Marked")
    assert panel.borderSizeSlider.minimum() == 12 and panel.borderSizeField.value() == 12
    assert v.exportOverlay.borderSize == 12
    assert panel.Render("png").size() == canvasSize + QtCore.QSize(24, 24)
    panel.borderSizeField.setValue(45)
    assert panel.borderSizeSlider.value() == 45
    png = panel.Render("png")
    assert png.size() == canvasSize + QtCore.QSize(90, 90)
    assert [field.value() for field in panel.resolutionFields] == [png.width(), png.height()]
    panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
    svg = panel.Render("svg")
    renderer = QtSvg.QSvgRenderer(svg)
    assert renderer.isValid() and renderer.defaultSize() == png.size()
    v.grab()
    assert not v.exportOverlay.previewError

    normalBorderColor = palette.themeDefinitions[palette.activeCanvasTheme]["colors"]["rulerBackground"]
    normalCanvasColor = palette.themeColors["canvas"]
    with patch.object(ColorPickerDialog, "GetColor", return_value = QtGui.QColor("#d34567")):
        panel.borderColorButton.click()
    assert panel.overrides["borderColor"] == "#d34567"
    assert palette.themeColors["rulerBackground"] == "#d34567"
    assert palette.themeColors["canvas"] == normalCanvasColor
    panel.borderField.setCurrentText("Plain")
    assert panel.Render("png").pixelColor(0, 0).name() == "#d34567"
    coloredSvg = panel.Render("svg")
    image = QtGui.QImage(png.size(), QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    with QtGui.QPainter(image) as painter:
        QtSvg.QSvgRenderer(coloredSvg).render(painter)
    assert image.pixelColor(0, 0).name() == "#d34567"
    main.sidebarTabs.setCurrentIndex(0)
    assert palette.themeColors["rulerBackground"] == normalBorderColor
    main.sidebarTabs.setCurrentWidget(panel)
    assert palette.themeColors["rulerBackground"] == "#d34567"
    savedColor = main.BuildProjectData(includeHistory = False)
    assert DecodeProject(savedColor, v.furnishingDefinitions)[5]["exportSettings"]["borderColor"] == "#d34567"
    main.ApplyProject(DecodeProject(savedColor, v.furnishingDefinitions), None)
    main.sidebarTabs.setCurrentWidget(panel)
    assert palette.themeColors["rulerBackground"] == "#d34567"
    previousSettings = main.ProjectSettings()
    def PreviewAndCancel():
        dialog = app.activeModalWidget()
        dialog.SetColor(QtGui.QColor("#aabbcc"))
        assert palette.themeColors["rulerBackground"] == "#aabbcc"
        assert main.ProjectSettings() == previousSettings
        v.grab()
        dialog.reject()
    QtCore.QTimer.singleShot(0, PreviewAndCancel)
    panel.borderColorButton.click()
    assert palette.themeColors["rulerBackground"] == "#d34567"
    with patch.object(ColorPickerDialog, "GetColor", return_value = QtGui.QColor(normalBorderColor)):
        panel.borderColorButton.click()
    assert "borderColor" not in panel.overrides
    assert palette.themeColors["rulerBackground"] == normalBorderColor
    panel.SetOverride("borderColor", "#d34567")
    panel.borderColorReset.click()
    assert "borderColor" not in panel.overrides
    assert palette.themeColors["rulerBackground"] == normalBorderColor
    panel.borderField.setCurrentText("Marked")

    saved = main.BuildProjectData(includeHistory = False)
    main.ApplyProject(DecodeProject(saved, v.furnishingDefinitions), None)
    main.sidebarTabs.setCurrentWidget(panel)
    assert panel.overrides["border"] == "Marked" and panel.overrides["borderSize"] == 45
    assert panel.borderSizeField.value() == 45

    # The real ruler renderer must omit both edge labels and corner units.
    class TextCountingPainter(QtGui.QPainter):
        def drawText(self, *args):
            self.textCount += 1
            super().drawText(*args)

    source = DrawingViewport()
    source.setMinimumSize(0, 0)
    source.resize(400, 300)
    source.rulerSize = 12
    rect = QtCore.QRectF(12, 12, 376, 276)
    counts = []
    for marked in (True, False):
        image = QtGui.QImage(400, 300, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        with TextCountingPainter(image) as painter:
            painter.textCount = 0
            unit = source.DrawGridBackground(painter, rect, rect.center(), .1, drawGrid = False,
                                             allEdges = True, markingsOnly = marked)
            source.DrawRulerFrame(painter, unit, allEdges = True, drawUnits = not marked)
            counts.append(painter.textCount)
        assert image.pixelColor(12, 12).alpha() > 0, "Border markings were not rendered"
    assert counts[0] == 0 and counts[1] > 4
    panel.borderField.setCurrentText("Ruler")
    panel.borderSizeField.setValue(28)
    ruler = panel.Render("png")
    panel.borderField.setCurrentText("Ruler + Reference Zones")
    assert panel.borderSizeSlider.minimum() == panel.borderSizeField.value() == 56
    combined = panel.Render("png")
    assert combined.size() == ruler.size() + QtCore.QSize(56, 56)
    assert combined.copy(29, 29, ruler.width() - 2, ruler.height() - 2) == ruler.copy(1, 1, ruler.width() - 2, ruler.height() - 2), "Reference zones changed the inner ruler or scene"
    zonesColor = QtGui.QColor(palette.themeColors["rulerBackground"]).darker(110)
    assert combined.pixelColor(14, 14).name() == zonesColor.name()
    for x in (28, combined.width() - 28):
        for y in (14, combined.height() - 14):
            assert combined.pixelColor(x, y).name() != zonesColor.name(), "Missing reference-zone corner divider"
    svg = panel.Render("svg")
    assert QtSvg.QSvgRenderer(svg).isValid() and QtSvg.QSvgRenderer(svg).defaultSize() == combined.size()
    saved = main.BuildProjectData(includeHistory = False)
    assert DecodeProject(saved, v.furnishingDefinitions)[5]["exportSettings"]["border"] == "Ruler + Reference Zones"
    panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
    app.processEvents()
    v.grab()
    assert not v.exportOverlay.previewError and len(v.exportOverlay.rulerStrips) == 4
    class BorderRecordingPainter(QtGui.QPainter):
        def drawImage(self, *args):
            self.bitmapCount += 1
            super().drawImage(*args)

    for style in ("Plain", "Frame", "Corner Marks", "Reference Zones", "Marked", "Ruler", "Ruler + Reference Zones"):
        panel.borderField.setCurrentText(style)
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        v.grab()
        surface = QtGui.QImage(v.size(), QtGui.QImage.Format.Format_ARGB32)
        surface.fill(QtCore.Qt.GlobalColor.transparent)
        painter = BorderRecordingPainter(surface)
        painter.bitmapCount = 0
        with patch.object(v.rasterCacheBudget, "Prepare", wraps = v.rasterCacheBudget.Prepare) as prepareBorder:
            v.exportOverlay.DrawCropRulers(painter, v.DrawingRect())
        painter.end()
        assert painter.bitmapCount == 0, f"{style} uses raster images in SVG preview"
        assert not v.exportOverlay.rulerStrips
        assert not any(call.args[0] == "rulers" for call in prepareBorder.call_args_list), "SVG borders must not allocate raster strips"
    panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
    v.grab()
    assert len(v.exportOverlay.rulerStrips) == 4, "Switching back to PNG should restore raster border strips"
    x, y, width, height = v.exportOverlay.bounds
    topCenter = v.WorldToViewport(QtCore.QPointF(x + width / 2, y + height))
    factor = v.basePixelsPerMillimeter * v.zoom / (v.exportOverlay.scale / 1000)
    assert v.exportOverlay.HitRuler(topCenter - QtCore.QPointF(0, 14 * factor)) == 0
    assert v.exportOverlay.HitRuler(topCenter - QtCore.QPointF(0, 42 * factor)) is None, "Reference zones act as ruler drag handles"
    v.exportOverlay.rulerKey = None
    prepare = v.rasterCacheBudget.Prepare
    with patch.object(v.rasterCacheBudget, "Prepare", side_effect = lambda name, *args, **kwargs: False if name == "rulers" else prepare(name, *args, **kwargs)):
        v.grab()
    assert not v.exportOverlay.previewError
    combined.save(str(Path(__file__).resolve().parent.parent / "screenshots" / "ruler-reference-zones.png"))
    for style in ("Frame", "Corner Marks", "Reference Zones"):
        panel.borderField.setCurrentText(style)
        png = panel.Render("png")
        svg = panel.Render("svg")
        assert QtSvg.QSvgRenderer(svg).isValid()
        assert QtSvg.QSvgRenderer(svg).defaultSize() == png.size()
        saved = main.BuildProjectData(includeHistory = False)
        assert DecodeProject(saved, v.furnishingDefinitions)[5]["exportSettings"]["border"] == style
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        v.grab()
        assert not v.exportOverlay.previewError
        image = QtGui.QImage(500, 400, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        with TextCountingPainter(image) as painter:
            painter.textCount = 0
            painter.setFont(source.font())
            DrawExportBorder(painter, QtCore.QRectF(40, 40, 420, 320), 40, style)
            assert (painter.textCount > 0) == (style == "Reference Zones")
        assert image.pixelColor(0, 0).name() == palette.themeColors["rulerBackground"]
        assert image.pixelColor(250, 200).alpha() == 0, "Border painted over the plan interior"
        if style in ("Frame", "Corner Marks"):
            assert image.pixelColor(20, 20).name() != palette.themeColors["rulerBackground"]
            assert (image.pixelColor(250, 20).name() != palette.themeColors["rulerBackground"]) == (style == "Frame")
    with patch.object(QtWidgets.QMessageBox, "question", return_value = QtWidgets.QMessageBox.StandardButton.Discard):
        main.close()
    print("PASS: Border style minimums, width synchronization, PNG/SVG layout, preview, persistence and text-free markings")


if __name__ == "__main__":
    Main()
