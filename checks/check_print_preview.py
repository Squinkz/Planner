"""Whole-paper preview decorates selected pages only and matches their output."""
import base64
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui
from planner_app.export_plan import RenderPlan
from planner_app.graphics.title_block import TitleBlockLayout, TitleBlockCells
from planner_app.print_layout import SelectedPrintPages
from planner_app.export_settings import ExportBorderSize
from fixtures.parity_examples import ExampleWindow


def Main():
    assert SelectedPrintPages((1, 0, 199, 200), (100, 200)) == [(100, 0, 100, 200)]
    assert SelectedPrintPages((1, 1, 199, 399), (100, 200)) == [(100, 200, 100, 200)]
    assert SelectedPrintPages((0, 0, 99, 200), (100, 200)) == []
    assert SelectedPrintPages((0, 0, 100, 199), (100, 200)) == []
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetScaleOption("dpi", 96)
        panel.SetOverride("canvasColor", "#ffffff")
        panel.SetOverride("linesColor", "#202020")
        panel.SetOverride("borderColor", "#cc0000")
        panel.SetOverride("showGrid", False)
        panel.SetBorder("Plain")
        panel.SetOverride("borderWidth", 500)
        logo = QtGui.QImage(180, 90, QtGui.QImage.Format.Format_RGB32)
        logo.fill(QtGui.QColor("#0064ff"))
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        assert logo.save(buffer, "PNG")
        encoded = base64.b64encode(bytes(buffer.data())).decode("ascii")
        for orientation in ("Landscape", "Portrait"):
            panel.pageOrientationButtons[orientation].click()
            panel.SetScaleOption("pageOrigin", [0, 0])
            for position in ("Right", "Bottom"):
                panel.SetOverride("titleBlock", dict(enabled = True, position = position, logoMode = "Custom", logo = encoded,
                    projectName = "Preview matches output", sheetNumber = "UNCHANGED"))
                layout = panel.PrintLayout()
                width, height = layout["paperTile"]
                v.exportOverlay.bounds = (0, 0, width * 2, height)
                panel.SetBounds(v.exportOverlay.bounds)
                view = v.DrawingRect()
                v.zoom = min(view.width() / (width * 2), view.height() / height) * .9 / v.basePixelsPerMillimeter
                first = v.WorldToViewport(QtCore.QPointF(0, height))
                v.panOffset += view.topLeft() + QtCore.QPointF(20, 20) - first
                for kind in ("PNG", "SVG"):
                    v.exportOverlay.printPreviewTimer.stop()
                    panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
                    preview = v.grab().toImage()
                    overlay = v.exportOverlay
                    assert not overlay.previewError, overlay.previewError
                    jobs = panel.ExportJobs(folder / "preview.png", "png")
                    assert len(jobs) == 2
                    assert jobs[1][1]["bounds"][0] == jobs[0][1]["bounds"][0] + jobs[0][1]["bounds"][2], "Title blocks left a gap in plan content"
                    border = ExportBorderSize(panel.overrides)
                    baseWidth = layout["drawingPixels"][0] + 2 * border
                    baseHeight = layout["drawingPixels"][1] + 2 * border
                    outputWidth, outputHeight, block = TitleBlockLayout(baseWidth, baseHeight, panel.TitleBlockOptions(),
                        panel.PreviewScalePerMeter(), 100, kind.lower(), 300, fitWidth = position == "Bottom", pageSize = layout["paper"])
                    logoCell = next(cell for name, label, value, cell in TitleBlockCells(block, panel.TitleBlockOptions(),
                        panel.PreviewScalePerMeter(), 100, kind.lower(), 300, fitWidth = position == "Bottom", pageSize = layout["paper"]) if name == "logo")
                    for index in range(2):
                        page = (index * width, 0, width, height)
                        assert page in overlay.printPageCache
                        target = overlay.PrintPageRect(page)
                        for point, color in ((logoCell.center(), QtGui.QColor("#0064ff")),
                                             (QtCore.QPointF(border / 2, layout["baselinePixels"][1] * .5), QtGui.QColor("#cc0000"))):
                            sample = target.topLeft() + QtCore.QPointF(point.x() * target.width() / layout["baselinePixels"][0],
                                                                      point.y() * target.height() / layout["baselinePixels"][1])
                            actual = preview.pixelColor((sample * v.devicePixelRatioF()).toPoint())
                            assert max(abs(a - b) for a, b in zip(actual.getRgb(), color.getRgb())) <= 1, (orientation, position, kind, actual.name(), color.name())
                        if kind == "PNG":
                            expected = RenderPlan(**jobs[index][1])
                            if overlay.printPageCache[page] != expected:
                                diagnostic = root / "diagnostics" / "print"
                                diagnostic.mkdir(exist_ok = True)
                                overlay.printPageCache[page].save(str(diagnostic / "page-actual.png"))
                                expected.save(str(diagnostic / "page-expected.png"))
                            assert overlay.printPageCache[page] == expected, ("Page preview differs from its exported pixels", orientation, position, index, overlay.printPageSampling[page])
                    cache = dict(overlay.printPageCache)
                    overlay.bounds = (0, 0, width * 1.5, height)
                    panel.SetBounds(overlay.bounds)
                    assert len(panel.ExportJobs(folder / "partial.png", "png")) == 1
                    dimmed = v.grab().toImage()
                    assert all(overlay.printPageCache[page] is image for page, image in cache.items()), "Crop selection rebuilt page artwork"
                    second = overlay.PrintPageRect((width, 0, width, height))
                    sample = second.topLeft() + QtCore.QPointF(logoCell.center().x() * second.width() / layout["baselinePixels"][0],
                                                               logoCell.center().y() * second.height() / layout["baselinePixels"][1])
                    assert dimmed.pixelColor((sample * v.devicePixelRatioF()).toPoint()) != QtGui.QColor("#0064ff"), "Partial page retained its logo"
                    borderPoint = second.topLeft() + QtCore.QPointF(border / 2 * second.width() / layout["baselinePixels"][0], second.height() * .5)
                    assert dimmed.pixelColor((borderPoint * v.devicePixelRatioF()).toPoint()) != QtGui.QColor("#cc0000"), "Partial page retained its border"
                    overlay.bounds = (0, 0, width * 2, height)
                    panel.SetBounds(overlay.bounds)
                diagnostics = root / "diagnostics" / "print"
                diagnostics.mkdir(exist_ok = True)
                QtCore.QCoreApplication.processEvents()
                button = panel.pageOrientationButtons[orientation]
                assert button.visibleRegion().boundingRect().height() == button.height(), "Orientation buttons were clipped by the print controls"
                main.grab().save(str(diagnostics / f"full-pages-{orientation.lower()}-{position.lower()}.png"))
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        oldLimit = v.viewportRasterByteLimit
        v.viewportRasterByteLimit = 64 * 1024
        v.grab()
        assert not v.exportOverlay.previewError
        assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
        v.viewportRasterByteLimit = oldLimit
    print("Selected-page PNG/SVG previews, undecorated context and raster budgeting passed")


if __name__ == "__main__":
    Main()
