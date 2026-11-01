"""Print preview reuses page artwork and model context across navigation/selection."""
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
        InstallScene(main, [Wall(QtCore.QPointF(1000, 1000), QtCore.QPointF(5000, 1000), 200)])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetScaleOption("dpi", 96)
        panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "Planner"))
        for kind in ("PNG", "SVG"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
            overlay = v.exportOverlay
            panel.SetScaleOption("pageOrigin", [0, 0])
            width, height = panel.PrintLayout()["paperTile"]
            overlay.bounds = (0, 0, width * 1.8, height * 1.8)
            panel.SetBounds(overlay.bounds)
            v.zoom = v.DrawingRect().width() / (width * 2.5) / v.basePixelsPerMillimeter
            first = v.WorldToViewport(QtCore.QPointF(0, height))
            v.panOffset += v.DrawingRect().topLeft() + QtCore.QPointF(20, 20) - first
            overlay.ClearPrintPreview()
            with patch.object(overlay, "renderPrintPage", wraps = overlay.renderPrintPage) as render, \
                    patch.object(panel, "RenderArguments", wraps = panel.RenderArguments) as capture:
                v.grab()
                assert not overlay.previewError, overlay.previewError
                assert render.call_count == (0 if kind == "SVG" else 1), "Rendered decorations for unselected pages"
                assert capture.call_count == 1, "Rebuilt the project snapshot per page"
                original = overlay.printPageCache[(0, 0, width, height)]
                context = overlay.snapshot
                sharedVectors = overlay.printVectorRenderer
                if kind == "SVG":
                    with patch.object(original, "render", wraps = original.render) as vectors:
                        v.ZoomBy(1.02, v.DrawingRect().center())
                        v.grab()
                        assert not vectors.called, "First zoom replayed a page already in the sharp view"
                        assert overlay.printPageImages
                        overlay.navigationTimer.stop()
                        v.grab()
                        assert vectors.call_count == 1, "Stopping zoom did not restore the sharp vector page"
                render.reset_mock()
                capture.reset_mock()
                v.grab()
                view = overlay.svgViewImage
                v.grab()
                assert not render.called and not capture.called
                if kind == "SVG":
                    assert overlay.svgViewImage is view, "Repeated SVG paints rerasterized the same view"
                    with patch.object(original, "render", wraps = original.render) as vectors:
                        v.grab()
                        assert not vectors.called, "Repeated SVG paints replayed vector paths"
                v.panOffset += QtCore.QPointF(250, 0)
                v.grab()
                v.zoom *= 1.1
                v.grab()
                assert not render.called and not capture.called, "Camera movement rebuilt page content"
                assert overlay.snapshot is context, "Camera movement rebuilt the shared plan context"
                overlay.bounds = (0, 0, width * 1.7, height * 1.8)
                panel.SetBounds(overlay.bounds)
                v.grab()
                assert not render.called, "Crop movement rebuilt unchanged selected pages"
                overlay.bounds = (0, 0, width * 2, height)
                panel.SetBounds(overlay.bounds)
                v.grab()
                assert render.call_count == (0 if kind == "SVG" else 1), "Selecting a new page rebuilt existing pages"
                assert overlay.printPageCache[(0, 0, width, height)] is original
                assert not capture.called, "New pages duplicated project preparation"
                render.reset_mock()
                overlay.bounds = (0, 0, width * 1.8, height)
                panel.SetBounds(overlay.bounds)
                v.grab()
                overlay.bounds = (0, 0, width * 2, height)
                panel.SetBounds(overlay.bounds)
                v.grab()
                assert not render.called, "Reselecting a cached page rerendered it"
                if kind == "SVG":
                    v.isPanning = True
                    v.panOffset += QtCore.QPointF(10, 0)
                    v.grab()
                    navigation = dict(overlay.printPageImages)
                    with patch.object(original, "render", wraps = original.render) as vectors:
                        v.panOffset += QtCore.QPointF(10, 0)
                        v.grab()
                        assert not vectors.called, "SVG navigation replayed cached vector paths"
                    assert all(overlay.printPageImages[page] is image for page, image in navigation.items())
                    v.isPanning = False
                overlay.dragPage = 0
                panel.SetScaleOption("pageOrigin", [100, 0])
                render.reset_mock()
                v.grab()
                assert render.called and all(call.kwargs.get("decorationsOnly") for call in render.call_args_list), "Offset drag rebuilt the plan per page"
                render.reset_mock()
                v.grab()
                assert not render.called, "An unchanged drag frame rebuilt decorations"
                assert overlay.snapshot is context, "Offset drag discarded the shared plan context"
                panel.SetTitleBlockOption("projectName", "Updated during preview")
                v.grab()
                assert overlay.printRenderArguments["titleBlock"]["projectName"] == "Updated during preview", "Prepared settings remained stale"
                overlay.dragPage = None
                overlay.printPreviewTimer.stop()
                v.grab()
                if kind == "SVG":
                    assert not render.called
                    assert overlay.printVectorRenderer is sharedVectors
                else:
                    assert render.called
                    assert any(not call.kwargs.get("decorationsOnly", False) for call in render.call_args_list)
                assert not overlay.previewError
                assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
                # Border editing uses cached context and cheap decorations;
                # full page artwork is rebuilt only after the edit settles.
                render.reset_mock()
                context = overlay.snapshot
                panel.SetOverride("borderSize", panel.overrides.get("borderSize", 56) + 4)
                v.grab()
                assert render.called and all(call.kwargs.get("decorationsOnly", False) for call in render.call_args_list)
                assert overlay.snapshot is context
                render.reset_mock()
                v.grab()
                assert not render.called, "An unchanged decoration frame was rebuilt"
                overlay.printPreviewTimer.stop()
                v.grab()
                if kind == "SVG":
                    assert not render.called
                    assert overlay.printVectorRenderer is sharedVectors
                else:
                    assert render.called
                    assert all(not call.kwargs.get("decorationsOnly", False) for call in render.call_args_list)
    print("Print cache reuse, selected-only rendering, SVG navigation and cheap offset dragging passed")


if __name__ == "__main__":
    Main()
