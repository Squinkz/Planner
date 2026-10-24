"""Check every wall remains filled in a multi-room plan across view transforms."""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtWidgets

from planner import DrawingViewport, Wall
from planner_app.graphics.palette import themeColors


def Main():
    app = QtWidgets.QApplication([])
    if os.path.exists("C:/Windows/Fonts/segoeui.ttf"):
        QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    viewport = DrawingViewport()
    viewport.resize(1600, 1150)
    point = QtCore.QPointF
    vertices = [point(x * 8.75, -y * 8.75) for x, y in (
        (143, 803), (385, 210), (556, 551), (881, 506),
        (1062, 172), (1310, 163), (1470, 735), (1012, 1032), (829, 757))]
    edges = ((0, 2), (2, 1), (1, 4), (4, 5), (4, 3), (3, 2),
             (3, 8), (8, 0), (8, 6), (6, 5), (6, 7), (7, 0))
    for reverse in (False, True):
        walls = [Wall(vertices[a], vertices[b], firstMiter = 0.0, secondMiter = 0.0) for a, b in edges]
        if reverse:
            walls = [Wall(wall.secondVertex, wall.firstVertex, firstMiter = 0.0, secondMiter = 0.0) for wall in reversed(walls)]
        for zoom in (0.37, 0.5714285714285714, 1.0, 1.33):
            viewport.zoom = zoom
            for pan in range(12):
                viewport.panOffset = point(-800 + pan * 0.17, -500 + pan * 0.31)
                path = viewport.ConnectedWallPath(walls)
                for wallIndex, wall in enumerate(walls):
                    direction = wall.secondVertex - wall.firstVertex
                    normal = point(-direction.y(), direction.x()) / QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
                    for fraction in (0.1, 0.25, 0.5, 0.75, 0.9):
                        position = wall.firstVertex + (wall.secondVertex - wall.firstVertex) * fraction
                        for across in (-80, 0, 80):
                            assert path.contains(viewport.WorldToViewport(position + normal * across)), (reverse, zoom, pan, wallIndex, fraction, across)
    viewport.zoom = 0.5714285714285714
    viewport.panOffset = point(-800, -560)
    viewport.walls = [Wall(vertices[a], vertices[b], firstMiter = 0.0, secondMiter = 0.0) for a, b in edges]
    viewport.show()
    app.processEvents()
    image = viewport.grab().toImage()
    for wall in viewport.walls:
        sample = viewport.WorldToViewport((wall.firstVertex + wall.secondVertex) / 2).toPoint()
        assert image.pixelColor(sample).name() in (themeColors["wallFill"], themeColors["materialPattern"]), image.pixelColor(sample).name()
    image.save(str(Path(__file__).resolve().parent.parent / "screenshots" / "complex-rendering-preview.png"))
    print("PASS: all wall bodies remain present across pan, zoom and endpoint reversal.")


if __name__ == "__main__":
    Main()
