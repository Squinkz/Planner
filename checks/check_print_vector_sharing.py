"""Shared Print model vectors match complete SVGs across page cuts and styles."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
import numpy as np
from PySide6 import QtCore, QtGui
from planner_app.models import Wall, Window, Furnishing, Label
from planner_app.export_plan import RenderPlan
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from fixtures.parity_examples import ExampleWindow, InstallScene


def Main():
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        points = [QtCore.QPointF(1000, 1000), QtCore.QPointF(33000, 1000), QtCore.QPointF(33000, 18000), QtCore.QPointF(1000, 18000)]
        walls = [Wall(points[index], points[(index + 1) % 4], 200) for index in range(4)]
        InstallScene(main, [*walls, Window(walls[0], .2, .3),
                           Furnishing(v.furnishingDefinitions["desk"], QtCore.QPointF(21000, 12000)),
                           Furnishing(v.furnishingDefinitions["washer"], QtCore.QPointF(8000, 7000)),
                           Label(QtCore.QPointF(16000, 9000), "Shared vectors")])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetOverride("canvasTheme", "Light Canvas")
        panel.SetScaleOption("scaleMode", "Print")
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        panel.SetScaleOption("pageOrigin", [0, 0])
        for solidRooms in (False, True):
            panel.SetOverride("solidRooms", solidRooms)
            with patch.object(v.exportOverlay, "renderPrintScene", wraps = v.exportOverlay.renderPrintScene) as sceneRender:
                for position in ("Right", "Bottom"):
                    panel.SetOverride("titleBlock", dict(enabled = True, position = position, projectName = "Shared model",
                                                       drawingTitle = "Ground floor", comments = "Verify on site.", revision = "B"))
                    for border in ("None", "Plain", "Ruler + Reference Zones"):
                        panel.SetBorder(border)
                        layout = panel.PrintLayout()
                        width, height = layout["paperTile"]
                        overlay = v.exportOverlay
                        overlay.bounds = (0, 0, width * 2, height)
                        panel.SetBounds(overlay.bounds)
                        v.zoom = v.DrawingRect().width() / (width * 2.1) / v.basePixelsPerMillimeter
                        point = v.WorldToViewport(QtCore.QPointF(width, height / 2))
                        v.panOffset += v.DrawingRect().center() - point
                        overlay.printPreviewTimer.stop()
                        v.grab()
                        assert not overlay.previewError, overlay.previewError
                        assert sceneRender.call_count <= 1, "Page decoration changes rebuilt the shared model"
                        jobs = panel.ExportJobs(folder / "reference.svg", "svg")
                        for page, (path, arguments) in zip(sorted(overlay.printPageCache), jobs):
                            cached = overlay.printPageCache[page]
                            assert cached.scene is overlay.printVectorRenderer
                            assert isinstance(cached.grid, QtGui.QPicture) and isinstance(cached.decorations, QtGui.QPicture)
                            reference = SvgPreviewRenderer(RenderPlan(**arguments))
                            images = []
                            for renderer in (cached, reference):
                                image = QtGui.QImage(1053, 744, QtGui.QImage.Format.Format_ARGB32)
                                image.fill(QtCore.Qt.GlobalColor.transparent)
                                with QtGui.QPainter(image) as painter:
                                    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
                                    renderer.render(painter)
                                images.append(image)
                            arrays = [np.frombuffer(image.constBits(), dtype = np.uint8).reshape(image.height(), image.width(), 4) for image in images]
                            differences = np.abs(arrays[0].astype(np.int16) - arrays[1].astype(np.int16))
                            mean = float(differences.mean())
                            # Native picture replay and SVG path serialization
                            # can differ slightly at antialiased edges. Reject
                            # moved geometry or visible fill/clip differences.
                            changed = float(np.any(differences > 24, axis = 2).mean())
                            if mean >= .2 or changed >= .006:
                                diagnostic = root / "diagnostics" / "print"
                                diagnostic.mkdir(exist_ok = True)
                                images[0].save(str(diagnostic / "shared-vector-actual.png"))
                                images[1].save(str(diagnostic / "shared-vector-reference.png"))
                            assert mean < .2 and changed < .006, (solidRooms, position, border, page, mean, changed)
                            reference.deleteLater()
                assert not overlay.printVectorRenderer.root.findall(".//{http://www.w3.org/2000/svg}image"), "Shared drawing was rasterized"
                previousCalls = sceneRender.call_count
                flags = {name: not value for name, value in v.measurementVisibility.items()}
                panel.SetOverride("measurementVisibility", flags)
                overlay.printPreviewTimer.stop()
                v.grab()
                assert sceneRender.call_count == previousCalls + 1, "Changed dimension visibility reused stale model vectors"
        shared = overlay.printVectorRenderer
        with patch.object(overlay, "renderPrintScene", side_effect = AssertionError("RGB edits rebuilt the drawing")), \
                patch("planner_app.graphics.svg_preview.SvgClipPath", side_effect = AssertionError("RGB edits reparsed clips")):
            for name, color in (("lines", "#254b78"), ("canvas", "#f3e6ce"), ("grid", "#81796e")):
                panel.PreviewColor(name, QtGui.QColor(color))
                v.grab()
                assert not overlay.previewError, overlay.previewError
                assert overlay.printVectorRenderer is shared
        fresh = SvgPreviewRenderer(panel.RenderPrintScene(overlay.printVectorBounds))
        images = []
        for renderer in (shared, fresh):
            image = QtGui.QImage(1053, 744, QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtCore.Qt.GlobalColor.transparent)
            with QtGui.QPainter(image) as painter:
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
                renderer.render(painter)
            images.append(image)
        arrays = [np.frombuffer(image.constBits(), dtype = np.uint8).astype(np.int16) for image in images]
        assert float(np.abs(arrays[0] - arrays[1]).mean()) < .05, "Recolored model differs from fresh vectors"
        fresh.deleteLater()
        with patch.object(overlay, "renderPrintScene", wraps = overlay.renderPrintScene) as sceneRender:
            panel.SetOverride("linesColor", "#80254b78")
            v.grab()
            assert not overlay.previewError, overlay.previewError
            assert sceneRender.call_count == 1 and overlay.printVectorRenderer is not shared, "Opacity changes reused RGB-only paints"
        # A constrained vector budget retains the old per-page clipping path
        # instead of rejecting a project whose whole-model SVG is too large.
        InstallScene(main, [Wall(QtCore.QPointF(1000, 1000), QtCore.QPointF(5000, 1000), 200)])
        panel.SetOverride("titleBlock", dict(enabled = False))
        panel.SetOverride("showGrid", False)
        panel.SetBorder("None")
        v.viewportRasterByteLimit = 512 * 1024
        overlay.bounds = (0, 0, *panel.PrintLayout()["paperTile"])
        panel.SetBounds(overlay.bounds)
        overlay.ClearPrintPreview()
        overlay.ClearPrintVectors()
        overlay.printPreviewTimer.stop()
        with patch.object(overlay, "renderPrintScene", return_value = b"x" * (v.viewportRasterByteLimit // 2 + 1)) as oversized:
            v.grab()
            assert not overlay.previewError, overlay.previewError
            assert overlay.printVectorBounds is None and oversized.call_count == 1
            assert all(isinstance(page, SvgPreviewRenderer) for page in overlay.printPageCache.values())
            panel.SetBorder("Plain")
            overlay.printPreviewTimer.stop()
            v.grab()
            assert not overlay.previewError and oversized.call_count == 1
            assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
    print("Shared vector geometry, room/grid clipping and page decoration parity passed")


if __name__ == "__main__":
    Main()
