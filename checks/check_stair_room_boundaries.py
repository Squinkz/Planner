"""Stair footprints close room boundaries and invalidate only on relevant changes."""
import os
import json
import math
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Stair, RoomLabel
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
    for gap in (.001, 1):
        separated = Stair(point(0, 100 + gap), point(0, 4000), 900)
        assert DetectRooms(walls + [separated], geometry)[1] == 0, "Room tracing closed a genuine gap"
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
    # Exact structural coordinates from prewar_rowhouse: the bottom wall is
    # almost horizontal and the stair meets its face within a few float ULPs.
    # Qt's union used to produce overlapping holes and zero-area room regions.
    records = json.loads((Path(__file__).parent / "fixtures/rowhouse_stair_room.json").read_text(encoding = "utf-8"))
    corridor = point(14500, 8000)
    stairCentre = point(15000, 7205)
    expectedArea = 6938300
    for angle, offset in ((0, point()), (37, point()), (90, point()), (0, point(1e8, -1e8)), (37, point(1e8, -1e8))):
        transform = QtGui.QTransform().translate(offset.x(), offset.y()).rotate(angle)
        objects = []
        for record in records:
            obj = (Stair if record["type"] == "Stair" else Wall)(transform.map(point(*record["first"])),
                  transform.map(point(*record["second"])), record["width"])
            obj.firstMiter, obj.secondMiter = record["firstMiter"], record["secondMiter"]
            obj.objectId = record["id"]
            objects.append(obj)
        before = [(obj.firstVertex.toTuple(), obj.secondVertex.toTuple(), obj.width) for obj in objects]
        for scale in (.2, 1):
            geometry = FootprintGeometry(scale)
            rooms, count = DetectRooms(objects, geometry)
            probe = transform.map(corridor)
            assert rooms.contains(probe), (angle, offset, scale)
            assert not rooms.contains(transform.map(stairCentre))
            regions = [region for region in geometry.roomRegions if region["path"].contains(probe)]
            assert len(regions) == 1 and math.isclose(regions[0]["area"], expectedArea, rel_tol = 1e-7), (angle, offset, scale, regions)
            assert all(region["area"] > 0 for region in geometry.roomRegions)
        assert before == [(obj.firstVertex.toTuple(), obj.secondVertex.toTuple(), obj.width) for obj in objects]
        if angle == 0 and offset.isNull():
            rowhouse = objects
    view.exportRender = False
    view.walls = rowhouse
    view.labels = [RoomLabel(corridor, "Hall")]
    detector.Check()
    assert detector.path.contains(corridor) and math.isclose(view.labels[0].areaSquareMillimeters, expectedArea, rel_tol = 1e-10)
    builds = detector.rebuildCount
    for zoom in (.1, .5, 2):
        view.zoom = zoom
        view.panOffset += point(.31, -.43)
        detector.Check()
    assert detector.rebuildCount == builds
    view.walls = [obj for obj in rowhouse if obj.objectId != 96]
    detector.Check()
    assert math.isclose(view.labels[0].areaSquareMillimeters, expectedArea + 2480 * 730, rel_tol = 1e-10)
    view.walls = rowhouse
    detector.Check()
    PrepareExportScene(view)
    assert detector.path.contains(corridor) and math.isclose(view.labels[0].areaSquareMillimeters, expectedArea, rel_tol = 1e-10)
    view.close()
    print("PASS: stair enclosure/area, edit invalidation, visibility, camera reuse and export preparation")


if __name__ == "__main__":
    Main()
