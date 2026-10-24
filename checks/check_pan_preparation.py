"""Camera movement reuses furnishing bounds and culls whole wall contours safely."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner_app.models import Furnishing, Wall
from planner_app.viewport.widget import DrawingViewport
from planner_app.viewport import rendering
from check_pan_dpi import CompareDirect


def Main():
    app = QtWidgets.QApplication([])
    v = DrawingViewport()
    v.resize(1000, 700)
    v.performanceTimer.stop()
    v.showMeasurements = v.showTips = False
    point = QtCore.QPointF
    v.walls = [Wall(point(index * 1400 - 5000, -2000), point(index * 1400 - 4000, -2000)) for index in range(20)]
    v.furnishings = [Furnishing(v.furnishingDefinitions["desk"], point(index * 1600 - 5000, 800)) for index in range(20)]
    v.show()
    app.processEvents()
    v.performanceLabel.hide()
    v.grab()
    v.isPanning = True
    v.grab()
    with patch.object(rendering, "FurnishingArtworkBounds", wraps = rendering.FurnishingArtworkBounds) as bounds:
        with patch.object(v, "DrawDirtyWallOutline", wraps = v.DrawDirtyWallOutline) as outline:
            for delta in (point(3, 1), point(4, -2), point(.7, .3), point(-7, 2)):
                v.panOffset += delta
                v.grab()
            assert bounds.call_count == 0, 'Camera-only movement recomputed world-space artwork bounds'
            assert any(call.kwargs.get("wholeContours") is True for call in outline.call_args_list)
        v.furnishings[0].width += 100
        v.grab()
        assert bounds.call_count > 0, 'Geometry changes must invalidate cached artwork extents'
    for change in ("move", "flip", "visibility", "layer"):
        obj = v.furnishings[1]
        if change == "move":
            obj.firstVertex += point(200, 0)
            obj.secondVertex += point(200, 0)
        elif change == "flip":
            obj.flipHorizontal = not obj.flipHorizontal
        elif change == "visibility":
            v.visibility["Furnishings"] = False
        else:
            v.visibility["Furnishings"] = True
            obj.behindCounters = not obj.behindCounters
        v.panOffset += point(3, 1)
        CompareDirect(v)
    v.isPanning = False
    CompareDirect(v)
    v.close()
    print("PASS: camera-only furnishing preparation reuse, geometry/visibility/layer invalidation and whole-contour pan outlines")


if __name__ == "__main__":
    Main()
