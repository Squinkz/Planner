"""Touching stair edges preserve wall stroke/fill and free edges stay lighter."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.palette import themeColors
from planner_app.models import Wall, Stair, Door
from planner_app.viewport.widget import DrawingViewport


def Main():
    app = QtWidgets.QApplication([])
    themeColors.update(canvas = "#ffffff", wallFill = "#cccccc", wallOutline = "#000000", objectOutline = "#000000")
    viewport = DrawingViewport()
    viewport.resize(900, 650)
    viewport.showGrid = viewport.showMeasurements = False
    viewport.performanceTimer.stop()
    viewport.lineWidths.update(walls = 8, architectural = 2)
    point = QtCore.QPointF
    for vertical in (False, True):
        walls = [Wall(point(-1000, y), point(1500, y), 240) for y in (-620, 620)]
        stair = Stair(point(-1000, 0), point(1000, 0), 1000)
        if vertical:
            for obj in walls + [stair]:
                obj.firstVertex = point(obj.firstVertex.y(), obj.firstVertex.x())
                obj.secondVertex = point(obj.secondVertex.y(), obj.secondVertex.x())
        viewport.walls = walls
        viewport.show()
        app.processEvents()
        before = viewport.grab().toImage()
        viewport.walls = walls + [stair]
        after = viewport.grab().toImage()
        for y in (-500, 500, -620, 620):
            sample = viewport.WorldToViewport(point(y, 125) if vertical else point(125, y)).toPoint()
            # Inset stair edges may occupy nearby canvas, but must preserve every
            # existing wall stroke/fill pixel, including its antialiasing fringe.
            for offset in range(-8, 9):
                x = sample.x() + offset if vertical else sample.x()
                row = sample.y() if vertical else sample.y() + offset
                if before.pixelColor(x, row) == QtGui.QColor("#ffffff"):
                    continue
                assert before.pixelColor(x, row) == after.pixelColor(x, row), (vertical, y, offset)
        freeEdge = viewport.WorldToViewport(point(200, 1000) if vertical else point(1000, 200)).toPoint()
        coverage = sum((255 - after.pixelColor(freeEdge.x() if vertical else freeEdge.x() + offset,
                                              freeEdge.y() + offset if vertical else freeEdge.y()).red()) / 255
                       for offset in range(-8, 9))
        assert abs(coverage - 2) < .08, (vertical, coverage)
        clip = viewport.stairWallClip
        stair.secondVertex += point(0, 50) if vertical else point(50, 0)
        viewport.grab()
        assert viewport.stairWallClip is clip, "Moving stairs rebuilt the wall clip"
    # A stair end at a doorway must remain visible inside the wall's opening.
    wall = Wall(point(-1500, 0), point(1500, 0), 240)
    stair = Stair(point(0, -120), point(0, -1200), 590)
    viewport.walls = [wall, stair]
    viewport.windows = []
    viewport.grab()
    solidClip = viewport.stairWallClip
    door = Door(wall, .3, .7)
    viewport.windows = [door]
    after = viewport.grab().toImage()
    cap = viewport.WorldToViewport(point(150, -120)).toPoint()
    assert viewport.stairWallClip is not solidClip, "Adding a doorway did not refresh stair clipping"
    assert viewport.stairWallClip.contains(QtCore.QPointF(cap))
    coverage = sum((255 - after.pixelColor(cap.x(), cap.y() + offset).red()) / 255
                   for offset in range(-5, 6))
    assert abs(coverage - 2) < .08, coverage
    # Moving the opening restores wall priority at the stair end immediately.
    door.centerFraction = .8
    viewport.grab()
    assert not viewport.stairWallClip.contains(QtCore.QPointF(cap))
    viewport.close()


if __name__ == "__main__":
    Main()
