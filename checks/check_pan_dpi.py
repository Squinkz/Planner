"""Whole-physical-pixel pan reuse and fresh-render comparisons at fractional DPI."""
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner_app.models import Wall, Door, BifoldDoor, Stair, Furnishing, Label
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.viewport.widget import DrawingViewport


def CompareDirect(v):
    cached = v.grab().toImage()
    pan = (v.viewportPanRaster, v.viewportPanKey, v.viewportPanOrigin, v.viewportPanState)
    limit = v.viewportSceneByteLimit
    v.viewportSceneByteLimit = 0
    direct = v.grab().toImage()
    v.viewportSceneByteLimit = limit
    v.viewportPanRaster, v.viewportPanKey, v.viewportPanOrigin, v.viewportPanState = pan
    if cached != direct:
        first, second = memoryview(cached.constBits()), memoryview(direct.constBits())
        changed = [index for index, (a, b) in enumerate(zip(first.cast("I"), second.cast("I"))) if a != b]
        maximumDifference = max(abs(first[index * 4 + channel] - second[index * 4 + channel]) for index in changed for channel in range(4))
        # Qt can round antialiasing differently when a diagonal crosses a new
        # viewport/strip clip. Keep a small color tolerance, never geometric drift.
        if maximumDifference <= 3 and len(changed) <= max(64, cached.width() * cached.height() // 1000):
            return
        samples = [(index % cached.width(), index // cached.width(),
                    cached.pixelColor(index % cached.width(), index // cached.width()).getRgb(),
                    direct.pixelColor(index % cached.width(), index // cached.width()).getRgb()) for index in changed[:12]]
        cached.save(str(Path(__file__).resolve().parent.parent / "diagnostics/pan-dpi-cached.png"))
        direct.save(str(Path(__file__).resolve().parent.parent / "diagnostics/pan-dpi-direct.png"))
        raise AssertionError((v.devicePixelRatioF(), v.size(), v.zoom, v.panOffset, maximumDifference, len(changed), samples))


def Child():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    v = DrawingViewport()
    v.performanceTimer.stop()
    point = QtCore.QPointF
    wall = Wall(point(-2400, 1800), point(2400, 1800), material = "Brick")
    branch = Wall(point(2400, 1800), point(1800, -1800), 180)
    v.walls = [wall, branch, Stair(point(-1000, 1000), point(-1000, -1600), 750)]
    v.windows = [Door(wall, .1, .3), BifoldDoor(branch, .25, .55)]
    desk = Furnishing(v.furnishingDefinitions["desk"], point())
    desk.angle = 31
    v.furnishings = [desk]
    label = Label(point(-1700, -2200), "DPI preview\nj\u0301 Åg", .6)
    label.angle = 31
    label.width *= .8
    v.labels = [label]
    v.showMeasurements = False
    v.show()
    app.processEvents()
    v.performanceLabel.hide()
    ratio = v.devicePixelRatioF()
    reused = 0
    for width, height, measurements in ((1000, 700, False), (1001, 701, False),
                                        (1000, 700, True), (1001, 701, True)):
        v.showMeasurements = measurements
        v.resize(width, height)
        for zoom in (.4, 1.1):
            v.zoom = zoom
            v.panOffset = point(.3, -.7)
            v.isPanning = True
            v.viewportPanRaster = None
            v.grab()
            for dx, dy in ((1, 0), (-3, 2), (0, -1), (2, 3)):
                v.panOffset += point(dx / ratio, dy / ratio)
                with patch.object(v, "DrawGridBackground", wraps = v.DrawGridBackground) as grid:
                    v.grab()
                    assert sum(call.kwargs.get("gridOnly", False) for call in grid.call_args_list) == 1, (ratio, width, height)
                reused += 1
                CompareDirect(v)
            # Nonintegral device movement keeps a fresh, unfiltered render.
            v.panOffset += point(.25 / ratio, .4 / ratio)
            with patch.object(v, "DrawGridBackground", wraps = v.DrawGridBackground) as grid:
                v.grab()
                assert not any(call.kwargs.get("gridOnly", False) for call in grid.call_args_list)
            CompareDirect(v)
            v.isPanning = False
            with patch.object(v, "DrawScene", wraps = v.DrawScene) as draw:
                v.grab()
                assert draw.call_count == 0, "Release rebuilt the scene"
            CompareDirect(v)
    v.close()
    print(f"DPR {ratio}: {reused} reused frames, fresh-render comparisons including odd sizes and fractional fallback")


def Main():
    if "--child" in sys.argv:
        Child()
        return
    for ratio in (1, 1.25, 1.5, 1.75, 2):
        environment = dict(os.environ, QT_SCALE_FACTOR = str(ratio))
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child"],
                                env = environment, capture_output = True, text = True, timeout = 15)
        assert result.returncode == 0, (ratio, result.stdout, result.stderr)
        print(result.stdout.strip())


if __name__ == "__main__":
    Main()
