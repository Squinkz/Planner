"""Aspect-correct multiply vignette, PNG preview/output, SVG exclusion and persistence."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from planner import MainWindow
from planner_app.graphics.compositing import DrawVignette
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.project_codec import DecodeProject


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    # Matching normalized positions must have the same shade despite aspect ratio.
    shades = []
    for width, height in ((800, 400), (400, 800), (400, 400)):
        image = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.white)
        with QtGui.QPainter(image) as painter:
            DrawVignette(painter, QtCore.QRectF(0, 0, width, height), 1)
        repeated = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32)
        repeated.fill(QtCore.Qt.GlobalColor.white)
        with QtGui.QPainter(repeated) as painter:
            DrawVignette(painter, QtCore.QRectF(0, 0, width, height), 1)
        assert repeated == image, "Dithering changed between identical renders"
        # Equal-radius positions would be identical in an undithered gradient.
        # The small variation breaks contours without introducing heavy grain.
        differences = [abs(image.pixelColor(x, height // 4).red()
                           - image.pixelColor(width - 1 - x, height // 4).red())
                       for x in range(width // 8, width // 4)]
        assert 2 <= max(differences) <= 4, (width, height, max(differences))
        assert image.pixelColor(width // 2, height // 2).red() >= 254
        shades.append(image.pixelColor(width // 4, height // 4).red())
        # The center remains clear through 30% of the center-to-corner radius.
        # Halfway outward is still light, with shading concentrated at the edge.
        assert 216 <= shades[-1] <= 223, (width, height, shades[-1])
        assert image.pixelColor(width * 7 // 20, height * 7 // 20).red() >= 254
        assert image.pixelColor(0, 0).red() < 5
    assert max(shades) - min(shades) <= 2

    main = MainWindow()
    main.show()
    panel = main.exportPanel
    v = main.viewport
    main.sidebarTabs.setCurrentWidget(panel)
    panel.SetOverride("canvasColor", "#ffffff")
    panel.SetOverride("borderColor", "#ff0000")
    panel.showGridField.setChecked(False)
    panel.borderField.setCurrentText("Plain")
    panel.scaleField.setValue(100)
    v.exportOverlay.bounds = (0, 0, 4000, 2000)
    panel.SetBounds(v.exportOverlay.bounds)
    baseline = panel.Render("png")
    assert not panel.vignetteStrengthOptions.isEnabled()
    panel.enableVignetteField.setChecked(True)
    assert panel.vignetteStrengthOptions.isEnabled()
    panel.sectionButtons["Composite"].setChecked(True)
    app.processEvents()
    assert not panel.vignetteStrengthField.keyboardTracking()
    panel.vignetteStrengthField.setFocus()
    panel.vignetteStrengthField.selectAll()
    previous = dict(panel.overrides)
    QtTest.QTest.keyClicks(panel.vignetteStrengthField.lineEdit(), "0.375")
    assert panel.vignetteStrengthField.lineEdit().text() == "0.375"
    assert panel.overrides == previous
    QtTest.QTest.keyClick(panel.vignetteStrengthField, QtCore.Qt.Key.Key_Return)
    assert panel.vignetteStrengthSlider.value() == 375
    panel.vignetteStrengthField.setValue(.375)
    assert panel.vignetteStrengthSlider.value() == 375
    panel.vignetteStrengthReset.click()
    assert "vignetteStrength" not in panel.overrides and panel.vignetteStrengthField.value() == .125
    panel.vignetteStrengthField.setValue(0)
    assert panel.vignetteStrengthSlider.value() == 0
    assert panel.Render("png") == baseline
    panel.vignetteStrengthSlider.setValue(1000)
    shaded = panel.Render("png")
    assert shaded != baseline
    size = v.exportOverlay.borderSize
    assert shaded.pixelColor(0, 0).red() < 5, "Vignette did not cover the border"
    for style in ("Marked", "Ruler"):
        panel.borderField.setCurrentText(style)
        assert panel.Render("png").pixelColor(3, 3).red() < 25, "Vignette did not cover the rulers"
    panel.borderField.setCurrentText("Plain")
    assert shaded.pixelColor(size + 200, size + 100).red() >= 254, (shaded.size(), size, shaded.pixelColor(size + 200, size + 100).name(), baseline.pixelColor(size + 200, size + 100).name(), len(v.walls), v.exportOverlay.bounds)
    sample = shaded.pixelColor(size + 100, size + 50).red()
    panel.vignetteStrengthSlider.setValue(2000)
    assert panel.Render("png").pixelColor(size + 100, size + 50).red() < sample

    # Preview uses the crop rather than the larger cached plan snapshot.
    v.grab()
    assert v.exportOverlay.snapshot is not None and not v.exportOverlay.previewError
    cachedSnapshot = v.exportOverlay.snapshot
    panel.vignetteStrengthSlider.setValue(500)
    v.grab()
    assert v.exportOverlay.snapshot is cachedSnapshot, "Strength changes rebuilt the plan bitmap"
    assert v.exportOverlay.vignetteStrength == .5
    preview = v.grab().toImage()
    position = v.WorldToViewport(QtCore.QPointF(1000, 1500)) * v.devicePixelRatioF()
    exportedShade = panel.Render("png").pixelColor(size + 100, size + 50).red()
    assert abs(preview.pixelColor(round(position.x()), round(position.y())).red() - exportedShade) <= 3

    panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
    assert not panel.enableVignetteField.isEnabled() and not panel.vignetteStrengthSlider.isEnabled()
    svg = panel.Render("svg")
    panel.SetOverride("vignetteEnabled", False)
    assert panel.Render("svg") == svg, "Vignette changed SVG output"
    panel.SetOverride("vignetteEnabled", True)
    panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
    assert panel.enableVignetteField.isChecked() and panel.vignetteStrengthSlider.value() == 500
    assert panel.vignetteStrengthSlider.isEnabled()
    saved = main.BuildProjectData(includeHistory = False)
    decoded = DecodeProject(saved, v.furnishingDefinitions)
    assert decoded[5]["exportSettings"]["vignetteStrength"] == .5
    main.ApplyProject(decoded, None)
    main.sidebarTabs.setCurrentWidget(panel)
    assert panel.enableVignetteField.isChecked() and panel.vignetteStrengthSlider.value() == 500
    main.sidebarTabs.setCurrentIndex(0)
    assert not v.exportOverlay.active
    main.close()
    print("PASS: aspect ratio, strength, border/ruler coverage, cached preview, SVG exclusion and saved vignette settings")


if __name__ == "__main__":
    Main()
