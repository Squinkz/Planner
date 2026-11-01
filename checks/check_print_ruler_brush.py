"""Ruler frames cannot inherit an opening's brush and fill over the print page."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
import numpy as np
from PySide6 import QtCore, QtGui, QtSvg
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_export_preview_process import WaitForPreview
from planner_app.models import Wall, BifoldDoor
from planner_app.export_plan import RenderPlan


def Pixels(image):
    image = image.convertToFormat(QtGui.QImage.Format.Format_RGB32)
    return np.frombuffer(image.constBits(), dtype = np.uint8).reshape(image.height(), image.bytesPerLine()).copy()[:, :image.width() * 4].reshape(image.height(), image.width(), 4)


def Main():
    with ExampleWindow() as (main, folder):
        panel, view = main.exportPanel, main.viewport
        main.SetThemes(canvasTheme = "Magnetite Canvas")
        # Cover the painter contract directly, independent of which object
        # currently leaves a filled brush behind after drawing its artwork.
        for allEdges in (False, True):
            for color in ("white", "red"):
                image = QtGui.QImage(view.size(), QtGui.QImage.Format.Format_RGB32)
                image.fill(QtGui.QColor("#167243"))
                with QtGui.QPainter(image) as painter:
                    brush = QtGui.QBrush(QtGui.QColor(color))
                    painter.setBrush(brush)
                    view.DrawRulerFrame(painter, "mm", allEdges = allEdges)
                    assert painter.brush() == brush
                assert image.pixelColor(image.width() // 2, image.height() // 2) == QtGui.QColor("#167243"), "Ruler outline filled the canvas"
        wall = Wall(QtCore.QPointF(-3000, 0), QtCore.QPointF(3000, 0), 200)
        InstallScene(main, [wall, BifoldDoor(wall, .4, .6)])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetOverride("showGrid", False)
        overlay = view.exportOverlay
        # The complete page must contain the same model pixels as a borderless
        # render of its drawing area, rather than merely matching another blank.
        for style in ("Ruler", "Marked", "Ruler + Reference Zones"):
            panel.SetBorder(style)
            for kind in ("png", "svg"):
                job = panel.ExportJobs(folder / ("page." + kind), kind)[0][1]
                complete = RenderPlan(**job)
                reference = RenderPlan(**dict(job, border = "None", ruler = False, pageSize = None))
                if kind == "svg":
                    renders = []
                    for data in (complete, reference):
                        renderer = QtSvg.QSvgRenderer(data)
                        assert renderer.isValid()
                        image = QtGui.QImage(renderer.viewBoxF().size().toSize(), QtGui.QImage.Format.Format_RGB32)
                        image.fill(QtCore.Qt.GlobalColor.white)
                        with QtGui.QPainter(image) as painter:
                            renderer.render(painter)
                        renders.append(image)
                    complete, reference = renders
                expected = Pixels(reference)[2:-2, 2:-2, :3]
                assert np.count_nonzero(np.min(expected, axis = 2) < 200) > 100, "Reference lost its model ink"
                actual = Pixels(complete.copy(overlay.borderSize, overlay.borderSize, reference.width(), reference.height()))[2:-2, 2:-2, :3]
                difference = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
                if kind == "svg" and style == "Ruler + Reference Zones":
                    # Translating the SVG by the larger physical text bands
                    # changes Qt's antialias rounding at a few existing ink
                    # edges (142 pixels, at most 4/255 on Qt 6.11.2). Keep the
                    # interiors exact and reject any displaced/new geometry.
                    yy, xx = np.where(np.any(difference, axis = 2))
                    assert len(xx) <= 256 and difference.max() <= 4, (style, kind, len(xx), int(difference.max()))
                    if len(xx):
                        neighbors = np.stack([expected[np.clip(yy + dy, 0, expected.shape[0] - 1),
                            np.clip(xx + dx, 0, expected.shape[1] - 1)] for dy in (-1, 0, 1) for dx in (-1, 0, 1)])
                        assert np.all(np.max(np.ptp(neighbors.astype(np.int16), axis = 0), axis = 1) > 4), "Changed flat interior pixels"
                else:
                    assert difference.max() <= 1, (style, kind, int(difference.max()), "Ruler frame overwrote drawing pixels")
        # Exercise the real background PNG renderer both at rest and after a
        # crop gesture. Its page image must retain the wall and opening.
        os.environ.pop("PLANNER_SYNCHRONOUS_PREVIEW", None)
        WaitForPreview(view, "png")
        assert len(overlay.printPageCache) == 1
        expected = RenderPlan(**panel.ExportJobs(folder / "settled.png", "png")[0][1])
        assert next(iter(overlay.printPageCache.values())) == expected
        panel.BeginExportGesture()
        overlay.dragEdge = 1
        overlay.MoveEdge(1, overlay.bounds[0] + overlay.bounds[2] + 100, modifiers = QtCore.Qt.KeyboardModifier.AltModifier)
        view.grab()
        overlay.dragEdge = None
        panel.EndExportGesture()
        overlay.printPreviewTimer.stop()
        WaitForPreview(view, "png")
        assert next(iter(overlay.printPageCache.values())) == expected
        os.environ["PLANNER_SYNCHRONOUS_PREVIEW"] = "1"
    print("PASS: stroke-only ruler frames, opening ink in PNG/SVG pages and settled asynchronous PNG after crop drag")


if __name__ == "__main__":
    Main()
