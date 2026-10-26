"""Room/opening/overall chains compact to at most three exterior tiers."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from check_scene_render_cache import CompareDirect
from planner_app.models import Wall, Door, Window
from planner_app.export_plan import RenderPlan
from planner_app.viewport.rendering import RenderingMixin


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        walls = Rectangle(-2000, -2000, 4000, 4000)
        partition = Wall(p(0, -2000), p(0, 2000), 200)
        door, window = Door(walls[0], .15, .3), Window(walls[2], .2, .35)
        InstallScene(main, walls + [partition, door, window])
        v.showMeasurements = True
        v.measurementVisibility = dict.fromkeys(v.measurementVisibility, False)
        v.measurementVisibility["walls"] = True
        v.wallMeasurementMode = "Exterior stacked"
        v.wallMeasurementReference = "Centerline"
        v.zoom, v.showTips = .5, False
        v.grab()
        inner, additional = v.sceneMeasurements[1:]
        assert len(inner) == 10 and len(additional) == 6, (len(inner), additional)
        rooms = [(first, second) for first, second, owners, tier in additional if tier == 1]
        totals = [(first, second) for first, second, owners, tier in additional if tier == 2]
        assert len(rooms) == 4 and len(totals) == 2
        assert all(abs(QtCore.QLineF(first, second).length() - 2000) < 1e-6 for first, second in rooms)
        assert all(abs(QtCore.QLineF(first, second).length() - 4000) < 1e-6 for first, second in totals)
        v.wallMeasurementReference = "Wall faces"
        v.grab()
        assert len(v.sceneMeasurements[1]) == 12 and len(v.sceneMeasurements[2]) == 8
        lengths = sorted(round(QtCore.QLineF(first, second).length(), 5)
                         for first, second, owners, tier in v.sceneMeasurements[2] if tier == 1)
        assert lengths == [200, 200, 2000, 2000, 2000, 2000], lengths
        assert all(abs(QtCore.QLineF(first, second).length() - 4200) < 1e-6
                   for first, second, owners, tier in v.sceneMeasurements[2] if tier == 2)
        v.wallMeasurementReference = "Centerline"
        v.grab()
        CompareDirect(v)
        v.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/room-measurement-stacks.png"))
        path = folder / "room-stacks.plan"
        assert main.SaveProject(path)
        data = main.BuildProjectData()
        observed = []
        draw = RenderingMixin.DrawSceneMeasurements

        def DrawSceneMeasurements(viewport, *args, **kwargs):
            result = draw(viewport, *args, **kwargs)
            observed.append((len(viewport.sceneMeasurements[1]), len(viewport.sceneMeasurements[2])))
            return result

        with patch.object(RenderingMixin, "DrawSceneMeasurements", DrawSceneMeasurements):
            for format in ("png", "svg"):
                output = RenderPlan(path, 100, bounds = [-3000, -3000, 6000, 6000], projectData = data,
                                    outputFormat = format, applyTheme = False, useExportSettings = True)
                assert output if format == "png" else QtSvg.QSvgRenderer(output).isValid()
        assert observed and all(value == (10, 6) for value in observed), observed
        # Room-only chains compact to two tiers. No partitions/openings uses one.
        v.windows = []
        v.grab()
        assert len(v.sceneMeasurements[1]) == 6 and len(v.sceneMeasurements[2]) == 2
        assert all(tier == 1 for first, second, owners, tier in v.sceneMeasurements[2])
        v.walls = walls
        v.grab()
        assert len(v.sceneMeasurements[1]) == 4 and not v.sceneMeasurements[2]
        # A free stub is not a room division. More rooms never add another tier.
        v.walls = walls + [Wall(p(0, -2000), p(0, -1000), 200)]
        v.windows = [door, window]
        v.grab()
        assert len(v.sceneMeasurements[1]) == 8 and len(v.sceneMeasurements[2]) == 2
        v.walls = walls + [Wall(p(-300, -2000), p(-300, 2000), 200), Wall(p(300, -2000), p(300, 2000), 200)]
        v.grab()
        assert len(v.sceneMeasurements[2]) == 8
        assert max(tier for first, second, owners, tier in v.sceneMeasurements[2]) == 2
        # Rotation does not turn room divisions into axis-aligned approximations.
        v.walls = walls + [partition]
        transform = QtGui.QTransform().rotate(31)
        for wall in v.walls:
            wall.firstVertex, wall.secondVertex = transform.map(wall.firstVertex), transform.map(wall.secondVertex)
        v.grab()
        assert len(v.sceneMeasurements[1]) == 10 and len(v.sceneMeasurements[2]) == 6
        assert all(abs(QtCore.QLineF(first, second).length() - (2000 if tier == 1 else 4000)) < 1e-6
                   for first, second, owners, tier in v.sceneMeasurements[2])
        v.wallMeasurementReference = "Wall faces"
        v.grab()
        assert sorted(round(QtCore.QLineF(first, second).length(), 5)
                      for first, second, owners, tier in v.sceneMeasurements[2] if tier == 1) == [200, 200, 2000, 2000, 2000, 2000]
        CompareDirect(v)
        # Unequal thicknesses and an oblique corner still measure the actual
        # wall axes, independently of endpoint order and camera movement.
        points = [p(0, 0), p(4000, 0), p(3500, 3000), p(0, 3000)]
        walls = [Wall(first, second, width) for first, second, width in
                 zip(points, points[1:] + points[:1], (200, 400, 100, 300))]
        InstallScene(main, walls)
        v.wallMeasurementMode = "Exterior stacked"
        v.wallMeasurementReference = "Centerline"
        v.showMeasurements = True
        v.measurementVisibility = {key: key == "walls" for key in v.measurementVisibility}
        expected = sorted(round(QtCore.QLineF(wall.firstVertex, wall.secondVertex).length(), 5) for wall in walls)
        for reverse in (False, True):
            if reverse:
                for wall in walls:
                    wall.firstVertex, wall.secondVertex = wall.secondVertex, wall.firstVertex
                v.panOffset += p(21, -34)
            v.grab()
            actual = sorted(round(QtCore.QLineF(first, second).length(), 5)
                            for first, second, owners in v.sceneMeasurements[1])
            assert actual == expected, (actual, expected)
            assert not v.sceneMeasurements[2]
        walls = Rectangle(-2000, -2000, 4000, 4000)
        partition = Wall(p(-500, -2000), p(500, 2000), 200)
        InstallScene(main, walls + [partition, Door(walls[0], .15, .3), Window(walls[2], .2, .35)])
        v.grab()
        assert sorted(round(QtCore.QLineF(first, second).length(), 5)
                      for first, second, owners, tier in v.sceneMeasurements[2] if tier == 1) == [1500, 1500, 2500, 2500]
        # Three overlapping walls form one thick partition. A probe just beyond
        # any individual wall is still inside its neighbors, not inside a room.
        walls = Rectangle(-2000, -2000, 4000, 4000)
        partitions = [Wall(p(x, -1900), p(x, 1900), width)
                      for x, width in ((-150, 120), (0, 200), (150, 120))]
        InstallScene(main, walls + partitions + [Door(walls[0], .15, .3), Window(walls[2], .2, .35)])
        for reference, expected in (("Wall faces", [420, 420, 1890, 1890, 1890, 1890]),
                                    ("Centerline", [2000, 2000, 2000, 2000])):
            v.wallMeasurementReference = reference
            # Use a new camera key so these assertions inspect freshly built
            # spans rather than an already-recorded measurement picture.
            v.zoom += .01
            v.grab()
            lengths = sorted(round(QtCore.QLineF(first, second).length(), 5)
                             for first, second, owners, tier in v.sceneMeasurements[2] if tier == 1)
            assert lengths == expected, (reference, lengths)
            CompareDirect(v)
    print("PASS: compact one/two/three-tier room chains, stubs, rotation and PNG/SVG export")


if __name__ == "__main__":
    Main()
