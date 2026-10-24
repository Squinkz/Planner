"""SVG solid-fill switches reuse bounded vectors and invalidate real edits."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from furnishings import Furnishing
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.graphics.svg_preview import SvgPreviewRenderer


def RenderImage(renderer):
    image = QtGui.QImage(renderer.defaultSize(), QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    with QtGui.QPainter(image) as painter:
        renderer.render(painter)
    return image


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    main = MainWindow()
    v, panel = main.viewport, main.exportPanel
    v.walls = []
    v.furnishings = [Furnishing(v.furnishingDefinitions["desk"]),
                    Furnishing(v.furnishingDefinitions["washer"], QtCore.QPointF(600, 100))]
    v.sceneRevision += 1
    main.sidebarTabs.setCurrentWidget(panel)
    panel.SetOverride("visibility", True, "Furnishings")
    panel.borderField.setCurrentText("None")
    panel.scaleField.setValue(100)
    panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
    overlay = v.exportOverlay
    renderers = {}
    for solid in (True, False):
        panel.solidObjectsField.setChecked(solid)
        v.grab()
        assert not overlay.previewError, overlay.previewError
        renderers[solid] = overlay.svgRenderer
    with patch.object(overlay, "renderVector", side_effect = AssertionError("Repeated toggle regenerated SVG")):
        for solid in (True, False, True):
            panel.solidObjectsField.setChecked(solid)
            v.grab()
            assert not overlay.previewError, overlay.previewError
            assert overlay.svgRenderer is renderers[solid]
        panel.PreviewColor("canvas", QtGui.QColor("#abc123"))
        panel.PreviewColor("lines", QtGui.QColor("#789def"))
        v.grab()
        panel.solidObjectsField.setChecked(False)
        v.grab()
        assert not overlay.previewError, overlay.previewError
        assert RenderImage(overlay.svgRenderer) == RenderImage(SvgPreviewRenderer(panel.Render("svg", preview = True, previewScene = True)))
    with patch.object(overlay, "renderVector", wraps = overlay.renderVector) as render:
        v.furnishings[0].firstVertex.setX(80)
        v.grab()
        assert render.call_count == 1, "Geometry edit reused stale solid-fill cache"
        assert not overlay.previewError, overlay.previewError
        panel.solidObjectsField.setChecked(True)
        v.grab()
        assert render.call_count == 2, "Geometry edit retained the stale alternate"
    assert overlay.svgAlternate is not None
    overlay.SetActive(False)
    assert overlay.svgAlternate is None and overlay.svgRenderer is None
    main.MarkProjectClean()
    main.close()


if __name__ == "__main__":
    Main()
