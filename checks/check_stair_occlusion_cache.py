"""Camera-independent stair occlusion agrees with the original Boolean clip."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Stair, Door
from planner_app.viewport.widget import DrawingViewport


def ClipMask(viewport, path):
    image = QtGui.QImage(viewport.size(), QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtCore.Qt.GlobalColor.black)
    painter = QtGui.QPainter(image)
    painter.setClipRect(viewport.DrawingRect())
    painter.setClipPath(path, QtCore.Qt.ClipOperation.IntersectClip)
    painter.fillRect(viewport.rect(), QtCore.Qt.GlobalColor.white)
    painter.end()
    return image


def Main():
    app = QtWidgets.QApplication([])
    v = DrawingViewport()
    v.resize(1001, 701)
    v.performanceTimer.stop()
    v.showMeasurements = v.showGrid = False
    v.viewportSceneByteLimit = 0
    point = QtCore.QPointF
    wall = Wall(point(-2000, 600), point(2000, 600))
    stair = Stair(point(-1700, 0), point(1700, 0), 1000)
    door = Door(wall, .3, .6)
    v.walls, v.windows = [wall, stair], [door]
    for zoom in (.2, .7, 1.3, 3):
        v.zoom = zoom
        v.lineWidths.update(walls = 8, architectural = 2)
        v.panOffset = point(13.25, -7.75)
        v.grab()
        occlusion = v.stairWallOcclusion
        for pan in (point(13.25, -7.75), point(27.25, 8.25), point(27.7, 8.9), point(-400, 125)):
            v.panOffset = pan
            v.grab()
            assert v.stairWallOcclusion is occlusion, "Camera translation rebuilt wall occlusion"
            # Original algorithm: viewport minus wall fill and stroke, plus doorway.
            combined = v.ConnectedWallPath([wall])
            reference = QtGui.QPainterPath()
            reference.addRect(v.DrawingRect())
            reference = reference.subtracted(combined)
            stroke = QtGui.QPainterPathStroker()
            stroke.setWidth(8)
            stroke.setJoinStyle(QtCore.Qt.PenJoinStyle.BevelJoin)
            stroke.setCapStyle(QtCore.Qt.PenCapStyle.SquareCap)
            reference = reference.subtracted(stroke.createStroke(combined))
            first, second = v.WorldToViewport(door.firstVertex), v.WorldToViewport(door.secondVertex)
            direction = second - first
            normal = point(-direction.y(), direction.x()) / QtCore.QLineF(first, second).length()
            normal *= door.width * v.basePixelsPerMillimeter * v.zoom / 2 + v.lineWidths["walls"]
            opening = QtGui.QPainterPath()
            opening.addPolygon(QtGui.QPolygonF([first + normal, second + normal, second - normal, first - normal]))
            opening.closeSubpath()
            reference = reference.united(opening)
            assert ClipMask(v, v.stairWallClip) == ClipMask(v, reference), (zoom, pan)
    for mutation in (lambda: setattr(wall, "width", wall.width + 20),
                     lambda: setattr(door, "centerFraction", door.centerFraction + .05),
                     lambda: v.lineWidths.update(walls = 10),
                     lambda: setattr(v, "zoom", v.zoom * 1.1),
                     lambda: v.visibility.update(Walls = False)):
        occlusion = v.stairWallOcclusion
        mutation()
        v.grab()
        assert v.stairWallOcclusion is not occlusion, "Occlusion remained stale after an edit/settings change"
    v.close()
    print("PASS: zero camera-only occlusion rebuilds, exact legacy clip masks, geometry/opening/zoom/linework/visibility invalidation")


if __name__ == "__main__":
    Main()
