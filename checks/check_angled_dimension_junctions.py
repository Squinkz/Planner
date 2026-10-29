"""Angled facade corners must not become tiny room-division dimensions."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall
from check_scene_render_cache import CompareDirect


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        for angle in (0, 31, 113):
            for reverse in (False, True):
                for reference in ("Wall faces", "Centerline"):
                    for divided in (False, True):
                        transform = QtGui.QTransform().rotate(angle)
                        points = [p(-2500, 1500), p(0, 0), p(2500, 0), p(2500, -2500), p(-2500, -2500)]
                        walls = [Wall(a, b, 200) for a, b in zip(points, points[1:] + points[:1])]
                        walls.append(Wall(p(0, 0), p(0, -2500), 200))
                        if divided:
                            # A real division on the diagonal must remain, even
                            # while the false division at its corner is removed.
                            walls.append(Wall(p(-600, 360), p(-600, -2500), 200))
                        for wall in walls:
                            wall.firstVertex = transform.map(wall.firstVertex)
                            wall.secondVertex = transform.map(wall.secondVertex)
                            if reverse:
                                wall.firstVertex, wall.secondVertex = wall.secondVertex, wall.firstVertex
                        InstallScene(main, walls)
                        v.showMeasurements, v.showTips = True, False
                        v.wallMeasurementMode, v.wallMeasurementReference = "Exterior stacked", reference
                        v.measurementVisibility = {key: key == "walls" for key in v.measurementVisibility}
                        v.zoom = .35 + angle * .0001
                        v.panOffset = p(0, 40)
                        v.grab()
                        assert v.roomDetection.count == (3 if divided else 2)
                        inner = [(a, b) for a, b, owners in v.sceneMeasurements[1] if walls[0] in owners]
                        outer = [(a, b) for a, b, owners, tier in v.sceneMeasurements[2] if walls[0] in owners]
                        expectedCount = (3 if reference == "Wall faces" else 2) if divided else 1
                        assert len(inner) == expectedCount, (angle, reverse, reference, divided, inner)
                        assert len(outer) == int(divided), (angle, reference, outer)
                        if not divided and reference == "Centerline":
                            assert abs(QtCore.QLineF(*inner[0]).length() - QtCore.QLineF(walls[0].firstVertex, walls[0].secondVertex).length()) < .01
                        if divided:
                            assert abs(sum(QtCore.QLineF(a, b).length() for a, b in inner)
                                       - QtCore.QLineF(*outer[0]).length()) < .01
                        CompareDirect(v)
    print("PASS: angled three-way corners, genuine nearby divisions, rotations, reversed endpoints and both dimension references")


if __name__ == "__main__":
    Main()
