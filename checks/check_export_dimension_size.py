"""Dimension sizes preserve printed height, preview parity and editor isolation."""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
import numpy as np
from PySide6 import QtCore, QtGui, QtSvg
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from planner_app.export_plan import ExportSceneCache, RenderPlan
from planner_app.export_settings import measurementTextSizes, measurementDefaultTextSize
from planner_app.graphics import palette
from planner_app.graphics.scale_bar import ScaleBarLayout
from planner_app.graphics.measurement_text import MeasurementTextPath
from planner_app.graphics.text import PathTextPainter
from planner_app.models import MeasurementGuide, Door
from planner_app.project_codec import DecodeProject
from planner_app.project_recovery import RecoverProject


def DigitHeight(image):
    image = image.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
    pixels = np.frombuffer(image.constBits(), dtype = np.uint8).reshape(image.height(), image.bytesPerLine())
    pixels = pixels[:, :image.width() * 4].reshape(image.height(), image.width(), 4)
    centerX, centerY = image.width() // 2, image.height() // 2
    # Only the central label: endpoints/ticks are well outside this window.
    halfWidth = round(image.width() * .095)
    halfHeight = round(image.height() * .18)
    ink = pixels[centerY - halfHeight:centerY + halfHeight, centerX - halfWidth:centerX + halfWidth, :3].min(axis = 2) < 128
    rows = np.flatnonzero(ink.any(axis = 1))
    assert rows.size, "Dimension label is missing"
    return rows[-1] - rows[0] + 1


