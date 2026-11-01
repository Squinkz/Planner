"""Frozen geometry, room and editor parity through live wall transformations."""
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'planner-main')]
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Pillar, Stair, Counter, Door, SilledWindow, Furnishing, RoomLabel
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.viewport.widget import DrawingViewport
from check_room_detection import Rectangle
from check_connections_opening_jambs import SceneImage
from fixtures.qt_room_edits_reference_20261030 import ReferenceViewport


def Sync(view, reference):
    for name in ('walls', 'windows', 'furnishings', 'labels', 'hiddenObjectIds', 'visibility', 'collisionSettings',
                 'zoom', 'panOffset', 'lineWidths', 'solidObjects', 'floors', 'solidRooms', 'showMeasurements',
                 'wallMeasurementMode', 'wallStyle', 'connectedEnabled', 'connectedVerticesEnabled', 'connectedObjectsEnabled',
                 'selectedWall', 'selectedVertex', 'dragStart', 'isDragging', 'pendingWall', 'pendingShapeWalls',
                 'axisConstraintOrigin', 'alignmentGuides', 'interactionBefore', 'dragVertices', 'dragAttachments'):
        setattr(reference, name, getattr(view, name))
    reference.SetSelection(view.SelectionEntries(), notify = False)
    reference.selectedWall, reference.selectedVertex = view.selectedWall, view.selectedVertex


