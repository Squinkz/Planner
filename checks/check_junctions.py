"""Regression checks for clean multi-wall endpoint junctions."""

import itertools
import math
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtWidgets

from planner import MainWindow, Wall
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    fontPath = "C:/Windows/Fonts/segoeui.ttf"
    if os.path.exists(fontPath):
        QtGui.QFontDatabase.addApplicationFont(fontPath)
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    walls = [Wall(point(), point(0, 1500), 200, firstMiter = 0.0, secondMiter = 0.0), Wall(point(), point(1500, 0), 200, firstMiter = 0.0, secondMiter = 0.0),
             Wall(point(), point(1500, 1500), 200, firstMiter = 0.0, secondMiter = 0.0)]

    # Match the user's three-ray junction, independent of object/endpoint order.
    for zoom in (0.02, 1.0, 10.0):
        viewport.zoom = zoom
        for orderedWalls in itertools.permutations(walls):
            for reverseEndpoints in (False, True):
                testWalls = [Wall(wall.secondVertex, wall.firstVertex, wall.width, firstMiter = 0.0, secondMiter = 0.0)
                             if reverseEndpoints else wall for wall in orderedWalls]
                path = viewport.ConnectedWallPath(testWalls)
                assert path.contains(viewport.WorldToViewport(point(-80, -80)))
                for outsidePoint in (point(-120, 0), point(0, -120), point(-80, -180), point(-180, -80)):
                    assert not path.contains(viewport.WorldToViewport(outsidePoint))
                bounds = path.boundingRect()
                expectedCorner = viewport.WorldToViewport(point(-100, -100))
                assert abs(bounds.left() - expectedCorner.x()) < 1e-6
                assert abs(bounds.bottom() - expectedCorner.y()) < 1e-6

    viewport.ResetView()
    # Keep the legitimate miter when only the vertical and diagonal rays meet.
    twoWallPath = viewport.ConnectedWallPath([walls[0], walls[2]])
    assert twoWallPath.contains(viewport.WorldToViewport(point(-80, -180)))
    # Coincident duplicate rays must not mask the widest wall's outer edge.
    duplicateWalls = walls + [Wall(point(), point(0, 1000), 300, firstMiter = 0.0, secondMiter = 0.0)]
    duplicatePath = viewport.ConnectedWallPath(duplicateWalls)
    assert duplicatePath.contains(viewport.WorldToViewport(point(-140, -80)))
    assert not duplicatePath.contains(viewport.WorldToViewport(point(-170, -80)))
    # Four-way junction with an extra diagonal has no pairwise miter spikes.
    multiWalls = walls + [Wall(point(), point(-1500, 0), 200, firstMiter = 0.0, secondMiter = 0.0), Wall(point(), point(0, -1500), 200, firstMiter = 0.0, secondMiter = 0.0)]
    multiPath = viewport.ConnectedWallPath(multiWalls)
    assert multiPath.contains(viewport.WorldToViewport(point(80, 80)))
    assert not multiPath.contains(viewport.WorldToViewport(point(-180, -180)))

    # Acute outer corners must reach the actual offset-edge intersection,
    # including angles just below the former four-half-width miter cutoff.
    for degrees in (28, 15, 5, 1):
        angle = math.radians(degrees)
        for firstWidth, secondWidth in ((240, 240), (120, 240)):
            sharpWalls = [Wall(point(-5000, 0), point(), firstWidth, firstMiter = 0.0, secondMiter = 0.0),
                          Wall(point(), point(-3000 * math.cos(angle), -3000 * math.sin(angle)), secondWidth, firstMiter = 0.0, secondMiter = 0.0)]
            tip = point((secondWidth / 2 + firstWidth / 2 * math.cos(angle)) / math.sin(angle), firstWidth / 2)
            for zoom in (0.02, 1, 10):
                viewport.zoom = zoom
                for reverse in (False, True):
                    testWalls = [Wall(wall.secondVertex, wall.firstVertex, wall.width, firstMiter = 0.0, secondMiter = 0.0)
                                 for wall in reversed(sharpWalls)] if reverse else sharpWalls
                    path = viewport.ConnectedWallPath(testWalls)
                    assert abs(path.boundingRect().right() - viewport.WorldToViewport(tip).x()) < 1e-5
                    assert path.contains(viewport.WorldToViewport(tip * 0.95))

    # Unequal collinear widths must step at the branch face, not the joint center.
    for branchWidth in (120, 240, 360):
        fixture = [Wall(point(-1500, 0), point(), 120), Wall(point(), point(1500, 0), 240),
                   Wall(point(), point(0, 1500), branchWidth)]
        for degrees in (0, 90, 180, 270, 37):
            transform = QtGui.QTransform().rotate(degrees)
            for zoom in (.02, 1, 10):
                viewport.zoom = zoom
                for orderedWalls in itertools.permutations(fixture):
                    for reverse in (False, True):
                        testWalls = [Wall(transform.map(wall.secondVertex if reverse else wall.firstVertex),
                                          transform.map(wall.firstVertex if reverse else wall.secondVertex), wall.width)
                                     for wall in orderedWalls]
                        path = viewport.ConnectedWallPath(testWalls)
                        assert path.contains(viewport.WorldToViewport(transform.map(point(-branchWidth / 4, -90))))
                        assert not path.contains(viewport.WorldToViewport(transform.map(point(-branchWidth / 2 - 20, -90))))
                        assert not path.contains(viewport.WorldToViewport(transform.map(point(-branchWidth / 4, -140))))

    viewport.ResetView()

    joint = point(-1000, -600)
    viewport.walls = [Wall(joint, joint + point(0, 2000), firstMiter = 0.0, secondMiter = 0.0),
                      Wall(joint, joint + point(3000, 0), firstMiter = 0.0, secondMiter = 0.0),
                      Wall(joint, joint + point(2000, 2000), firstMiter = 0.0, secondMiter = 0.0)]
    app.processEvents()
    window.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "junction-preview.png"))
    viewport.walls = [Wall(point(-1500, 0), point(), 120), Wall(point(), point(1500, 0), 240),
                      Wall(point(), point(0, 1500), 240)]
    viewport.showGrid = False
    viewport.showMeasurements = False
    viewport.selectedWall = None
    viewport.hoverPosition = None
    viewport.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "unequal-width-junction-preview.png"))
    window.close()
    print("PASS: square three-wall corner, two-wall miter, order/reversal/zoom invariance, duplicate rays, unequal-width T transitions and multi-wall junctions.")


if __name__ == "__main__":
    Main()
