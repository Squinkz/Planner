"""Translated right-angle joins must retain closed, axis-aligned outlines."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    viewport = main.viewport
    point = QtCore.QPointF
    for x, y in ((-2465.9999975, -6449.9999975), (0, 0), (137.0000025, 129.0000025),
                 (5217.0000025, -4514.9999975), (-6849.9999975, 6321.0000025)):
        walls = [Wall(point(x, y), point(x + 1000, y), 240),
                 Wall(point(x, y), point(x, y - 1800), 240),
                 Wall(point(x - 4000, y), point(x - 6000, y), 240),
                 Wall(point(x - 4000, y), point(x - 4000, y - 2000), 240)]
        viewport.walls = walls
        for zoom in (.05, 1, 8):
            viewport.zoom = zoom
            path = viewport.ConnectedWallPath(walls)
            previous = None
            perimeter = 0.0
            contourCount = 0
            for index in range(path.elementCount()):
                element = path.elementAt(index)
                current = viewport.ViewportToWorld(point(element.x, element.y))
                if element.isMoveTo():
                    contourCount += 1
                else:
                    assert abs(current.x() - previous.x()) < 1e-5 or abs(current.y() - previous.y()) < 1e-5
                    perimeter += QtCore.QLineF(previous, current).length()
                previous = current
            assert contourCount == 2 and abs(perimeter - 14560) < .01, (contourCount, perimeter)
            for offset in (point(500, 0), point(0, -900), point(-80, 80)):
                assert path.contains(viewport.WorldToViewport(point(x, y) + offset))
            for offset in (point(300, -300), point(-150, 150)):
                assert not path.contains(viewport.WorldToViewport(point(x, y) + offset))
        # Exercise paint and selection clipping with the same fractional geometry.
        viewport.SetSelection([(walls[0], None)])
        viewport.grab()
    main.close()


if __name__ == "__main__":
    Main()
