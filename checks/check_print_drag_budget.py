"""Zoomed Print edits replace unused page rasters without transient budget errors."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall


def Main():
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(1000, 1000), QtCore.QPointF(5000, 3500), 200)])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetScaleOption("dpi", 600)
        panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "None"))
        panel.SetScaleOption("pageOrigin", [0, 0])
        overlay = v.exportOverlay
        width, height = panel.PrintLayout()["paperTile"]
        overlay.bounds = (0, 0, width, height)
        panel.SetBounds(overlay.bounds)
        v.zoom = 4 / v.basePixelsPerMillimeter
        point = v.WorldToViewport(QtCore.QPointF(width / 2, height / 2))
        v.panOffset += v.DrawingRect().center() - point
        for kind in ("PNG", "SVG"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
            v.viewportRasterByteLimit = 24 * 1024 * 1024
            overlay.ClearPrintPreview()
            overlay.printPreviewTimer.stop()
            v.grab()
            assert not overlay.previewError and overlay.printPageCache, overlay.previewError
            context = overlay.snapshot
            with patch.object(overlay, "renderPrintPage", wraps = overlay.renderPrintPage) as render:
                finalText = "Writing while zoomed in " + kind
                for text in ("W", "Wr", "Writing", finalText):
                    panel.SetTitleBlockOption("preparedBy", text)
                    overlay.printPreviewTimer.start()
                    v.grab()
                    assert not overlay.previewError, overlay.previewError
                    assert overlay.printDragImages, "Typing bypassed the fast decoration preview"
                    assert overlay.snapshot is context
                    assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
                assert render.called and all(call.kwargs.get("decorationsOnly") for call in render.call_args_list)
            overlay.printPreviewTimer.stop()
            v.grab()
            assert not overlay.previewError and overlay.printPageCache, overlay.previewError
            assert not overlay.printDragImages
            assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
            for text in (finalText + "x", finalText):
                panel.SetTitleBlockOption("preparedBy", text)
                overlay.printPreviewTimer.start()
                v.grab()
                assert not overlay.previewError, overlay.previewError
                assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
            assert not overlay.printDragImages, "Returning to the original text retained temporary page images"
            overlay.printPreviewTimer.stop()
    print("Zoomed Print typing keeps fast/final previews within the raster budget")


if __name__ == "__main__":
    Main()