def Main():
    with ExampleWindow() as (main, folder):
        panel, viewport = main.exportPanel, main.viewport
        InstallScene(main, [MeasurementGuide(QtCore.QPointF(-2000, 0), QtCore.QPointF(2000, 0))])
        main.sidebarTabs.setCurrentWidget(panel)
        assert [panel.measurementSizeField.itemText(index) for index in range(3)] == ["Small", "Medium", "Large"]
        assert panel.measurementSizeField.currentData() == viewport.measurementTextSize == measurementDefaultTextSize
        assert viewport.MeasurementFont()[0].family() == "D-DIN Condensed"
        assert panel.measurementSizeField.accessibleName() == "Export dimension text size"
        panel.ResetExportHistory()
        beforeKey = viewport.SceneRenderKey(None)
        panel.measurementSizeField.setCurrentText("Small")
        assert viewport.measurementTextSize == panel.overrides["measurementTextSize"] == measurementTextSizes["Small"]
        panel.UndoExport()
        assert viewport.measurementTextSize == measurementDefaultTextSize
        panel.ResetExportHistory()
        panel.measurementSizeField.setCurrentText("Large")
        assert viewport.measurementTextSize == panel.overrides["measurementTextSize"] == 2.5
        assert viewport.SceneRenderKey(None) != beforeKey
        assert len(panel.exportUndoHistory) == 1
        panel.UndoExport()
        assert viewport.measurementTextSize == measurementDefaultTextSize
        panel.RedoExport()
        assert viewport.measurementTextSize == 2.5
        for mode in ("Digital", "Architectural", "Print"):
            panel.SetScaleOption("scaleMode", mode)
            assert panel.RenderArguments("png")["measurementTextSize"] == 2.5
            assert panel.RenderArguments("svg")["measurementTextSize"] == 2.5
        data = main.BuildProjectData(includeHistory = False)
        decoded = DecodeProject(data, viewport.furnishingDefinitions)
        assert decoded[5]["exportSettings"]["measurementTextSize"] == 2.5
        assert "measurementTextSize" not in {key: value for key, value in data["settings"].items() if key != "exportSettings"}
        recovered, repairs = RecoverProject(data, viewport.furnishingDefinitions, main.defaultProjectData)
        assert not repairs and recovered[5]["exportSettings"]["measurementTextSize"] == 2.5
        main.sidebarTabs.setCurrentIndex(0)
        assert viewport.measurementTextSize == 0
        assert viewport.MeasurementFont()[0].family() == "Noto Sans"
        main.ApplyProject(decoded, None)
        main.sidebarTabs.setCurrentWidget(panel)
        assert panel.measurementSizeField.currentData() == viewport.measurementTextSize == 2.5
        legacy = copy.deepcopy(data)
        legacy["settings"]["exportSettings"]["measurementTextSize"] = 3.5
        assert DecodeProject(legacy, viewport.furnishingDefinitions)[5]["exportSettings"]["measurementTextSize"] == 2.5
        legacy["settings"]["exportSettings"]["measurementTextSize"] = 0
        assert DecodeProject(legacy, viewport.furnishingDefinitions)[5]["exportSettings"]["measurementTextSize"] == measurementTextSizes["Small"]
        for invalid in (True, -1, 1.25, 4, "2.5", float("nan")):
            broken = copy.deepcopy(data)
            broken["settings"]["exportSettings"]["measurementTextSize"] = invalid
            try:
                DecodeProject(broken, viewport.furnishingDefinitions)
            except ValueError:
                pass
            else:
                raise AssertionError(invalid)

        # A plain high-contrast scene makes actual printed numeral ink measurable.
        palette.themeColors["canvas"] = "#ffffff"
        palette.themeColors["objectOutline"] = "#000000"
        palette.themeColors["measurementLine"] = "#000000"
        data["settings"].update(showGrid = False, unitsMode = "Millimeters", showMeasurements = True)
        data["settings"]["exportSettings"] = dict(border = "None", showGrid = False)
        arguments = dict(planPath = folder / "dimensions.plan", scale = 300 * 1000 / (25.4 * 100),
                         bounds = (-4000, -2000, 8000, 4000), projectData = data,
                         border = "None", ruler = False, applyTheme = False)
        original = RenderPlan(**arguments, measurementTextSize = measurementTextSizes["Small"])
        assert original == RenderPlan(**arguments, measurementTextSize = 0)
        assert RenderPlan(**arguments) == RenderPlan(**arguments, measurementTextSize = measurementDefaultTextSize)
        currentHeight = DigitHeight(original)
        assert abs(currentHeight * 25.4 / 300 - measurementTextSizes["Small"]) < .15
        for size in measurementTextSizes.values():
            for density in (150, 300, 600):
                image = RenderPlan(**arguments, architecturalScale = 100, dpi = density, measurementTextSize = size)
                actual = DigitHeight(image) * 25.4 / density
                assert abs(actual - size) < .2, (size, density, actual)
            svg = RenderPlan(**arguments, outputFormat = "svg", architecturalScale = 100, measurementTextSize = size)
            assert b"<text" not in svg
            renderer = QtSvg.QSvgRenderer(svg)
            image = QtGui.QImage(renderer.viewBoxF().size().toSize(), QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtCore.Qt.GlobalColor.white)
            with QtGui.QPainter(image) as painter:
                renderer.render(painter)
            assert abs(DigitHeight(image) * 25.4 / 300 - size) < .2
            # Digital has the same design size at its assumed 300 PPI.
            assert abs(DigitHeight(RenderPlan(**arguments, measurementTextSize = size)) * 25.4 / 300 - size) < .2

        cache = ExportSceneCache()
        source = None
        for size in (*measurementTextSizes.values(), measurementTextSizes["Small"]):
            data["settings"]["exportSettings"]["measurementTextSize"] = size
            expected = RenderPlan(**arguments, useExportSettings = True)
            actual = RenderPlan(**arguments, measurementTextSize = size, sceneCache = cache,
                                furnishingDefinitions = viewport.furnishingDefinitions)
            assert actual == expected
            assert cache.viewport.measurementTextSize == size
            if source is not None:
                assert cache.viewport is source, "Text size repeated scene preparation"
            source = cache.viewport
        cache.Clear()

        # The local interactive PNG preview shares the same sizing as file output.
        panel.SetScaleOption("scaleMode", "Digital")
        panel.SetScale(300 * 1000 / (25.4 * 100))
        panel.SetOverride("showGrid", False)
        panel.SetOverride("unitsMode", "Millimeters")
        panel.SetOverride("canvasColor", "#ffffff")
        panel.SetOverride("linesColor", "#000000")
        previousBarKey = None
        for size in measurementTextSizes.values():
            panel.SetOverride("measurementTextSize", size)
            font, spacing = viewport.MeasurementFont()
            assert font.family() == "D-DIN Condensed"
            if size > 0:
                originalPixels = round(viewport.font().pointSizeF() * viewport.logicalDpiY() / 72)
                assert 1 < spacing < font.pixelSize() / originalPixels
                digits = MeasurementTextPath("0123456789", font.toString(), viewport.logicalDpiY()).boundingRect()
                assert 20 * spacing > digits.height() + 4, "Tighter rows clip their numbers"
            layout = ScaleBarLayout(QtCore.QRectF(0, 0, 1600, 900), {}, panel.PreviewScalePerMeter(),
                                    viewport.unitsMode, viewport.font(), measurementTextSize = size)
            assert layout["font"].pixelSize() == (font.pixelSize() if font.pixelSize() > 0 else round(font.pointSizeF() * viewport.logicalDpiY() / 72))
            image = viewport.exportOverlay.CaptureRaster(QtCore.QRectF(-4000, -2000, 8000, 4000), 1, "snapshot")
            expected = size
            assert abs(DigitHeight(image) * 25.4 / 300 - expected) < .2
            overlay = viewport.exportOverlay
            overlay.scaleBar = dict(enabled = True)
            image = QtGui.QImage(1600, 900, QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtCore.Qt.GlobalColor.white)
            with QtGui.QPainter(image) as painter:
                painter.setFont(viewport.font())
                overlay.DrawScaleBarDecoration(painter, QtCore.QRectF(0, 0, 1600, 900), (-4000, -2000, 8000, 4000))
            assert overlay.scaleBarImageKey != previousBarKey, "Size change retained stale scale-bar pixels"
            previousBarKey = overlay.scaleBarImageKey
            for kind in ("png", "svg"):
                with patch("planner_app.graphics.scale_bar.ScaleBarLayout", wraps = ScaleBarLayout) as layoutCall:
                    RenderPlan(**arguments, outputFormat = kind, scaleBar = dict(enabled = True), measurementTextSize = size)
                assert layoutCall.call_count == 1 and layoutCall.call_args.args[7] == size
        main.sidebarTabs.setCurrentIndex(0)
        assert viewport.measurementTextSize == 0
        # Check the rendered stack rows, not just their layout multiplier.
        walls = Rectangle(-2000, -2000, 4000, 4000)
        InstallScene(main, walls + [Door(walls[0], .25, .5)])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetOverride("wallMeasurementMode", "Exterior stacked")
        panel.SetBorder("None")
        drawText = PathTextPainter.drawText
        for size in measurementTextSizes.values():
            panel.SetOverride("measurementTextSize", size)
            rows = []

            def CaptureText(painter, *args):
                if len(args) == 3 and isinstance(args[0], QtCore.QRectF) and args[2].replace(".", "").isdigit():
                    transform = painter.worldTransform()
                    center = transform.map(args[0].center())
                    if abs(transform.m12()) < 1e-8 and center.y() > 7000 * arguments["scale"] / 1000:
                        rows.append(round(center.y(), 5))
                return drawText(painter, *args)

            render = panel.RenderArguments("png")
            render.update(bounds = (-5000, -5000, 10000, 10000), architecturalScale = None, dpi = None, scale = arguments["scale"])
            with patch.object(PathTextPainter, "drawText", CaptureText):
                RenderPlan(**render)
            rows = sorted(set(rows))
            assert len(rows) >= 2, rows
            font, spacing = viewport.MeasurementFont()
            assert all(abs(second - first - 30 * spacing) < .001 for first, second in zip(rows, rows[1:])), (size, rows, spacing)
        main.sidebarTabs.setCurrentIndex(0)
    print("PASS: Medium default, export-only D-DIN dimensions, compact stacks, matched scale-bar sizes, physical PNG/SVG heights and preview/history/persistence")


if __name__ == "__main__":
    Main()
