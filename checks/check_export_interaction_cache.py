"""Scene caches survive export frame changes; SVG coverage expands on demand."""
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
        for mode in ("Digital", "Architectural"):
            panel.SetScaleOption("scaleMode", mode)
            for kind in ("PNG", "SVG"):
                panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
                panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "Planner", position = "Right"))
                overlay = v.exportOverlay
                overlay.bounds = (0, 0, 12000, 12000)
                panel.SetBounds(overlay.bounds)
                v.grab()
                assert not overlay.previewError
                scene = overlay.snapshot if kind == "PNG" else overlay.svgRenderer
                titleImage = overlay.titleBlockImage
                with patch.object(overlay, "renderVector", wraps = overlay.renderVector) as vectors, \
                        patch.object(overlay, "BuildSnapshot", wraps = overlay.BuildSnapshot) as snapshots:
                    for index in range(3):
                        v.isPanning = True
                        v.panOffset += QtCore.QPointF(10, 0)
                        v.grab()
                        v.isPanning = False
                        overlay.MoveEdge(1, overlay.bounds[0] + overlay.bounds[2] - 100,
                                         modifiers = QtCore.Qt.KeyboardModifier.AltModifier)
                        v.grab()
                        if kind == "PNG":
                            assert overlay.titleBlockImage is titleImage, "Right title block rebuilt when only crop width changed"
                        panel.SetOverride("borderSize", 60 + index)
                        v.grab()
                        assert (overlay.snapshot if kind == "PNG" else overlay.svgRenderer) is scene
                        titleImage = overlay.titleBlockImage
                    panel.SetTitleBlockOption("enabled", False)
                    v.grab()
                    panel.SetTitleBlockOption("enabled", True)
                    v.grab()
                    assert not vectors.called and not snapshots.called, "Frame edits rebuilt the plan"
                    if kind == "SVG":
                        x, y, width, height = overlay.vectorBounds
                        overlay.MoveEdge(1, x + width + 5000, modifiers = QtCore.Qt.KeyboardModifier.AltModifier)
                        v.grab()
                        assert vectors.call_count == 1, "Moving beyond SVG coverage did not expand the cached scene"
                    assert not overlay.previewError
                    assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
                    titleImage = overlay.titleBlockImage
    print("Export scene reuse, title-block bitmap reuse and SVG coverage expansion passed")


if __name__ == "__main__":
    Main()
