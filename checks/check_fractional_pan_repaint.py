"""Fresh fractional pan pixels, bounded surface recycling and opening re-entry."""
import math
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"


def SceneImage(view, panning):
    from PySide6 import QtCore, QtGui
    from planner_app.graphics.palette import themeColors
    view.isPanning = panning
    ratio = view.devicePixelRatioF()
    image = QtGui.QImage(math.ceil(view.width() * ratio), math.ceil(view.height() * ratio), QtGui.QImage.Format.Format_ARGB32)
    image.setDevicePixelRatio(ratio)
    image.fill(QtGui.QColor(themeColors["canvas"]))
    with QtGui.QPainter(image) as painter:
        painter.setClipRect(view.DrawingRect())
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        view.DrawScene(painter, view.DrawingRect(), view.WorldToViewport(QtCore.QPointF()),
                       view.basePixelsPerMillimeter * view.zoom, drawAnnotations = False)
    return image


def Child():
    from PySide6 import QtCore, QtWidgets
    from planner_app.models import Wall, Fireplace
    from planner_app.object_schema import openingClasses
    from planner_app.viewport.widget import DrawingViewport
    from planner_app.viewport import rendering
    from check_pan_dpi import CompareDirect
    app = QtWidgets.QApplication([])
    view = DrawingViewport()
    view.resize(801, 603)
    view.showTips = view.showMeasurements = False
    view.performanceTimer.stop()
    point = QtCore.QPointF
    wall = Wall(point(-3000, 0), point(3000, 0), 240)
    view.walls = [wall]
    view.show()
    app.processEvents()
    view.performanceLabel.hide()
    ratio = view.devicePixelRatioF()
    frameBytes = math.ceil(view.width() * ratio) * math.ceil(view.height() * ratio) * 4
    view.viewportRasterByteLimit = frameBytes
    view.SetRenderDiagnosticsEnabled(True)
    view.isPanning = True
    view.grab()
    for change in ("camera", "geometry", "grid", "zoom"):
        if change == "geometry": wall.secondVertex += point(200, 75)
        elif change == "grid": view.showGrid = False
        elif change == "zoom": view.zoom *= 1.2
        view.renderDiagnostics.events.clear()
        view.panOffset += point(.31, .43) / ratio
        with patch.object(view, "DrawGridBackground", wraps = view.DrawGridBackground) as grid:
            view.grab()
            assert sum(call.kwargs.get("drawGrid") is False for call in grid.call_args_list) == 1
        assert not any(event.get("kind") == "rasterCache" and event.get("action") == "allocation"
                       for event in view.renderDiagnostics.events), change
        assert view.rasterCacheBudget.RetainedBytes() == frameBytes
        CompareDirect(view)
    view.resize(843, 625)
    view.panOffset += point(.21, -.37) / ratio
    CompareDirect(view)
    view.SetRenderDiagnosticsEnabled(False)
    view.viewportRasterByteLimit = 128 * 1024 * 1024
    # Isolate native symbols from pan-specific wall stroke reuse. Compare each
    # family to uncropped native painting, including artwork reaching in from
    # an offscreen wall and a fireplace deeper than its opening span.
    view.viewportSceneByteLimit = 0
    view.zoom = .8
    view.showGrid = False
    comparisons = 0
    for index, kind in enumerate(openingClasses.values()):
        axis = point(800, 0) if index % 2 else point(0, 800)
        wall = Wall(-axis, axis, 240)
        opening = kind(wall, .2, .8)
        if hasattr(opening, "windowWell"):
            opening.windowWell, opening.wellDepth, opening.wellDashed = True, 1800, True
        if hasattr(opening, "sillDepth"): opening.sillDepth = 1200
        if hasattr(opening, "swingsOutwards"): opening.swingsOutwards = True
        if isinstance(opening, Fireplace):
            opening.depth = 16000
            opening.depthOffset = 7000
        view.walls, view.windows = [wall], [opening]
        for style in ("Material", "Outline", "Solid"):
            view.wallStyle = style
            for offset in (point(.31, -.43), point(650.31, -.43), point(.31, 650.43), point(-650.31, -650.43)):
                view.panOffset = offset
                expected = SceneImage(view, False)
                actual = SceneImage(view, True)
                assert actual == expected, (ratio, kind.__name__, style, offset)
                comparisons += 1
    view.windows = [openingClasses["Door"](wall, .2, .8)]
    view.panOffset = point(10000.31, 10000.43)
    with patch.object(rendering, "DrawOpeningSymbol", wraps = rendering.DrawOpeningSymbol) as symbols:
        SceneImage(view, True)
        assert symbols.call_count == 0, "Offscreen symbols were still rendered"
    view.close()
    print("PASS: DPR", ratio, comparisons, "exact opening images, fractional repaint recycling, scene changes and budget/resize fallback")


if __name__ == "__main__":
    if "--child" in sys.argv:
        Child()
    else:
        for ratio in (1, 1.25):
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child"],
                env = dict(os.environ, QT_SCALE_FACTOR = str(ratio)), capture_output = True, text = True, timeout = 20)
            assert result.returncode == 0, result.stdout + result.stderr
            print(result.stdout.strip())
