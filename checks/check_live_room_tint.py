"""Tint, exterior measurements and room areas share live cached boundaries."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from planner_app.graphics.palette import themeColors
from planner_app.models import Furnishing, RoomLabel, Wall
from planner_app import room_detection


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        walls = Rectangle(0, 0, 4000, 4000)
        InstallScene(main, walls[:-1])
        v.zoom, v.showGrid, v.showTips = .5, False, False
        v.wallMeasurementMode = "Exterior stacked"
        v.showMeasurements = True
        v.grab()
        assert v.roomDetection.count == 0
        interior = v.WorldToViewport(p(1003, 1207)).toPoint()
        # The preview closes the room while all drag flags remain active.
        v.pendingWall = walls[-1]
        v.dragStart, v.isDragging = p(), True
        with patch.object(room_detection, "BuildRoomBoundary", wraps = room_detection.BuildRoomBoundary) as classify:
            image = v.grab().toImage()
            assert v.roomDetection.count == 1 and classify.call_count == 1, classify.call_count
            assert image.pixelColor(interior) == QtGui.QColor(themeColors["roomFill"])
            assert v.sceneMeasurements is None  # Live measurements are not retained.
            for unused in range(3):
                v.grab()
            assert classify.call_count == 1
            # Reopening/closing the preview changes tint in that same paint.
            v.pendingWall.secondVertex = p(0, 500)
            image = v.grab().toImage()
            assert v.roomDetection.count == 0 and classify.call_count == 2
            assert image.pixelColor(interior) == QtGui.QColor(themeColors["canvas"])
            v.pendingWall.secondVertex = p()
            v.grab()
            assert v.roomDetection.count == 1 and classify.call_count == 3
            v.pendingWall = None
            v.grab()
            assert v.roomDetection.count == 0 and classify.call_count == 4
        v.dragStart, v.isDragging = None, False
        label = RoomLabel(p(2000, 2000), "LIVE")
        InstallScene(main, walls + [label])
        v.grab()
        assert label.areaSquareMillimeters == 14440000
        v.dragStart, v.isDragging = p(), True
        walls[-1].secondVertex = p(0, 500)
        with patch.object(room_detection, "BuildRoomBoundary", wraps = room_detection.BuildRoomBoundary) as classify:
            v.grab()
            assert v.roomDetection.count == 0 and label.areaSquareMillimeters is None and classify.call_count == 1
            walls[-1].secondVertex = p()
            v.grab()
            assert v.roomDetection.count == 1 and label.areaSquareMillimeters == 14440000 and classify.call_count == 2
        v.dragStart, v.isDragging = None, False
        v.grab()
        # Camera, selection and furniture changes reuse the same classification.
        desk = Furnishing(v.furnishingDefinitions["desk"], p(-2000, -2000))
        v.furnishings = [desk]
        v.grab()
        with patch.object(room_detection, "BuildRoomBoundary", side_effect = AssertionError("Unchanged boundary was rebuilt")):
            desk.firstVertex += p(100, 0)
            desk.secondVertex += p(100, 0)
            v.grab()
            v.SetSelection([(walls[0], None)])
            v.grab()
            v.panOffset += p(31, -7)
            v.zoom = .6
            v.grab()
        # Polygon-tool previews use the same immediate path, and cancellation clears it.
        InstallScene(main, [])
        v.pendingWall = Wall(p(), p(4000, 4000), 200)
        v.pendingShapeWalls = walls
        v.grab()
        assert v.roomDetection.count == 1
        v.pendingShapeWalls = []
        v.pendingWall = None
        v.grab()
        assert v.roomDetection.count == 0
    print("PASS: same-frame tint/measurements/area during drag and previews; unchanged geometry classified once")


if __name__ == "__main__":
    Main()
