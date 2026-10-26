"""Frozen curved/transparent occlusion and cosmetic-stroke PNG/SVG parity."""
import os
import itertools
import math
from pathlib import Path
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner_app.graphics.object_composite import ObjectPaintDevice
from fixtures.native_paths_reference_20261017 import Configure, Load


def Main():
    app = QtWidgets.QApplication([])
    Configure()
    frozen = Load("graphics/object_composite.py").ObjectPaintDevice
    size = QtCore.QSize(600, 400)
    for case in range(8):
        devices = []
        for cls in (frozen, ObjectPaintDevice):
            device = cls(size, QtGui.QColor("white"))
            with QtGui.QPainter(device) as painter:
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                painter.setClipRect(QtCore.QRectF(15, 15, 550, 350))
                painter.translate(.37 + case * 2, .71)
                painter.rotate(case * .13)
                painter.setBrush(QtGui.QColor("white"))
                pen = QtGui.QPen(QtGui.QColor("black"), .7)
                pen.setCosmetic(bool(case % 2))
                if case % 3 == 0: pen.setStyle(QtCore.Qt.PenStyle.DashLine)
                painter.setPen(pen)
                for i in range(5):
                    path = QtGui.QPainterPath()
                    path.addRoundedRect(30 + i * 70, 40 + i * 25, 150, 150, 35, 35)
                    path.addEllipse(60 + i * 70, 60 + i * 25, 90, 90)
                    path.setFillRule(QtCore.Qt.FillRule.WindingFill if case % 2 else QtCore.Qt.FillRule.OddEvenFill)
                    painter.drawPath(path)
                painter.setPen(QtGui.QPen(QtGui.QColor("white"), 3))
                painter.drawLine(30, 100, 450, 300)
                painter.setPen(QtGui.QColor("black"))
                painter.setFont(QtGui.QFont("Arial", 12))
                painter.drawText(QtCore.QPointF(220, 150), "REF W")
            devices.append(device)
        for svg in (False, True):
            pixels = []
            for device in devices:
                image = QtGui.QImage(size, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(QtGui.QColor("white"))
                if svg:
                    data = QtCore.QByteArray()
                    buffer = QtCore.QBuffer(data)
                    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
                    generator = QtSvg.QSvgGenerator()
                    generator.setOutputDevice(buffer)
                    generator.setSize(size)
                    generator.setViewBox(QtCore.QRect(0, 0, size.width(), size.height()))
                    with QtGui.QPainter(generator) as painter:
                        device.engine.Replay(painter, QtCore.QRectF(0, 0, 600, 400))
                    buffer.close()
                    renderer = QtSvg.QSvgRenderer(data)
                    assert renderer.isValid()
                    with QtGui.QPainter(image) as painter: renderer.render(painter)
                else:
                    with QtGui.QPainter(image) as painter:
                        device.engine.Replay(painter, QtCore.QRectF(0, 0, 600, 400))
                pixels.append(bytes(image.constBits()))
            assert pixels[0] == pixels[1], (case, svg)
    from planner_app.viewport.widget import DrawingViewport
    from planner_app.models import Wall, Column, Arrow, Stair, Counter, Door, Fireplace
    from fixtures.native_paths_reference_20261017 import ReferenceViewport
    p = QtCore.QPointF
    walls = [Wall(p(0, 0), p(4000, 0), 240), Wall(p(4000, 0), p(4000, 3000), 240),
             Column(p(1500, 1000), p(1500, 1800), 700),
             Arrow(p(-1000, 500), p(2000, 2700), 80),
             Stair(p(0, -1000), p(0, -3000), 900),
             Counter(p(500, 2500), p(2500, 2500), 600)]
    # Keep openings above the 10-pixel expanded hit area added after this frozen
    # reference. Tiny-opening selection is covered by check_problem_duplicate_repair.
    openings = [Door(walls[0], .2, .5), Fireplace(walls[1], .3, .7)]
    views = [DrawingViewport(), ReferenceViewport()()]
    for case in range(3):
        for view in views:
            view.walls, view.windows = walls, openings
            view.setFixedSize(1000, 900)
            view.zoom = (.05, .2, 1.5)[case]
            view.panOffset = p(.37, .71)
            view.SetSelection([(openings[1], None)] if case == 1 else [])
        for x in range(-1000, 5001, 300):
            for y in range(-3200, 3500, 350):
                position = views[0].WorldToViewport(p(x, y))
                actual, expected = [view.HitTest(position) for view in views]
                assert actual[0] is expected[0] and actual[1] == expected[1], (case, x, y,
                    type(actual[0]).__name__, actual[1], type(expected[0]).__name__, expected[1])
        for first in walls + openings:
            for second in walls + openings:
                assert views[0].JoinedObjectsOverlap(first, second) == views[1].JoinedObjectsOverlap(first, second)
    junctionCases = 0
    footprintCases = 0
    for degrees, widths, amount in itertools.product((30, 90, 135), ((120, 120), (120, 360)), (0, .5, 1)):
        radians = math.radians(degrees)
        walls = [Wall(p(), p(5000, 0), widths[0], amount, 0),
                 Wall(p(), p(math.cos(radians), math.sin(radians)) * 5000, widths[1], amount, 0)]
        paths = []
        fills = []
        for view in views:
            view.SetSelection([])
            view.walls, view.windows = walls, []
            path = view.ConnectedWallPath(walls)
            paths.append([(path.elementAt(index).x, path.elementAt(index).y, path.elementAt(index).type)
                          for index in range(path.elementCount())])
            fills.append([(id(owner), [(point.x(), point.y()) for point in polygon])
                          for owner, polygon in view.wallFillPolygons])
            assert view.ConnectedWallPath(walls) == path, ("warm junction", degrees, widths, amount)
        assert paths[0] == paths[1], ("junction outline", degrees, widths, amount)
        assert fills[0] == fills[1], ("junction ownership", degrees, widths, amount)
        footprintCases += any(any(entry[4].values()) for entry in views[1].wallJunctionCache.values())
        junctionCases += 1
    assert footprintCases > 0, "Junction fixtures did not exercise footprint clipping planes"
    for view in views: view.close()
    print("PASS: 1260 frozen hit tests and mixed curved collision pairs at three zoom levels")
    print("PASS: 8 frozen curved/text/transparent scenes, identical PNG and rasterized SVG pixels")
    print(f"PASS: {junctionCases} junction API cases with exact outlines, ownership and warm-cache parity")


if __name__ == "__main__":
    Main()
