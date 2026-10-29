"""Stair footprints close room boundaries and invalidate only on relevant changes."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Stair, RoomLabel
from planner_app.viewport.widget import DrawingViewport
from planner_app.viewport.geometry import FootprintGeometry
from planner_app.room_detection import DetectRooms
from check_room_detection import Rectangle
from planner_app.export_scene import PrepareExportScene


def Main():
    app = QtWidgets.QApplication([])
    point = QtCore.QPointF
    walls = Rectangle(0, 0, 4000, 4000)[:3]
    stair = Stair(point(0, 0), point(0, 4000), 900)
    geometry = FootprintGeometry(1)
    assert DetectRooms(walls, geometry)[1] == 0
    rooms, count = DetectRooms(walls + [stair], geometry)
    assert count == 1 and rooms.contains(point(2000, 2000))
    assert not rooms.contains(point(0, 2000))
    # Connected flights and rotated enclosures use the same joined stair body
    # as rendering, including the corner landing.
    for angle in (0, 37, 90):
        transform = QtGui.QTransform().rotate(angle)
        joined = Rectangle(0, 0, 4000, 4000)[:3] + [
            Stair(point(0, 0), point(0, 2000), 900), Stair(point(0, 2000), point(0, 4000), 900)]
        for obj in joined:
            obj.firstVertex = transform.map(obj.firstVertex)
            obj.secondVertex = transform.map(obj.secondVertex)
        rotated, rotatedCount = DetectRooms(joined, geometry)
        assert rotatedCount == 1 and rotated.contains(transform.map(point(2000, 2000))), angle
    view = DrawingViewport()
    view.performanceTimer.stop()
    view.walls = walls + [stair]
    view.labels = [RoomLabel(point(1500, 2000), "Room")]
    detector = view.roomDetection
    detector.Check()
    assert detector.count == 1
    area = view.labels[0].areaSquareMillimeters
    assert area == (3900 - 450) * 3800, area
    builds = detector.rebuildCount
    for step in range(4):
        view.panOffset += point(.31, -.43)
        view.zoom *= 1.1
        detector.Check()
    assert detector.rebuildCount == builds
    stair.firstVertex.setY(1000)
    detector.Check()
    assert detector.count == 0 and view.labels[0].areaSquareMillimeters is None
    stair.firstVertex.setY(0)
    detector.Check()
    assert detector.count == 1 and view.labels[0].areaSquareMillimeters == area
    view.visibility["Stairs"] = False
    detector.Check()
    assert detector.count == 0
    view.visibility["Stairs"] = True
    detector.Check()
    assert detector.count == 1
    state = view.CaptureState()
    stair.width = 1200
    detector.Check()
    assert view.labels[0].areaSquareMillimeters == (3900 - 600) * 3800
    view.RestoreState(state)
    detector.Check()
    assert detector.count == 1 and view.labels[0].areaSquareMillimeters == area
    PrepareExportScene(view)
    assert detector.count == 1 and detector.path.contains(point(2000, 2000))
    view.close()
    print("PASS: stair enclosure/area, edit invalidation, visibility, camera reuse and export preparation")


if __name__ == "__main__":
    Main()
