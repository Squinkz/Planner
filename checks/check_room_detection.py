"""Cached wall enclosures and theme-controlled room backgrounds, without room objects."""
import os
import json
import math
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Door, Furnishing, Counter
from planner_app.room_detection import DetectRooms
from planner_app.graphics.palette import themeColors
from planner_app.viewport.geometry import FootprintGeometry
from check_scene_render_cache import CompareDirect as CompareScene
from check_pan_dpi import CompareDirect as ComparePan


def Rectangle(x, y, width, height):
    points = [QtCore.QPointF(x, y), QtCore.QPointF(x + width, y),
              QtCore.QPointF(x + width, y + height), QtCore.QPointF(x, y + height)]
    return [Wall(first, second, 200) for first, second in zip(points, points[1:] + points[:1])]


def Main():
    p = QtCore.QPointF
    walls = Rectangle(0, 0, 4000, 4000)
    geometry = FootprintGeometry(1.0)
    rooms, count = DetectRooms(walls, geometry)
    assert count == 1 and rooms.contains(p(2000, 2000))
    assert not rooms.contains(p(-1000, 2000)) and not rooms.contains(p(0, 2000))
    assert rooms.boundingRect() == QtCore.QRectF(100, 100, 3800, 3800)
    assert geometry.roomRegions[0]["area"] == 14440000
    for duplicate in (Wall(p(0, 0), p(4000, 0), 200), Wall(p(4000, 0), p(0, 0), 200)):
        duplicateRooms, duplicateCount = DetectRooms(walls + [duplicate], geometry)
        assert duplicateCount == 1 and duplicateRooms.contains(p(2000, 2000))
    # A rotated enclosure uses the same inside wall faces, not axis-aligned bounds.
    diamond = [p(0, 3000), p(3000, 0), p(0, -3000), p(-3000, 0)]
    rotated = [Wall(first, second, 200) for first, second in zip(diamond, diamond[1:] + diamond[:1])]
    rotatedRooms, rotatedCount = DetectRooms(rotated, geometry)
    assert rotatedCount == 1 and rotatedRooms.contains(p()) and not rotatedRooms.contains(p(2500, 2500))
    # Open spaces and disconnected wall ends do not acquire an implicit closure.
    assert DetectRooms(walls[:-1], geometry)[0].isEmpty()
    gap = [Wall(p(0, 0), p(0, 1500), 200), Wall(p(0, 2000), p(0, 4000), 200)]
    assert DetectRooms(walls[:-1] + gap, geometry)[0].isEmpty()
    split = Wall(p(2000, 0), p(2000, 4000), 200)
    rooms, count = DetectRooms(walls + [split], geometry)
    assert count == 2 and rooms.contains(p(1000, 2000)) and rooms.contains(p(3000, 2000))
    assert sorted(region["area"] for region in geometry.roomRegions) == [6840000, 6840000]
    assert not rooms.contains(p(2000, 2000))
    rooms, count = DetectRooms(walls + [split, Wall(p(0, 2000), p(4000, 2000), 200)], geometry)
    assert count == 4 and all(rooms.contains(p(x, y)) for x in (1000, 3000) for y in (1000, 3000))
    # Separate buildings, negative coordinates and nested wall islands.
    rooms, count = DetectRooms(walls + Rectangle(-6000, -5000, 3000, 3000), geometry)
    assert count == 2 and rooms.contains(p(-4500, -3500)) and not rooms.contains(p(-2000, -1000))
    rooms, count = DetectRooms(Rectangle(-5000, -5000, 10000, 10000) + Rectangle(-1000, -1000, 2000, 2000), geometry)
    assert count == 2 and rooms.contains(p()) and rooms.contains(p(3000, 3000)) and not rooms.contains(p(1000, 0))
    assert sorted(region["area"] for region in geometry.roomRegions) == [3240000, 91200000]
    # Dexter's small enclosure has a traced corner a few floating-point steps
    # beyond its surrounding contour. Do not classify that corner as exterior.
    records = json.loads((Path(__file__).parent / "fixtures/dexter_room_walls.json").read_text(encoding = "utf-8"))
    dexter = [Wall(p(*first), p(*second), width) for first, second, width in records]
    rooms, count = DetectRooms(dexter, geometry)
    assert count == 6 and rooms.contains(p(-1515, -380))
    small = next(region for region in geometry.roomRegions if region["path"].contains(p(-1515, -380)))
    assert math.isclose(small["area"], 210 * 1440, abs_tol = 1e-6)
    # Reversing endpoints and translating must not change the classification.
    for offset in (p(), p(1e8, -1e8)):
        translated = [Wall(wall.secondVertex + offset, wall.firstVertex + offset, wall.width) for wall in dexter]
        rooms, count = DetectRooms(translated, geometry)
        assert count == 6 and rooms.contains(p(-1515, -380) + offset)
    # Closing/reopening walls changes the cached geometry; unrelated edits don't.
    with ExampleWindow() as (main, folder):
        v = main.viewport
        InstallScene(main, walls)
        detector = v.roomDetection
        detector.Refresh()
        assert detector.count == 1
        builds = detector.rebuildCount
        with patch("planner_app.room_detection.BuildRoomBoundary", side_effect = AssertionError("Room detection ran during idle paint")):
            for index in range(5):
                v.panOffset += p(11, -7)
                v.zoom = .5 + index / 10
                detector.Check()
                v.grab()
        assert detector.rebuildCount == builds
        desk = Furnishing(v.furnishingDefinitions["desk"], p(2000, 2000))
        v.furnishings = [desk]
        detector.Check()
        detector.Refresh()
        assert detector.rebuildCount == builds
        desk.firstVertex += p(50, 0)
        detector.Check()
        assert detector.rebuildCount == builds
        door = Door(walls[0], .3, .6)
        v.windows = [door]
        detector.Check()
        detector.Refresh()
        assert detector.count == 1 and detector.rebuildCount == builds
        door.length = 400
        detector.Check()
        assert detector.rebuildCount == builds
        v.walls.append(Counter(p(-3000, 0), p(-3000, 2000), 600))
        detector.Check()
        detector.Refresh()
        assert detector.rebuildCount == builds
        # Wall edits update immediately, including during an active drag.
        before = v.CaptureState()
        for value in (4100, 4200, 4300):
            walls[0].secondVertex.setX(value)
            detector.Check()
        assert detector.rebuildCount == builds + 3
        v.RestoreState(before)
        detector.Check()
        detector.Refresh()
        assert detector.count == 1
        v.walls = walls[:-1]
        detector.Check()
        detector.Refresh()
        assert detector.path.isEmpty() and detector.count == 0
        v.walls = walls
        detector.Check()
        detector.Refresh()
        assert detector.count == 1
        # Room-aware cached scene and exposed-strip pan frames match full paint.
        v.zoom = .5
        v.panOffset = p()
        CompareScene(v)
        v.isPanning = True
        for offset in (p(3, 1), p(-10, 5), p(70, -110), p(-600, 300)):
            v.panOffset += offset
            ComparePan(v)
        v.isPanning = False
        v.panOffset = p(-200, 200)
        v.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/room-grid-preview.png"))
        # Only the canvas fill changes; grid pens and reference images are preserved.
        v.referenceImage = None
        v.zoom = .5
        v.panOffset = p()
        v.gridOrigin = (0, 0)
        origin, scale = p(300, 700), .1
        rect = QtCore.QRectF(0, 0, 1000, 900)
        class GridPainter(QtGui.QPainter):
            def drawLines(self, lines):
                alphas.append(self.pen().color().alpha())
                super().drawLines(lines)

        images, penAlphas = [], []
        canvas = QtGui.QColor(themeColors["canvas"])
        roomFill = QtGui.QColor(themeColors["roomFill"])
        cached = detector.path
        for path in (QtGui.QPainterPath(), cached):
            detector.path = path
            image = QtGui.QImage(1000, 900, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(canvas)
            alphas = []
            with GridPainter(image) as painter:
                v.DrawGridBackground(painter, rect, origin, scale, gridOnly = True)
            images.append(image)
            penAlphas.append(alphas)
        inside, outside = QtCore.QPoint(400, 577), QtCore.QPoint(200, 577)
        assert penAlphas[0] == penAlphas[1] and any(penAlphas[0])
        assert images[0].pixelColor(401, 577) == canvas
        assert images[1].pixelColor(401, 577) == roomFill
        assert images[0].pixelColor(outside) == images[1].pixelColor(outside)
        reference = main.referenceImage
        v.referenceImage = reference
        green = QtGui.QColor("green")
        referenceFrames = []
        with patch.object(reference, "Draw", side_effect = lambda painter, rect: painter.fillRect(rect, green)):
            for path in (QtGui.QPainterPath(), cached):
                detector.path = path
                image = QtGui.QImage(1000, 900, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(QtCore.Qt.GlobalColor.transparent)
                with QtGui.QPainter(image) as painter:
                    v.DrawGridBackground(painter, rect, origin, scale, gridOnly = True)
                referenceFrames.append(image)
        assert referenceFrames[1].pixelColor(401, 577) == green
        assert referenceFrames[0].pixelColor(outside) == referenceFrames[1].pixelColor(outside)
        assert referenceFrames[0] == referenceFrames[1]
        v.referenceImage = None
        # A grid-origin offset must not move the room mask itself.
        v.gridOrigin = (300, -200)
        with QtGui.QPainter(images[1]) as painter:
            painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(rect, canvas)
            painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)
            v.DrawGridBackground(painter, rect, origin, scale, gridOnly = True)
        assert images[1].pixelColor(321, 577) == roomFill
        assert images[1].pixelColor(309, 577) == canvas
        v.showGrid = False
        image = QtGui.QImage(1000, 900, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(canvas)
        with QtGui.QPainter(image) as painter:
            v.DrawGridBackground(painter, rect, origin, scale, gridOnly = True)
        assert image.pixelColor(400, 577) == roomFill
        assert image.pixelColor(200, 577) == canvas
        v.showGrid = True
        # Floor shading can be disabled without changing the grid or enclosure.
        v.exportRender = True
        v.floors = False
        image = QtGui.QImage(1000, 900, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(canvas)
        v.gridOrigin = (0, 0)
        with QtGui.QPainter(image) as painter:
            v.DrawGridBackground(painter, rect, origin, scale, gridOnly = True)
        assert image == images[0]
        v.exportRender = False
        v.floors = True
        detector.path = cached
        v.windows = []
        v.walls = []
        detector.Check()
        detector.Refresh()
        assert detector.path.isEmpty()
    # Shared long walls intersect to create a grid of bounded faces.
    walls = [Wall(p(x, 0), p(x, 20000), 200) for x in range(0, 20001, 2000)]
    walls += [Wall(p(0, y), p(20000, y), 200) for y in range(0, 20001, 2000)]
    started = perf_counter()
    rooms, count = DetectRooms(walls, FootprintGeometry(1.0))
    assert count == 100
    print(f"Room detection: 100 crossing-wall rooms in {(perf_counter() - started) * 1000:.1f} ms")
    print("Rooms: enclosures/partitions/islands/gaps, wall-only invalidation, cached paint and optional floor shading passed")


if __name__ == "__main__":
    Main()
