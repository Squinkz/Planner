"""Check that edge-touching collinear walls have no internal outline."""

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
    if os.path.exists("C:/Windows/Fonts/segoeui.ttf"):
        QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas")  # Fixed palette for pixel assertions.
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    for direction in (point(1, 0), point(0, 1), point(1, 1), point(1, -1), point(0.37, 0.93)):
        direction /= math.hypot(direction.x(), direction.y())
        normal = point(-direction.y(), direction.x())
        for widths in ((200, 200), (300, 200)):
            for reverseEndpoints in (False, True):
                walls = [Wall(direction * -1000, point(), widths[0], firstMiter = 0.0, secondMiter = 0.0), Wall(point(), direction * 1000, widths[1], firstMiter = 0.0, secondMiter = 0.0)]
                if reverseEndpoints:
                    walls = [Wall(wall.secondVertex, wall.firstVertex, wall.width, firstMiter = 0.0, secondMiter = 0.0) for wall in reversed(walls)]
                viewport.walls = walls
                viewport.selectedWall = None
                for zoom in (0.5, 1, 2):
                    viewport.zoom = zoom
                    path = viewport.ConnectedWallPath(walls)
                    assert len(path.toSubpathPolygons()) == 1, (direction, widths, zoom)
                    if zoom < 1:
                        continue  # At this scale the handle and edge antialiasing overlap.
                    # Probe the old seam inside both walls, away from the handle
                    # and the outer boundary; it must contain ordinary wall fill.
                    image = viewport.grab().toImage()
                    for side in (-1, 1):
                        sample = viewport.WorldToViewport(normal * (70 * side)).toPoint()
                        assert image.pixelColor(sample).name() in ("#20262b", "#697680"), (direction, widths, zoom, sample, image.pixelColor(sample).name())

    viewport.ResetView()
    viewport.walls = [Wall(point(-1500, 0), point(), firstMiter = 0.0, secondMiter = 0.0), Wall(point(), point(1500, 0), firstMiter = 0.0, secondMiter = 0.0)]
    app.processEvents()
    window.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "seam-preview.png"))
    window.close()
    print("PASS: seamless shared collinear endpoints across directions, widths, endpoint order and zoom levels.")


if __name__ == "__main__":
    Main()
