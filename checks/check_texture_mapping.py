"""Filename-controlled stretch/tiling, map-pixel density and dropdown labels."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.graphics import compositing
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.ui import export_panel


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    hintedName = "Tiled_Paper_t1.33_5_5_5_3.png"
    expectedDefaults = {"strength": .5, "highlights": .5, "midtones": .5, "shadows": .3}
    assert compositing.TextureMapping(hintedName, includeDefaults = True) == ("Tiled Paper", "tile", 1.33, expectedDefaults)
    assert compositing.TextureMapping("Rough_Paper_s_0_1_0.25_0.75.png", includeDefaults = True) == (
        "Rough Paper", "stretch", 1, {"strength": 0, "highlights": 1, "midtones": .25, "shadows": .75})
    assert compositing.TextureMapping("Paper_t_0.5_0.5_0.5_0.3.png", includeDefaults = True)[3] == expectedDefaults
    assert compositing.TextureMapping("Paper_t2_0_1_75_10.png", includeDefaults = True) == (
        "Paper", "tile", 2, {"strength": 0, "highlights": .1, "midtones": .75, "shadows": 1})
    assert compositing.TextureMapping("Paper_t0.5_01_333_5_10.png", includeDefaults = True) == (
        "Paper", "tile", .5, {"strength": .01, "highlights": .333, "midtones": .5, "shadows": 1})
    assert compositing.CompactTextureName("Paper_t2_0.1_0.10_0.333_1.png") == "Paper_t2_1_1_333_10.png"
    assert compositing.CompactTextureName("Paper_t2_1_1_333_10.png") == "Paper_t2_1_1_333_10.png"
    for name in ("Paper_t1_1.1_0.5_0.5_0.3.png", "Paper_s_0.5_0.5_nan_0.3.png",
                 "Paper_t1_0.5_bad_0.5_0.3.png"):
        try:
            compositing.TextureMapping(name)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid texture lighting defaults were accepted")
    for name, mode, scale in (("Paper.png", "tile", 1),
                              ("Paper_t.png", "tile", 1), ("Paper_t2.png", "tile", 2),
                              ("Paper_2.png", "tile", 2), ("Paper_t0.5.png", "tile", .5),
                              ("Paper_S.png", "stretch", 1)):
        assert compositing.TextureMapping(name) == ("Paper", mode, scale)
    for name, label, mode, scale in (("Rough Paper_t2.png", "Rough Paper", "tile", 2),
                                    ("Rough_Paper_s.png", "Rough Paper", "stretch", 1),
                                    ("Rough_Paper.png", "Rough Paper", "tile", 1),
                                    ("Paper_stone.png", "Paper Stone", "tile", 1),
                                    ("Paper_texture.png", "Paper Texture", "tile", 1),
                                    ("Paper_t2 - Copy.png", "Paper T2 - Copy", "tile", 1),
                                    ("Paper_.png", "Paper", "tile", 1),
                                    ("rough__paper_t0.5.png", "Rough Paper", "tile", .5),
                                    ("fine cotton paper_s.png", "Fine Cotton Paper", "stretch", 1),
                                    ("aged_PVC_paper.png", "Aged PVC Paper", "tile", 1)):
        assert compositing.TextureMapping(name) == (label, mode, scale)
    for name in ("Paper_t0.png", "Paper_t-2.png"):
        try:
            compositing.TextureMapping(name)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid tiling density was accepted")
    with tempfile.TemporaryDirectory(dir = Path(__file__).parent) as folder:
        directory = Path(folder)
        textures = directory / "textures"
        textures.mkdir()
        normal = QtGui.QImage(4, 1, QtGui.QImage.Format.Format_RGB32)
        for index, color in enumerate(((128, 255, 255), (128, 0, 255), (255, 128, 255), (128, 128, 255))):
            normal.setPixelColor(index, 0, QtGui.QColor(*color))
        images = {}
        with patch.object(compositing, "texturesDirectory", directory / "textures"), patch.object(export_panel, "texturesDirectory", directory / "textures"):
            for suffix in ("_s", "_t", "_t2", "_t0.5", "_2", "", "_t1.33_5_5_5_3"):
                name = "Pattern" + suffix + ".png"
                assert normal.save(str(textures / name))
                image = QtGui.QImage(16, 8, QtGui.QImage.Format.Format_RGB32)
                image.fill(QtGui.QColor(128, 128, 128))
                with QtGui.QPainter(image) as painter:
                    compositing.DrawNormalTexture(painter, QtCore.QRectF(0, 0, 16, 8), name, 0, (16, 8))
                images[suffix] = image
            assert images[""] == images["_t"]
            assert images["_2"] == images["_t2"]
            for suffix, period in (("_t", 4), ("_t2", 2), ("_t0.5", 8)):
                values = [images[suffix].pixelColor(x, 4).red() for x in range(16)]
                assert values[:period] == values[period:2 * period], (suffix, values)
                assert len(set(values[:period])) > 1
            # Enlarged tiles interpolate rather than repeating each source pixel.
            assert images["_t0.5"].pixelColor(0, 4) != images["_t0.5"].pixelColor(1, 4)
            assert len({images["_t0.5"].pixelColor(x, 4).red() for x in range(8)}) > len({images["_t"].pixelColor(x, 4).red() for x in range(4)})
            assert images["_s"].pixelColor(0, 4).red() < 5
            assert images["_s"].pixelColor(15, 4).red() > 120
            assert images["_s"].pixelColor(4, 4) != images["_t"].pixelColor(4, 4)
            main = MainWindow()
            main.show()
            main.sidebarTabs.setCurrentWidget(main.exportPanel)
            field = main.exportPanel.textureField
            assert field.itemText(0) == "None"
            assert all(field.itemText(index) == "Pattern" for index in range(1, field.count()))
            for index in range(1, field.count()):
                field.setCurrentIndex(index)
                assert field.itemData(index) in field.toolTip()
                label, mode, scale = compositing.TextureMapping(field.itemData(index))
                assert main.exportPanel.textureScaleSlider.value() == round(scale * 1000)
                assert main.exportPanel.textureScaleSlider.isEnabled() == (mode == "tile")
            panel = main.exportPanel
            field.setCurrentIndex(field.findData("Pattern_t2.png"))
            panel.textureScaleSlider.setValue(500)
            assert panel.overrides["textureScale"] == .5
            field.setCurrentIndex(field.findData("Pattern_s.png"))
            assert not panel.textureScaleSlider.isEnabled()
            assert not panel.textureScaleReset.isEnabled()
            field.setCurrentIndex(field.findData("Pattern_t2.png"))
            assert panel.textureScaleSlider.value() == 2000
            panel.textureScaleReset.click()
            assert panel.textureScaleSlider.value() == 2000 and "textureScale" not in panel.overrides
            for name, slider in panel.textureSliders.items():
                slider.setValue(47 if name == "Angle" else 800)
                assert "texture" + name in panel.overrides
            panel.vignetteStrengthField.setValue(.75)
            field.setCurrentIndex(field.findData("Pattern_t1.33_5_5_5_3.png"))
            assert panel.textureScaleField.value() == 1.33
            assert panel.TextureSettings() == dict(expectedDefaults, scaleOverride = None)
            defaults = dict(expectedDefaults, scale = 1.33, angle = 0)
            for name, slider in panel.textureSliders.items():
                default = defaults[name.lower()]
                assert slider.value() == round(default if name == "Angle" else default * 1000)
                assert panel.textureFields[name].value() == default
                assert "texture" + name not in panel.overrides
                assert not panel.textureResetButtons[name].isEnabled()
            assert panel.overrides["vignetteStrength"] == .75
            # Existing saved projects resolve their old decimal filenames to
            # the renamed texture, keeping any saved adjustments intact.
            legacyName = "Pattern_t1.33_0.5_0.5_0.5_0.3.png"
            panel.overrides.update(texture = legacyName, textureAngle = 37)
            panel.RefreshControls()
            assert panel.textureField.currentData() == "Pattern_t1.33_5_5_5_3.png"
            assert panel.textureAngleField.value() == 37
            panel.textureAngleReset.click()
            legacyImage = QtGui.QImage(16, 8, QtGui.QImage.Format.Format_RGB32)
            legacyImage.fill(QtGui.QColor(128, 128, 128))
            with QtGui.QPainter(legacyImage) as painter:
                compositing.DrawNormalTexture(painter, QtCore.QRectF(0, 0, 16, 8), legacyName, 0, (16, 8))
            assert legacyImage == images["_t1.33_5_5_5_3"]
            for name in ("Strength", "Highlights", "Midtones", "Shadows"):
                default = expectedDefaults[name.lower()]
                assert panel.textureFields[name].value() == default
                panel.textureFields[name].setValue(.8)
                assert panel.TextureSettings()[name.lower()] == .8
                panel.textureResetButtons[name].click()
                assert panel.textureFields[name].value() == default
                assert panel.TextureSettings()[name.lower()] == default
            field.setCurrentIndex(field.findData("Pattern_t.png"))
            assert panel.TextureSettings() == {"strength": .5, "highlights": 1, "midtones": 1, "shadows": 1, "scaleOverride": None}
            main.close()
    print("PASS: stretch, default tiling, fractional/integer densities, short names and identifying tooltips")


if __name__ == "__main__":
    Main()
