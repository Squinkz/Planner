"""Verify exposed-edge dimension spans on both wall sides and room boundaries."""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtWidgets

from planner import DrawingViewport, Wall, Door, Window, SlidingDoor, PocketDoor


def Main():
    app = QtWidgets.QApplication([])
    if os.path.exists("C:/Windows/Fonts/segoeui.ttf"):
        QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    viewport = DrawingViewport()
    viewport.resize(1300, 1100)
    # These fixtures isolate doorway cuts; windows are continuous on both sides.
    viewport.measurementSettings["windows"] = 2
    point = QtCore.QPointF
    fixtures = [
        ([Wall(point(-2500, 0), point(2500, 0))], [5000, 5000]),
        ([Wall(point(-2500, 0), point(2500, 0)), Wall(point(), point(0, -1500), 120)],
         [1380, 1380, 2440, 2440, 5000]),
        ([Wall(point(-2500, 0), point(2500, 0)), Wall(point(0, 1500), point(0, -1500), 120)],
         [1380, 1380, 1380, 1380, 2440, 2440, 2440, 2440]),
        ([Wall(point(), point(5000, 0)), Wall(point(5000, 0), point(5000, -4000)),
          Wall(point(5000, -4000), point(0, -4000)), Wall(point(0, -4000), point()),
          Wall(point(0, -2000), point(5000, -2000))],
         [1760] * 4 + [4760] * 4 + [4240] * 2 + [5240] * 2),
    ]
    for walls, expectedLengths in fixtures:
        for reverse in (False, True):
            testWalls = [Wall(wall.secondVertex, wall.firstVertex, wall.width)
                         for wall in reversed(walls)] if reverse else walls
            for zoom in (0.02, 0.5, 1, 10):
                viewport.zoom = zoom
                viewport.panOffset = point(-137.21, 83.17)
                path = viewport.ConnectedWallPath(testWalls)
                dimensions = viewport.WallDimensions(testWalls, path)
                lengths = sorted(QtCore.QLineF(first, second).length() for first, second, owners in dimensions)
                assert len(lengths) == len(expectedLengths), (lengths, expectedLengths)
                assert all(abs(actual - expected) < 0.01 for actual, expected in zip(lengths, sorted(expectedLengths)))
                for first, second, owners in dimensions:
                    start = viewport.WorldToViewport(first)
                    end = viewport.WorldToViewport(second)
                    direction = end - start
                    normal = point(direction.y(), -direction.x()) / QtCore.QLineF(start, end).length()
                    assert not path.contains((start + end) / 2 + normal * 0.01)
    # Door jambs split the swing side, independently of hinge, orientation and zoom.
    for endpoint in (point(5000, 0), point(0, 5000), point(3000, 4000)):
        for reverse in (False, True):
            parent = Wall(endpoint, point()) if reverse else Wall(point(), endpoint)
            axis = (parent.secondVertex - parent.firstVertex) / 5000
            left = point(-axis.y(), axis.x())
            door = Door(parent, .2, .4)
            viewport.windows = [door, Window(parent, .6, .8)]
            for outward in (False, True):
                door.swingsOutwards = outward
                swingSide = -left if outward else left
                for hingeAtSecond in (False, True):
                    door.hingeAtSecond = hingeAtSecond
                    for zoom in (.02, 1, 10):
                        viewport.zoom = zoom
                        path = viewport.ConnectedWallPath([parent])
                        spans = viewport.WallDimensions([parent], path)
                        split = [(first, second) for first, second, owners in spans
                                 if point.dotProduct((first + second) / 2 - parent.firstVertex, swingSide) > 0]
                        continuous = [(first, second) for first, second, owners in spans
                                      if point.dotProduct((first + second) / 2 - parent.firstVertex, swingSide) < 0]
                        lengths = sorted(QtCore.QLineF(first, second).length() for first, second in split)
                        assert len(lengths) == 3 and all(abs(a - b) < .01 for a, b in zip(lengths, [1000, 1000, 3000]))
                        assert len(continuous) == 1 and abs(QtCore.QLineF(*continuous[0]).length() - 5000) < .01
            # Multiple openings, including clipping at the wall end, have separate doorway spans.
            door.swingsOutwards = False
            viewport.windows = [Door(parent, 0, .2), Door(parent, .4, .6)]
            spans = viewport.WallDimensions([parent], viewport.ConnectedWallPath([parent]))
            lengths = sorted(QtCore.QLineF(first, second).length() for first, second, owners in spans)
            assert len(lengths) == 5 and all(abs(a - b) < .01 for a, b in zip(lengths, [1000, 1000, 1000, 2000, 5000]))
    # Pocket opening calculations must not replace the wall-side midpoint used
    # by later regular doors. Check both insertion orders and rotated walls.
    for endpoint in (point(5000, 0), point(0, 5000), point(3000, 4000)):
        parent = Wall(point(), endpoint)
        axis = endpoint / 5000
        left = point(-axis.y(), axis.x())
        pocket = PocketDoor(parent, .1, .3)
        regular = Door(parent, .5, .6)
        path = viewport.ConnectedWallPath([parent])
        for openings in ([pocket, regular], [regular, pocket]):
            viewport.windows = openings
            for outward in (False, True):
                regular.swingsOutwards = outward
                side = -left if outward else left
                spans = viewport.WallDimensions([parent], path)
                split = [QtCore.QLineF(first, second).length() for first, second, owners in spans
                         if point.dotProduct((first + second) / 2 - parent.firstVertex, side) > 0]
                continuous = [QtCore.QLineF(first, second).length() for first, second, owners in spans
                              if point.dotProduct((first + second) / 2 - parent.firstVertex, side) < 0]
                assert len(split) == 5 and len(continuous) == 3
                assert all(abs(a - b) < .01 for a, b in zip(sorted(split), [500, 500, 500, 1500, 2000]))
        sliding = SlidingDoor(parent, .4, .6)
        viewport.windows = [sliding]
        for panelSide in (False, True):
            sliding.panelsFlipped = panelSide
            side = -left if panelSide else left
            for slideDirection in (False, True):
                sliding.hingeAtSecond = slideDirection
                spans = viewport.WallDimensions([parent], path)
                split = [QtCore.QLineF(first, second).length() for first, second, owners in spans
                         if point.dotProduct((first + second) / 2 - parent.firstVertex, side) > 0]
                continuous = [QtCore.QLineF(first, second).length() for first, second, owners in spans
                              if point.dotProduct((first + second) / 2 - parent.firstVertex, side) < 0]
                assert len(split) == 3 and len(continuous) == 1
                assert all(abs(a - b) < .01 for a, b in zip(sorted(split), [1000, 2000, 2000]))
                assert abs(continuous[0] - 5000) < .01
    viewport.windows = []
    viewport.zoom = 1
    viewport.panOffset = point(-500, -400)
    viewport.walls = fixtures[-1][0]
    viewport.show()
    app.processEvents()
    viewport.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "dimensions-preview.png"))
    print("PASS: both sides, T/cross intersections, continuous exterior dimensions, swing-side doorway measurements, room clearances and view invariance.")


if __name__ == "__main__":
    Main()
