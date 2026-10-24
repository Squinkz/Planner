"""Paint-prepared owner fills match independent collision geometry and safe fallbacks."""
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Pillar, Column, Furnishing
from planner_app.viewport.widget import DrawingViewport
from planner_app.viewport.geometry import FootprintGeometry, CollisionPass


@CollisionPass
def Query(viewport, first, second, excluded):
    return viewport.JoinedObjectsOverlap(first, second, excludedWalls = excluded)


def Probe(viewport, source, furnishing, excluded = (), reuse = True):
    # Force the exact joined-footprint branch, independently of whether a
    # particular test placement overlaps the simpler endpoint rectangles.
    viewport.collisionEpoch = 0
    viewport.collisionFootprintCache = {}
    viewport.collisionResults = {}
    viewport.collisionPairKeys = {}
    viewport.collisionPairEpochs = {}
    original = FootprintGeometry.ConnectedWallPath
    calls = []
    def Count(workspace, *args, **kwargs):
        calls.append(workspace)
        return original(workspace, *args, **kwargs)
    with patch.object(viewport, "ObjectsOverlap", return_value = False), patch.object(
            viewport, "JoinedObjectBounds", return_value = QtCore.QRectF(-1e6, -1e6, 2e6, 2e6)), patch.object(
            FootprintGeometry, "ConnectedWallPath", Count):
        result = Query(viewport, source, furnishing, excluded)
    assert bool(calls) != reuse, (reuse, len(calls))
    return result, viewport.collisionFootprintCache[Wall][1]


def ReferenceOutline(painter, path, dirtyRects):
    """Frozen pre-optimization outline culling, using Qt rectangle predicates."""
    if (not dirtyRects or painter.pen().style() != QtCore.Qt.PenStyle.SolidLine
            or any(path.elementAt(index).isCurveTo() for index in range(path.elementCount()))):
        painter.drawPath(path)
        return
    margin = max(1, painter.pen().widthF()) * max(4, painter.pen().miterLimit() * 2) + 3
    regions = [rect.adjusted(-margin, -margin, margin, margin) for rect in dirtyRects]
    fragments = QtGui.QPainterPath()
    for polygon in path.toSubpathPolygons():
        count = len(polygon) - 1
        if count <= 0:
            continue
        visible = []
        for index in range(count):
            bounds = QtCore.QRectF(polygon[index], polygon[index + 1]).normalized().adjusted(-margin, -margin, margin, margin)
            visible.append(any(bounds.intersects(rect) for rect in regions))
        if all(visible):
            fragments.addPolygon(polygon)
            fragments.closeSubpath()
            continue
        start = visible.index(False)
        drawing = False
        for offset in range(1, count + 1):
            index = (start + offset) % count
            if visible[index]:
                if not drawing:
                    fragments.moveTo(polygon[index])
                fragments.lineTo(polygon[index + 1])
            drawing = visible[index]
    painter.drawPath(fragments)


