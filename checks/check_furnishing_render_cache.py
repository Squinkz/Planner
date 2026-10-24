"""View changes reuse validation; geometry edits invalidate it without changing pixels."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall
from furnishings import Furnishing


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    v = window.viewport
    point = QtCore.QPointF
    desk = Furnishing(v.furnishingDefinitions["desk"])
    wall = Wall(point(-1500, 1500), point(1500, 1500), 200)
    v.walls = [wall]
    v.furnishings = [desk]
    with patch.object(v, "FurnishingFits", wraps = v.FurnishingFits) as fits:
        v.grab()
        assert fits.call_count == 1
        for zoom, pan in ((.5, point(15, 25)), (1, point(-40, 30)), (1.5, point(20, 20))):
            v.zoom, v.panOffset = zoom, pan
            v.grab()
        assert fits.call_count == 1
        desk.angle = 30
        v.grab()
        assert fits.call_count == 2
        desk.width = 1400
        v.grab()
        assert fits.call_count == 3
        before = v.CaptureState()
        wall.firstVertex = point(-1500, 0)
        wall.secondVertex = point(1500, 0)
        v.grab()
        assert fits.call_count == 4 and v.furnishingValidationCache[id(desk)][1]
        v.RecordEdit(before)
        v.Undo()
        v.grab()
        assert not v.furnishingValidationCache[id(desk)][1]
        v.Redo()
        v.grab()
        assert v.furnishingValidationCache[id(desk)][1]
        offscreen = Furnishing(desk.definition, point(100000, 100000))
        v.furnishings.append(offscreen)
        previousCount = fits.call_count
        v.grab()
        assert fits.call_count == previousCount and id(offscreen) not in v.furnishingValidationCache
    for zoom in (.4, 1, 2):
        v.zoom = zoom
        cached = v.grab().toImage()
        v.furnishingValidationKey = None
        v.dimensionBoundaryKey = None
        for obj in v.walls + v.furnishings:
            obj.footprintCache = None
        assert v.grab().toImage() == cached
    footprint = v.ObjectFootprint(desk)
    assert v.ObjectFootprint(desk) is footprint
    desk.angle = 90
    assert v.ObjectFootprint(desk) is not footprint
    assert not v.ObjectsOverlap(desk, offscreen)
    window.close()
    print("PASS: pan/zoom validation reuse, rotation/width/wall/history invalidation, culling and identical cached/fresh pixels.")


if __name__ == "__main__":
    Main()