def Compare(view, reference, label, editor = True):
    Sync(view, reference)
    for viewport in (view, reference):
        viewport.roomDetection.Check()
    assert view.wallGeometryPath == reference.wallGeometryPath, ('wall path', label)
    assert view.wallFillPolygons == reference.wallFillPolygons, ('owned polygons', label)
    assert [[id(obj) for obj in members] for key, members, path in view.wallGeometryComponents] == [
        [id(obj) for obj in members] for key, members, path in reference.wallGeometryComponents], ('component order', label)
    first, second = view.roomDetection, reference.roomDetection
    assert (first.path, first.count, first.exteriorPath) == (second.path, second.count, second.exteriorPath), ('room paths', label)
    assert first.regions == second.regions, ('regions/areas', label)
    if editor:
        images = []
        for viewport in (view, reference):
            image = QtGui.QImage(viewport.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            viewport.render(image)
            images.append(image)
        assert images[0] == images[1], ('editor pixels', label)


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle('Fusion')
    LoadApplicationFonts(app)
    view = DrawingViewport()
    reference = ReferenceViewport(furnishingDefinitions = view.furnishingDefinitions)
    for viewport in (view, reference):
        viewport.resize(1000, 750)
        viewport.showTips = False
        viewport.showMeasurements = False
        viewport.zoom = .3
    point = QtCore.QPointF
    rng = random.Random(20261030)
    scenes = []
    scenes.append([wall for index in range(64) for wall in Rectangle(index % 8 * 6000, index // 8 * 6000, 4000, 4000)])
    scenes.append([Wall(point(x * 1000, -10000), point(x * 1000, 10000), 200) for x in range(-10, 11)] +
                  [Wall(point(-10000, y * 1000), point(10000, y * 1000), 200) for y in range(-10, 11)])
    scenes.append(Rectangle(-5000, -5000, 10000, 10000) + Rectangle(-1000, -1000, 2000, 2000) +
                  [Wall(point(index * 500, 10000), point(index * 500 + 200, 10000), 100) for index in range(40)])
    for angle in (0, 31, 90):
        transform = QtGui.QTransform().rotate(angle)
        walls = [Wall(transform.map(point(index % 8 * 1000, index // 8 * 1000)),
                      transform.map(point(index % 8 * 1000 + 800, index // 8 * 1000)),
                      (0, 100, 200)[index % 3]) for index in range(64)]
        walls += [Pillar(point(-100, -1000), point(-100, 1000), 200), Counter(point(-3000, 0), point(-1000, 0), 600),
                  Stair(point(2000, -3000), point(2000, -1000), 900)]
        scenes.append(walls)
    scenes.append([Wall(point(index * 100, 0), point((index + 1) * 100, 0), 200) for index in range(128)])
    # Distinct endpoint components can overlap at their bodies or only in their
    # bounding envelopes. Keep exact piece contact and resulting source order.
    scenes.append([wall for index in range(40) for wall in (
        Wall(point(index % 8 * 900, index // 8 * 900), point(index % 8 * 900 + 1000, index // 8 * 900), 100),
        Wall(point(index % 8 * 900 + 1000, index // 8 * 900), point(index % 8 * 900 + 1000, index // 8 * 900 + 1000), 100))])
    for sceneIndex, walls in enumerate(scenes):
        rng.shuffle(walls)
        view.walls = walls
        host = next(obj for obj in walls if type(obj) is Wall)
        view.windows = [Door(host, .2, .4), SilledWindow(host, .6, .8)]
        view.furnishings = [Furnishing(dict(view.furnishingDefinitions['desk']), point(-2000, 2000))]
        view.labels = [RoomLabel(point(2000, 2000), 'Room')]
        view.hiddenObjectIds = set()
        view.selectedWall, view.selectedVertex = host, None
        view.SetSelection([(host, None)], notify = False)
        view.dragStart, view.isDragging = point(400, 300), True
        view.interactionBefore = view.CaptureState()
        view.panOffset = point(.37, .71)
        for frame in range(6):
            host.secondVertex += point(17, -9)
            if frame == 1:
                view.hiddenObjectIds = {id(walls[-1])}
            if frame == 2:
                view.zoom *= 1.1
            if frame == 3:
                view.solidObjects = False
            if frame == 4:
                view.solidObjects = True
                view.wallMeasurementMode, view.showMeasurements = 'Exterior stacked', True
            if frame == 5:
                rotation = QtGui.QTransform().rotate(17)
                for wall in walls:
                    wall.firstVertex, wall.secondVertex = rotation.map(wall.firstVertex), rotation.map(wall.secondVertex)
            Compare(view, reference, (sceneIndex, frame))
        view.showMeasurements = False
        Sync(view, reference)
        for svg in (False, True):
            assert SceneImage(view, svg) == SceneImage(reference, svg), ('raster/SVG', sceneIndex, svg)
    # Whole-body edits keep the original direct-rendering policy.
    view.walls = [Wall(point(index % 16 * 3000, index // 16 * 3000),
                       point(index % 16 * 3000 + 2000, index // 16 * 3000), 200) for index in range(64)]
    view.windows, view.labels, view.furnishings = [], [], []
    host = view.walls[0]
    view.SetSelection([(host, None)], notify = False)
    view.dragStart, view.isDragging = point(400, 300), True
    view.interactionBefore = view.CaptureState()
    view.editDirtyFractionLimit = 1.1
    view.hiddenObjectIds = set()
    view.zoom = .5
    assert not view.CanCacheEditScene()
    for frame in range(7):
        host.firstVertex += point(10, 15)
        host.secondVertex += point(10, 15)
        Compare(view, reference, ('whole drag', frame))
    # Unchanged components keep their native paths even though the complete
    # room boundary is refreshed after an edit to one disconnected component.
    view.dragStart, view.isDragging = None, False
    view.walls = [wall for index in range(128) for wall in Rectangle(index % 16 * 6000, index // 16 * 6000, 4000, 4000)]
    view.SetSelection([], notify = False)
    view.roomDetection.Check()
    with patch.object(view, 'BuildWallComponent', wraps = view.BuildWallComponent) as build:
        view.walls[-1].secondVertex += point(25, 0)
        view.roomDetection.Check()
        assert build.call_count == 1, ('Stationary components rebuilt', build.call_count)
    # Shape, source order and tolerance changes can merge or split components.
    # Include tiny/zero-width pieces and far-origin coordinates in the index.
    for offset in (point(), point(1e8, -1e8)):
        for gap in (0, .009999, .010001, 100):
            walls = [Wall(offset + point(index % 8 * 1000, index // 8 * 1000),
                          offset + point(index % 8 * 1000 + 1000 - gap, index // 8 * 1000),
                          (0, .001, 100, 1200)[index % 4]) for index in range(64)]
            rng.shuffle(walls)
            view.walls = walls
            view.hiddenObjectIds = set()
            Compare(view, reference, ('precision', offset, gap), editor = False)
        # Enough multi-piece components to exercise envelope indexing far from
        # the origin, including nested envelopes without physical contact.
        view.walls = [wall for index in range(40) for wall in Rectangle(
            offset.x() + index % 8 * 6000, offset.y() + index // 8 * 6000, 4000, 4000)]
        view.walls += Rectangle(offset.x() + 1000, offset.y() + 1000, 1000, 1000)
        Compare(view, reference, ('indexed precision', offset), editor = False)
    view.walls, view.windows, view.furnishings, view.labels = [], [], [], []
    Compare(view, reference, 'empty')
    for viewport in (view, reference):
        viewport.close()
    print('PASS: frozen wall/component order, rooms/areas, raster/SVG and exact editor frames through live transformations.')


if __name__ == '__main__':
    Main()