def Main():
    app = QtWidgets.QApplication([])
    viewport = DrawingViewport()
    point = QtCore.QPointF
    randomizer = random.Random(418)
    definition = {"key": "test", "width": 200, "length": 200}
    for frame in range(25):
        vertices = [point(0, 0), point(1500, 0), point(1800, 1200), point(-500, 1500)]
        walls = [Wall(vertices[index], vertices[(index + 1) % 4], 120 + 30 * (index % 3)) for index in range(4)]
        walls[1].firstMiter = frame % 3 * .4
        if frame % 2:
            walls.append(Pillar(point(1300, -100), point(1300, 200), 400))
        viewport.walls = walls
        viewport.zoom = .5 + frame * .03
        viewport.panOffset = point(frame * .37, frame * .71)
        viewport.ConnectedWallPath(walls)
        furnishing = Furnishing(definition, point(randomizer.uniform(-300, 1800), randomizer.uniform(-200, 1500)))
        viewport.furnishings = [furnishing]
        actual, actualPaths = Probe(viewport, walls[0], furnishing)
        geometryKey = viewport.wallGeometryKey
        viewport.wallGeometryKey = None
        expected, expectedPaths = Probe(viewport, walls[0], furnishing, reuse = False)
        viewport.wallGeometryKey = geometryKey
        assert actual == expected
        assert actualPaths.keys() == expectedPaths.keys()
        for identity in actualPaths:
            assert actualPaths[identity] == expectedPaths[identity], (frame, identity)
        # Old screen geometry must not validate changed, reordered, excluded,
        # or hidden construction. Those use independent full collision fills.
        walls[0].width += 5
        Probe(viewport, walls[0], furnishing, reuse = False)
        viewport.ConnectedWallPath(walls)
        Probe(viewport, walls[0], furnishing, excluded = (id(walls[-1]),), reuse = False)
        viewport.ConnectedWallPath(list(reversed(walls)))
        Probe(viewport, walls[0], furnishing, reuse = False)
        viewport.ConnectedWallPath(walls[:-1])
        Probe(viewport, walls[0], furnishing, reuse = False)
    viewport.walls = [Wall(point(), point(1500, 0), 240), Column(point(500, -200), point(500, 200), 400)]
    viewport.ConnectedWallPath(viewport.walls)
    Probe(viewport, viewport.walls[0], furnishing, reuse = False)
    # Dirty outline fragments must preserve complete joins at the clip edge.
    # Compare exact raster pixels with the original Qt rectangle culling,
    # including fractional coordinates, offscreen contours and fallback pens.
    for frame in range(40):
        path = QtGui.QPainterPath()
        for offset in (-900, 0, 900):
            polygon = QtGui.QPolygonF([point(offset + randomizer.uniform(-80, 380), randomizer.uniform(-80, 320))
                                      for index in range(12)])
            path.addPolygon(polygon)
            path.closeSubpath()
        if frame % 7 == 0:
            path.moveTo(10, 10)
            path.cubicTo(50, 250, 250, -50, 290, 230)
        clip = QtCore.QRectF(35.3, 40.7, 185.4, 140.2)
        pen = QtGui.QPen(QtGui.QColor("white"), .5 + frame % 6)
        pen.setJoinStyle((QtCore.Qt.PenJoinStyle.MiterJoin, QtCore.Qt.PenJoinStyle.BevelJoin,
                          QtCore.Qt.PenJoinStyle.RoundJoin)[frame % 3])
        if frame % 5 == 0:
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        images = []
        for partial in (False, True):
            image = QtGui.QImage(300, 240, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QtCore.Qt.GlobalColor.transparent)
            with QtGui.QPainter(image) as painter:
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                painter.setClipRect(clip)
                painter.setPen(pen)
                if partial:
                    viewport.DrawDirtyWallOutline(painter, path, [clip])
                else:
                    ReferenceOutline(painter, path, [clip])
            images.append(image)
        assert images[0] == images[1], ("Outline clipping", frame)
    # A grid stroke centered just outside any edge still has visible pixels.
    # Compare with drawing an oversized grid under the same viewport clip.
    viewport.resize(300, 240)
    viewport.zoom = .862
    viewport.showGrid = True
    rect = viewport.DrawingRect()
    for x in (rect.left() - .1, rect.right() + .1):
        for y in (rect.top() - .1, rect.bottom() + .1):
            images = []
            for expanded in (False, True):
                image = QtGui.QImage(300, 240, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(QtCore.Qt.GlobalColor.black)
                with QtGui.QPainter(image) as painter:
                    painter.setClipRect(rect)
                    viewport.DrawGridBackground(painter, rect.adjusted(-10, -10, 10, 10) if expanded else rect,
                                                point(x, y), viewport.basePixelsPerMillimeter * viewport.zoom, gridOnly = True)
                images.append(image)
            assert images[0] == images[1], ("Grid stroke fringe", x, y)
    viewport.close()
    print("Paint owner reuse and collision fallbacks passed")


if __name__ == "__main__":
    Main()
