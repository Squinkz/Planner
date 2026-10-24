"""Directional normal masks, rotation, tiling, PNG preview and saved Composite controls."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from planner import MainWindow
from planner_app.graphics import compositing
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.project_codec import DecodeProject
from planner_app.ui import export_panel


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    with tempfile.TemporaryDirectory(dir = Path(__file__).parent) as folder:
        directory = Path(folder)
        textures = directory / "textures"
        textures.mkdir()
        normal = QtGui.QImage(8, 8, QtGui.QImage.Format.Format_RGB32)
        normal.fill(QtGui.QColor(255, 128, 255))
        assert normal.save(str(textures / "test.png"))
        (textures / "ignore.txt").write_text("not an image")
        with patch.object(compositing, "texturesDirectory", directory / "textures"), patch.object(export_panel, "texturesDirectory", directory / "textures"):
            shades = []
            for angle in (0, 90, 180, 270):
                image = QtGui.QImage(24, 24, QtGui.QImage.Format.Format_RGB32)
                image.fill(QtGui.QColor(128, 128, 128))
                with QtGui.QPainter(image) as painter:
                    compositing.DrawNormalTexture(painter, QtCore.QRectF(4, 4, 16, 16), "test.png", angle, (16, 16))
                assert image.pixelColor(0, 0).red() == 128, "Effect escaped its region"
                shades.append(image.pixelColor(8, 8).red())
            assert abs(shades[0] - 64) <= 1 and abs(shades[2] - 64) <= 1
            assert shades[1] == 0 and shades[3] >= 253, shades
            # The blue channel is irrelevant to the model.
            original = image.copy()
            normal.fill(QtGui.QColor(255, 128, 0))
            assert normal.save(str(textures / "test.png"))
            compositing.LoadNormalTexture.cache_clear()
            compositing.NormalLightingTile.cache_clear()
            image.fill(QtGui.QColor(128, 128, 128))
            with QtGui.QPainter(image) as painter:
                compositing.DrawNormalTexture(painter, QtCore.QRectF(4, 4, 16, 16), "test.png", 270, (16, 16))
            assert image == original

            main = MainWindow()
            main.show()
            panel = main.exportPanel
            v = main.viewport
            main.sidebarTabs.setCurrentWidget(panel)
            assert "Composite" in panel.sectionButtons and "Vignette" not in panel.sectionButtons
            assert [panel.textureField.itemText(index) for index in range(panel.textureField.count())] == ["None", "Test"]
            assert not panel.textureAngleSlider.isEnabled()
            panel.SetOverride("canvasColor", "#808080")
            panel.showGridField.setChecked(False)
            panel.borderField.setCurrentText("None")
            v.exportOverlay.bounds = (0, 0, 4000, 2000)
            panel.SetBounds(v.exportOverlay.bounds)
            panel.scaleField.setValue(100)
            baseline = panel.Render("png")
            panel.textureField.setCurrentText("Test")
            assert panel.textureAngleSlider.isEnabled()
            panel.sectionButtons["Composite"].setChecked(True)
            app.processEvents()
            for name, field in panel.textureFields.items():
                assert not field.keyboardTracking()
                field.setFocus()
                field.selectAll()
                typed = "137" if name == "Angle" else "0.375"
                previous = dict(panel.overrides)
                QtTest.QTest.keyClicks(field.lineEdit(), typed)
                assert field.lineEdit().text() == typed, "Partial numeric entry was reformatted"
                assert panel.overrides == previous, "Uncommitted typing changed the render"
                QtTest.QTest.keyClick(field, QtCore.Qt.Key.Key_Return)
                assert panel.overrides["texture" + name] == (137 if name == "Angle" else .375)
                panel.textureResetButtons[name].click()
            for name in panel.textureSliders:
                value = 37 if name == "Angle" else .375
                panel.textureFields[name].setValue(value)
                assert panel.textureSliders[name].value() == (37 if name == "Angle" else 375)
                panel.textureResetButtons[name].click()
                assert "texture" + name not in panel.overrides
                assert panel.textureFields[name].value() == (0 if name == "Angle" else .5 if name == "Strength" else 1)
            assert panel.TextureSettings()["strength"] == .5
            assert abs(panel.Render("png").pixelColor(200, 100).red() - 96) <= 1
            panel.textureStrengthSlider.setValue(1000)
            assert abs(panel.Render("png").pixelColor(200, 100).red() - 64) <= 1
            panel.textureAngleSlider.setValue(90)
            assert panel.Render("png").pixelColor(200, 100).red() == 0
            panel.textureAngleSlider.setValue(270)
            assert panel.Render("png").pixelColor(200, 100).red() >= 253
            v.grab()
            assert v.exportOverlay.snapshot is not None and not v.exportOverlay.previewError
            snapshot = v.exportOverlay.snapshot
            panel.textureAngleSlider.setValue(180)
            preview = v.grab().toImage()
            assert v.exportOverlay.snapshot is snapshot
            point = v.WorldToViewport(QtCore.QPointF(2000, 1000)) * v.devicePixelRatioF()
            assert abs(preview.pixelColor(round(point.x()), round(point.y())).red() - 64) <= 1
            panel.textureStrengthSlider.setValue(0)
            assert panel.Render("png") == baseline
            panel.textureStrengthSlider.setValue(500)
            assert abs(panel.Render("png").pixelColor(200, 100).red() - 96) <= 1
            panel.textureStrengthSlider.setValue(1000)
            panel.textureMidtonesSlider.setValue(0)
            assert abs(panel.Render("png").pixelColor(200, 100).red() - 128) <= 1
            panel.textureMidtonesSlider.setValue(1000)
            panel.textureAngleSlider.setValue(90)
            panel.textureShadowsSlider.setValue(0)
            assert abs(panel.Render("png").pixelColor(200, 100).red() - 128) <= 1
            panel.textureShadowsSlider.setValue(1000)
            panel.textureAngleSlider.setValue(270)
            panel.textureHighlightsSlider.setValue(0)
            assert abs(panel.Render("png").pixelColor(200, 100).red() - 128) <= 1
            panel.textureHighlightsSlider.setValue(1000)
            panel.textureAngleSlider.setValue(180)
            panel.textureScaleSlider.setValue(0)
            assert panel.Render("png") == baseline, "Zero density did not bypass the texture"
            panel.textureScaleReset.click()
            assert "textureScale" not in panel.overrides and panel.textureScaleSlider.value() == 1000
            panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
            assert panel.compositeSection.isHidden()
            assert panel.sectionButtons["Composite"].isChecked()
            assert not panel.textureField.isEnabled() and not panel.textureAngleSlider.isEnabled()
            svg = panel.Render("svg")
            panel.SetOverride("texture", None)
            assert panel.Render("svg") == svg
            panel.SetOverride("texture", "test.png")
            panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
            assert not panel.compositeSection.isHidden()
            assert panel.sectionButtons["Composite"].isChecked()
            assert panel.textureField.currentText() == "Test" and panel.textureAngleSlider.value() == 0
            panel.textureAngleSlider.setValue(180)
            for name, value in (("Scale", 500), ("Strength", 625), ("Highlights", 750), ("Midtones", 250), ("Shadows", 875)):
                panel.textureSliders[name].setValue(value)
            panel.sectionButtons["Composite"].setChecked(True)
            saved = main.BuildProjectData(includeHistory = False)
            decoded = DecodeProject(saved, v.furnishingDefinitions)
            assert decoded[5]["exportSettings"]["texture"] == "test.png"
            assert decoded[5]["exportSettings"]["textureAngle"] == 180
            main.ApplyProject(decoded, None)
            main.sidebarTabs.setCurrentWidget(panel)
            assert panel.sectionButtons["Composite"].isChecked()
            assert panel.textureField.currentText() == "Test" and panel.textureAngleSlider.value() == 180
            for name, value in (("Scale", 500), ("Strength", 625), ("Highlights", 750), ("Midtones", 250), ("Shadows", 875)):
                assert panel.textureSliders[name].value() == value
            panel.textureField.setCurrentText("None")
            assert panel.Render("png") == baseline
            assert not panel.textureAngleSlider.isEnabled()
            main.close()
    print("PASS: normal masks, rotation, blue exclusion, clipping, cached preview, PNG-only controls and persistence")


if __name__ == "__main__":
    Main()
