"""Crop guide strokes retain equal pixel coverage across zoom and display scales."""
import math
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.palette import themeColors
from planner_app.viewport.export_bounds import ExportBoundsOverlay


class GuideViewport(QtWidgets.QWidget):
    def WorldToViewport(self, point):
        return point * self.zoom + self.offset


def Main():
    app = QtWidgets.QApplication([])
    viewport = GuideViewport()
    overlay = ExportBoundsOverlay(viewport)
    overlay.active = True
    overlay.bounds = (60.2, 50.7, 120.4, 90.9)
    with patch.dict(themeColors, selectionOutline = "#ff0000"):
        for ratio in (1, 1.25, 1.5, 2):
            for zoom in (.37, .73, 1.11, 1.63):
                viewport.zoom = zoom
                viewport.offset = QtCore.QPointF(20.13, 20.47)
                x, y, width, height = overlay.bounds
                first = viewport.WorldToViewport(QtCore.QPointF(x, y))
                second = viewport.WorldToViewport(QtCore.QPointF(x + width, y + height))
                coordinates = (first.x(), second.x(), first.y(), second.y())
                for hovered in (None, 0, 1, 2, 3):
                    overlay.dragEdge = hovered
                    image = QtGui.QImage(round(400 * ratio), round(300 * ratio), QtGui.QImage.Format.Format_ARGB32)
                    image.setDevicePixelRatio(ratio)
                    image.fill(QtCore.Qt.GlobalColor.transparent)
                    with QtGui.QPainter(image) as painter:
                        # Exercise both inherited AA states; Draw must be stable.
                        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, zoom > 1)
                        overlay.Draw(painter, QtCore.QRectF(0, 0, 400, 300), shade = False)
                    for edge, coordinate in enumerate(coordinates):
                        centre = math.floor(coordinate * ratio)
                        coverage = []
                        for along in range(2, int(20 * ratio)):
                            alphas = [image.pixelColor(across, along).alpha() if edge < 2 else
                                      image.pixelColor(along, across).alpha()
                                      for across in range(centre - 5, centre + 6)]
                            assert all(alpha in (0, 255) for alpha in alphas), "Guide acquired fractional AA coverage"
                            coverage.append(sum(alpha > 0 for alpha in alphas))
                        expected = math.floor((2.5 if edge == hovered else 1.5) * ratio + .5)
                        assert max(coverage) == expected, (ratio, zoom, hovered, edge, max(coverage), expected)
    print("Crop guide pixel widths verified at four zooms and 100/125/150/200% display scaling")


if __name__ == "__main__":
    Main()
