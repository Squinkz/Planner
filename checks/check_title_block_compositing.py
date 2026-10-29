"""Texture and vignette cover the complete title-block export and preview."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui
from planner_app.graphics import compositing
from planner_app.graphics.title_block import TitleBlockLayout
from planner_app.export_settings import ExportPixelSize
from fixtures.parity_examples import ExampleWindow


def Main():
    with ExampleWindow() as (main, folder):
        normal = QtGui.QImage(8, 8, QtGui.QImage.Format.Format_RGB32)
        normal.fill(QtGui.QColor(255, 128, 255))
        assert normal.save(str(folder / "test_s.png"))
        with patch.object(compositing, "texturesDirectory", folder):
            panel, v = main.exportPanel, main.viewport
            main.sidebarTabs.setCurrentWidget(panel)
            panel.SetOverride("canvasColor", "#cccccc")
            panel.SetOverride("showGrid", False)
            panel.SetBorder("Plain")
            panel.SetScale(300)
            for position in ("Right", "Bottom"):
                panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "None", position = position,
                    projectName = "Composite test", sheetNumber = "", comments = "Notes", date = "2026-10-29"))
                v.exportOverlay.bounds = v.exportOverlay.ConstrainTitleBlockBounds((0, 0, 3000, 3000))
                panel.SetBounds(v.exportOverlay.bounds)
                panel.SetOverride("texture", None)
                panel.SetOverride("vignetteEnabled", False)
                baseline = panel.Render("png")
                args = panel.RenderArguments("png")
                width, height = ExportPixelSize(args["bounds"], args["scale"], args["borderSize"])
                outputWidth, outputHeight, block = TitleBlockLayout(width, height, args["titleBlock"], args["scale"])
                sample = QtCore.QPoint(int(block[0] + block[2] - 20), int(block[1] + block[3] - 20))
                assert baseline.pixelColor(sample) == QtGui.QColor("#cccccc")
                for texture, strength in (("test_s.png", 0), (None, .8), ("test_s.png", .8)):
                    panel.SetOverride("texture", texture)
                    panel.SetOverride("textureStrength", .5)
                    panel.SetOverride("vignetteEnabled", strength > 0)
                    panel.SetOverride("vignetteStrength", strength)
                    expected = baseline.copy()
                    with QtGui.QPainter(expected) as painter:
                        frame = QtCore.QRectF(0, 0, outputWidth, outputHeight)
                        compositing.DrawNormalTexture(painter, frame, texture, 0, (outputWidth, outputHeight), **panel.TextureSettings())
                        compositing.DrawVignette(painter, frame, strength, (outputWidth, outputHeight))
                    rendered = panel.Render("png")
                    assert rendered == expected, f"Composite omitted part of {position} export"
                    assert rendered.pixelColor(sample) != baseline.pixelColor(sample)
                    factor = .2
                    v.zoom = factor * panel.ScalePerMeter() / (1000 * v.basePixelsPerMillimeter)
                    x, y, cropWidth, cropHeight = v.exportOverlay.bounds
                    first = v.WorldToViewport(QtCore.QPointF(x, y + cropHeight)) - QtCore.QPointF(args["borderSize"] * factor, args["borderSize"] * factor)
                    target = v.DrawingRect().topLeft() + QtCore.QPointF(20, 20)
                    v.panOffset += target - first
                    preview = v.grab().toImage()
                    previewPoint = (target + QtCore.QPointF(sample) * factor) * v.devicePixelRatioF()
                    previewColor = preview.pixelColor(previewPoint.toPoint())
                    expectedColor = rendered.pixelColor(sample)
                    assert max(abs(a - b) for a, b in zip(previewColor.getRgb(), expectedColor.getRgb())) <= 5, (
                        position, texture, strength, previewColor.name(), expectedColor.name())
    print("Title-block texture/vignette composition matches export and preview in both layouts")


if __name__ == "__main__":
    Main()
