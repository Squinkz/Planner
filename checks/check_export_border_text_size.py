"""Export ruler/zone labels share dimension ink height and fit their border bands."""
import math
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.export_plan import RenderPlan
from planner_app.export_settings import BorderSize, measurementTextSizes
from planner_app.graphics.measurement_text import MeasurementTextPath
from planner_app.graphics.text import PathTextPainter
from planner_app.models import Wall


def Main():
    with ExampleWindow() as (main, folder):
        view, panel = main.viewport, main.exportPanel
        InstallScene(main, [Wall(QtCore.QPointF(-3000, 0), QtCore.QPointF(3000, 0), 200)])
        main.SetThemes(canvasTheme = "Light Canvas")
        view.showGrid = view.showMeasurements = view.showTips = False
        editor = view.grab().toImage()
        data = main.BuildProjectData(includeHistory = False)
        calls = []
        drawText = PathTextPainter.drawText

        def RecordText(painter, *args):
            font = painter.font()
            transform = painter.worldTransform()
            height = MeasurementTextPath("0", font.toString(), painter.device().logicalDpiY()).boundingRect().height()
            calls.append((str(args[-1]), font, QtCore.QRectF(args[0]),
                          height * math.hypot(transform.m21(), transform.m22())))
            return drawText(painter, *args)

        count = 0
        for name, size in measurementTextSizes.items():
            for style in ("Ruler", "Reference Zones", "Ruler + Reference Zones"):
                for kind, dpi in (("png", 300), ("png", 600), ("svg", 300)):
                    calls.clear()
                    with patch.object(PathTextPainter, "drawText", RecordText):
                        result = RenderPlan(folder / "border.plan", 100, (-4000, -2000, 8000, 4000),
                            projectData = data, furnishingDefinitions = view.furnishingDefinitions, applyTheme = False,
                            outputFormat = kind, architecturalScale = 100, dpi = dpi,
                            border = style, borderSize = 1, measurementTextSize = 1.5, borderTextSize = size)
                    assert calls, (name, style, kind)
                    for text, font, rect, height in calls:
                        assert font.family() == "D-DIN Condensed", (name, style, text, font.family())
                        assert abs(height * 25.4 / dpi - size) < .06, (name, style, kind, text, height, dpi)
                        metrics = QtGui.QFontMetricsF(font)
                        assert rect.height() >= metrics.height(), (name, style, text, rect, metrics.height())
                        assert rect.width() >= metrics.horizontalAdvance(text), (name, style, text, rect)
                    if kind == "svg":
                        assert b"<text" not in result and b"<image" not in result
                    elif name == "Medium" and style == "Ruler + Reference Zones" and dpi == 300:
                        result.save(str(folder / "medium-border.png"))
                        destination = Path(__file__).resolve().parents[1] / "diagnostics"
                        destination.mkdir(exist_ok = True)
                        result.save(str(destination / "export-border-medium.png"))
                        result.copy(0, 0, min(800, result.width()), min(180, result.height())).save(str(destination / "export-border-medium-detail.png"))
                    count += 1
        # UI, page drawing area, source rasters and vector decorations agree on
        # both font and border size in every mode, including fixed-width borders.
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetOverride("borderSize", 128)
        for mode in ("Digital", "Architectural", "Print"):
            panel.SetScaleOption("scaleMode", mode)
            if mode != "Digital":
                panel.SetOverride("borderWidth", 128 * 1000 / panel.PreviewScalePerMeter())
            panel.SetScaleOption("dpi", 96)
            for kind in ("PNG", "SVG"):
                panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
                for style in ("Ruler", "Reference Zones", "Ruler + Reference Zones"):
                    panel.SetBorder(style)
                    previous = None
                    model = None
                    for name, size in measurementTextSizes.items():
                        panel.borderTextSizeField.setCurrentText(name)
                        assert panel.borderSizeSlider.minimum() == BorderSize(style, 1, size)
                        assert view.exportOverlay.borderSize == 128
                        assert abs(panel.borderSizeField.value() - 128 * panel.borderSizeUnitFactor) <= 10 ** -panel.borderSizeField.decimals()
                        view.exportOverlay.printPreviewTimer.stop()
                        view.grab()
                        assert not view.exportOverlay.previewError, (mode, kind, style, name, view.exportOverlay.previewError)
                        overlay = view.exportOverlay
                        key = overlay.printPageKey if mode == "Print" else overlay.rulerPictureKey
                        assert key != previous, (mode, kind, style, "Font change reused stale decorations")
                        previous = key
                        if mode == "Print" and kind == "SVG":
                            assert model is None or overlay.printVectorRenderer is model, "Border text size rebuilt model vectors"
                            model = overlay.printVectorRenderer
        main.sidebarTabs.setCurrentWidget(main.buildScrollArea)
        assert view.measurementTextSize == 0
        assert view.grab().toImage() == editor, "Export sizing changed the editor rulers"
    print("PASS:", count, "PNG/SVG physical ruler/zone font cases at 300/600 PPI; label fit, all-mode preview invalidation, border minimums and editor isolation")


if __name__ == "__main__":
    Main()
