"""A nearly straight T junction must have a closed exterior with no diagonals."""
import itertools
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall
from planner_app.viewport.widget import DrawingViewport
from planner_app.graphics.palette import themeColors
from planner_app.graphics.linework import LinePen


def Main():
    app = QtWidgets.QApplication([])
    viewport = DrawingViewport()
    viewport.resize(1000, 700)
    point = QtCore.QPointF
    # Exact wall coordinates from the reported session. Both horizontal rays
    # deviate slightly from straight, exposing tiny overlapping cap fragments.
    walls = [Wall(point(), point(0, 420), 240),
             Wall(point(0, 420), point(-713.7856350261153, 420.4334532883023), 240),
             Wall(point(0, 420), point(717.3500645702368, 420.43345350761547), 240),
             Wall(point(717.3500645702368, 420.43345350761547), point(717.3500645702368, 900), 240)]
    for zoom in (.02, 1, 10):
        viewport.zoom = zoom
        for ordered in itertools.permutations(walls):
            for reverse in (False, True):
                members = [Wall(wall.secondVertex, wall.firstVertex, wall.width) if reverse else wall for wall in ordered]
                path = viewport.ConnectedWallPath(members)
                contours = viewport.wallGeometryPath.toSubpathPolygons()
                assert len(contours) == 1, (zoom, reverse, len(contours))
                assert contours[0][0] == contours[0][-1]
                for position in (point(-70, 150), point(70, 330), point(-300, 420), point(700, 800)):
                    assert path.contains(viewport.WorldToViewport(position))
    # Exercise thinner slivers and different orientations/world positions.
    for deviation in (.01, .001, .0001):
        for angle in (0, 37, 90):
            transform = QtGui.QTransform().translate(100000, -100000).rotate(angle)
            members = [Wall(transform.map(first), transform.map(second), 240) for first, second in
                       ((point(), point(0, 420)), (point(0, 420), point(-714, 420 + deviation)),
                        (point(0, 420), point(717, 420 + deviation)))]
            viewport.ConnectedWallPath(members)
            assert len(viewport.wallGeometryPath.toSubpathPolygons()) == 1, (deviation, angle)
    for distance in (1e6, 1e7, 1e8):
        transform = QtGui.QTransform().translate(distance, -distance).rotate(37)
        members = [Wall(transform.map(wall.firstVertex), transform.map(wall.secondVertex), wall.width) for wall in walls]
        viewport.ConnectedWallPath(members)
        assert len(viewport.wallGeometryPath.toSubpathPolygons()) == 1, distance
    viewport.zoom = 2.5
    viewport.panOffset = point(0, 180)
    path = viewport.ConnectedWallPath(walls)
    image = QtGui.QImage(viewport.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtGui.QColor(themeColors["canvas"]))
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setPen(LinePen(themeColors["wallOutline"], 4))
    painter.setBrush(QtGui.QColor(themeColors["wallFill"]))
    painter.drawPath(path)
    painter.end()
    for position in (point(-70, 150), point(70, 330)):
        assert image.pixelColor(viewport.WorldToViewport(position).toPoint()).name() == themeColors["wallFill"]
    image.save(str(Path(__file__).resolve().parent.parent / "screenshots/nearly-straight-wall-boundary.png"))


if __name__ == "__main__":
    Main()
