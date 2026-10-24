"""Connected arrow corners render without internal seams or double opacity."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Arrow
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.showGrid = False
    v.showMeasurements = False
    point = QtCore.QPointF
    v.panOffset = point(-100, -50)
    for intensity in (1, .5):
        north = Arrow(point(0, 1000), point(), 200, intensity = intensity)
        east = Arrow(point(), point(1000, 0), 200, intensity = intensity)
        for zoom in (1, 3.25):
            v.zoom = zoom
            for arrows in ([north, east], [east, north]):
                v.walls = arrows
                image = v.grab().toImage()
                reference = v.WorldToViewport(point(200, 0)).toPoint()
                expected = image.pixelColor(reference)
                # The diagonal dividing the corner triangles is entirely
                # inside the combined fill; no pixel along it can be dimmer.
                for offset in range(20, 80, 2):
                    sample = v.WorldToViewport(point(-offset, -offset)).toPoint()
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            actual = image.pixelColor(sample + QtCore.QPoint(dx, dy))
                            assert actual == expected, (intensity, zoom, offset, actual.name(), expected.name())
                # Overlapping shaft rectangles have the same opacity as tails.
                overlap = v.WorldToViewport(point(50, 50)).toPoint()
                assert image.pixelColor(overlap) == expected
    main.close()


if __name__ == "__main__":
    Main()
