"""Consecutive border widths retain equal frame/corner stroke coverage."""
import math
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow
from planner_app.export_plan import RenderPlan
from planner_app.graphics import palette
from planner_app.graphics.export_border import DrawExportBorder
from planner_app.graphics.preview_bitmap import PictureBitmap
from planner_app.graphics.text import PathTextPainter


def Main():
    with ExampleWindow() as (main, folder):
        main.viewport.showGrid = main.viewport.showMeasurements = False
        data = main.BuildProjectData(includeHistory = False)
        cases = 0
        coverage = {}
        with patch.dict(palette.themeColors, canvas = "#ffffff", rulerBackground = "#ffffff", rulerMajorTick = "#000000"):
            for style in ("Frame", "Corner Marks"):
                for size in range(10, 62):
                    width, height = 500 + 2 * size, 300 + 2 * size
                    crop = QtCore.QRectF(size, size, 500, 300)
                    picture = QtGui.QPicture()
                    with PathTextPainter(picture) as painter:
                        DrawExportBorder(painter, crop, size, style)
                    frame = math.floor(size / 2) + .5
                    along = frame + size / 2
                    for density in (.5, 1, 2):
                        image = QtGui.QImage(round(width * density), round(height * density), QtGui.QImage.Format.Format_ARGB32)
                        image.fill(QtCore.Qt.GlobalColor.white)
                        with PathTextPainter(image) as painter:
                            painter.scale(density, density)
                            DrawExportBorder(painter, crop, size, style)
                        unused, cached = PictureBitmap(picture, QtCore.QRectF(0, 0, width, height), density)
                        # The cached bitmap is transparent only in the drawing
                        # interior; composite onto the same plain white canvas.
                        composited = QtGui.QImage(image.size(), image.format())
                        composited.fill(QtCore.Qt.GlobalColor.white)
                        with QtGui.QPainter(composited) as painter:
                            painter.drawImage(0, 0, cached)
                        assert composited == image, (style, size, density, "Picture preview differs")
                        if density <= 1:
                            exported = RenderPlan(folder / "border.plan", 100, (0, 0, 5000, 3000),
                                projectData = data, applyTheme = False, furnishingDefinitions = main.viewport.furnishingDefinitions,
                                border = style, borderSize = size, rasterSampling = density, preview = density != 1)
                            assert exported.convertToFormat(image.format()) == image, (style, size, density, "PNG export differs")
                        across = round(frame * density)
                        tangent = round(along * density)
                        for axis in (0, 1):
                            profile = [255 - image.pixelColor(tangent, coordinate).red() if axis == 0 else
                                       255 - image.pixelColor(coordinate, tangent).red()
                                       for coordinate in range(across - 3, across + 4)]
                            assert abs(sum(profile) - 255 * density) <= 2, (style, size, density, axis, profile)
                            key = style, density, axis
                            metrics = sum(profile), max(profile), sum(value > 0 for value in profile)
                            previous = coverage.setdefault(key, metrics)
                            assert all(abs(a - b) <= 1 for a, b in zip(metrics, previous)), (style, size, density, axis, profile)
                            if density >= 1:
                                assert metrics[2] == math.ceil(density), (style, size, density, axis, profile)
                                assert max(profile) == 255, (style, size, density, axis, profile)
                        cases += 1
    print("PASS:", cases, "consecutive-width frame/corner stroke profiles; half/native/double density, picture previews and PNG output")


if __name__ == "__main__":
    Main()
