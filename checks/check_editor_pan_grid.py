"""Live editor panning preserves solid-room grids and skips inactive hover work."""
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"


def Child():
    from PySide6 import QtCore, QtGui, QtWidgets
    from planner_app.viewport.widget import DrawingViewport
    from planner_app.models import Wall
    from check_room_detection import Rectangle
    from check_pan_dpi import CompareDirect
    app = QtWidgets.QApplication([])
    view = DrawingViewport()
    view.resize(1001, 701)
    view.performanceTimer.stop()
    view.showTips = view.showMeasurements = False
    view.walls = Rectangle(-1800, -1200, 3600, 2400)
    view.solidRooms = view.showGrid = True
    view.zoom = .8
    view.show()
    app.processEvents()
    view.performanceLabel.hide()
    point = QtCore.QPointF
    ratio = view.devicePixelRatioF()
    for units in ("Millimeters", "Feet and Inches"):
        view.unitsMode = units
        for floors in (False, True):
            view.floors = floors
            view.panOffset = point(.3, -.7)
            view.viewportPanRaster = None
            view.isPanning = True
            view.grab()
            for delta in (point(1, 0), point(-3, 2), point(0, -1), point(2, 3), point(.3, .4)):
                view.panOffset += delta / ratio
                CompareDirect(view)
            view.showGrid = False
            CompareDirect(view)
            view.showGrid = True
            CompareDirect(view)
    # Panning has no hover target. It must not inspect every unselected wall
    # for nearby handles, while explicit selection handles stay visible.
    view.walls = [Wall(point(-1000, 0), point(1000, 0), 240)]
    view.floors = view.solidRooms = view.showGrid = False
    view.SetSelection([], notify = False)
    view.hoverPosition = view.WorldToViewport(view.walls[0].firstVertex)
    view.isPanning = True
    view.grab()
    with patch.object(view, "ObjectFootprint", wraps = view.ObjectFootprint) as footprints, patch.object(view, "HitTest", wraps = view.HitTest) as hits:
        view.panOffset += point(3, 1) / ratio
        view.grab()
        assert footprints.call_count == 0, footprints.call_args_list
        assert hits.call_count == 0
    view.SetSelection([(view.walls[0], 0)])
    image = view.grab().toImage()
    position = (view.WorldToViewport(view.walls[0].firstVertex) * ratio).toPoint()
    assert image.pixelColor(position).name() == QtGui.QColor(view.SelectionColor(view.walls[0])).name()
    CompareDirect(view)
    view.isPanning = False
    view.close()
    print("PASS: DPR", ratio, "live solid-room panning, units/grid changes, no unselected hover scans and retained selected handles")


if __name__ == "__main__":
    if "--child" in sys.argv:
        Child()
    else:
        for ratio in (1, 1.25):
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child"],
                env = dict(os.environ, QT_SCALE_FACTOR = str(ratio)), capture_output = True, text = True, timeout = 20)
            assert result.returncode == 0, result.stdout + result.stderr
            print(result.stdout.strip())
