"""Frozen native column paths, ordered occluders, footprints and exact pixels."""
import math
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'planner-main'))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Pillar, Column, Door
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.viewport import geometry
from planner_app.viewport.widget import DrawingViewport
from check_connections_opening_jambs import SceneImage
from fixtures.qt_column_occlusion_reference_20261030 import ReferenceViewport


def PathValues(path):
    return path.fillRule(), tuple((element.type, element.x.hex(), element.y.hex())
        for index in range(path.elementCount()) for element in (path.elementAt(index),))


def Snapshot(view):
    return (PathValues(view.wallGeometryPath),
            [(PathValues(path), PathValues(occluders)) for path, occluders in view.columnOutlinePaths],
            {key: PathValues(path) for key, path in view.columnMaterialPaths.items()},
            [(id(owner), tuple((point.x().hex(), point.y().hex()) for point in polygon)) for owner, polygon in view.wallFillPolygons])


def Compare(view, reference, label, trace = True):
    paths = []
    for viewport in (view, reference):
        members = [obj for obj in viewport.walls if viewport.IsObjectVisible(obj)]
        paths.append(PathValues(viewport.ConnectedWallPath(members, trace)))
    assert paths[0] == paths[1], ('viewport path', label)
    assert Snapshot(view) == Snapshot(reference), ('native geometry/occluder order', label)


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle('Fusion')
    LoadApplicationFonts(app)
    point = QtCore.QPointF
    rng = random.Random(20261030)
    view = DrawingViewport()
    reference = ReferenceViewport(furnishingDefinitions = view.furnishingDefinitions)
    for viewport in (view, reference):
        viewport.resize(1000, 750)
        viewport.showMeasurements = viewport.showTips = False
    matrices = 0
    for case, count in enumerate((1, 8, 31, 32, 33, 40, 64, 40, 40, 40)):
        layout = case % 4
        offset = point(1e8, -1e8) if case == 7 else point()
        spacing = 100 if layout == 2 else 600 if layout == 3 else 1500
        columns = 8 if layout in (1, 2) else count
        wall = Wall(offset + point(-3000, 0), offset + point(3000, 0), 200, material = 'Brick')
        objects = [wall, Pillar(offset + point(-1000, -400), offset + point(-1000, 400), 200)]
        for index in range(count):
            center = offset + point(index % columns * spacing, index // columns * spacing)
            angle = index * .137 if case % 2 else 0
            axis = point(math.sin(angle), math.cos(angle)) * (300 + index % 3 * 50)
            objects.append(Column(center - axis, center + axis, (600, 200, 0)[index % 3] if case == 8 else 600,
                                  material = ('Generic', 'Concrete', 'Lumber')[index % 3]))
        if case == 9:
            objects.append(objects[-1])
        if case % 3 == 0:
            rng.shuffle(objects)
        for viewport in (view, reference):
            viewport.walls = objects
            viewport.windows = [Door(wall, .4, .6)]
            viewport.hiddenObjectIds = set()
            viewport.SetSelection([], notify = False)
            viewport.basePixelsPerMillimeter = .1
            viewport.zoom = .6
            viewport.panOffset = point(.37 - offset.x() * .06, .71 + offset.y() * .06)
            viewport.solidObjects = case % 3 != 0
            viewport.wallStyle = ('Outline', 'Solid', 'Material')[case % 3]
        last = next(obj for obj in reversed(objects) if isinstance(obj, Column))
        first = next(obj for obj in objects if isinstance(obj, Column))
        for frame in range(7):
            if frame == 1:
                last.secondVertex += point(17, -11)
            elif frame == 2:
                last.firstVertex += point(-9, 21)
            elif frame == 3:
                wall.secondVertex += point(17, -11)
            elif frame == 4:
                first.width += 31
            elif frame == 5:
                for viewport in (view, reference):
                    viewport.zoom *= 1.17
                    scale = viewport.basePixelsPerMillimeter * viewport.zoom
                    viewport.panOffset = point(17.74 - offset.x() * scale, -9 + offset.y() * scale)
            elif frame == 6:
                for viewport in (view, reference):
                    viewport.hiddenObjectIds = {id(first)}
            Compare(view, reference, (case, frame), trace = case % 2 == 0)
            matrices += 1
        # Mixed trace settings, scale and source order invalidate the right data.
        for viewport in (view, reference):
            viewport.hiddenObjectIds = set()
            viewport.walls.reverse()
            viewport.basePixelsPerMillimeter *= 1.25
            scale = viewport.basePixelsPerMillimeter * viewport.zoom
            viewport.panOffset = point(.37 - offset.x() * scale, .71 + offset.y() * scale)
        Compare(view, reference, (case, 'order/scale'), trace = True)
        if case == 5:
            middle = [obj for obj in view.walls if isinstance(obj, Column)][20]
            for frame in range(3):
                middle.secondVertex += point(.37, .13)
                Compare(view, reference, ('grid middle checkpoint', frame))
                assert view.columnExteriorPrefix[2] == 20
        if case in (1, 2, 3, 5, 7):
            for svg in (False, True):
                assert SceneImage(view, svg) == SceneImage(reference, svg), ('raster/SVG', case, svg)
            images = []
            for viewport in (view, reference):
                image = QtGui.QImage(viewport.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                viewport.render(image)
                images.append(image)
            assert images[0] == images[1], ('editor pixels', case)
    # Stable columns survive unrelated wall edits; only a changed column asks
    # for its native curve and collision polygon again.
    wall = Wall(point(-10000, -5000), point(-5000, -5000), 200)
    objects = [wall] + [Column(point(index * 2000, -300), point(index * 2000, 300), 600) for index in range(64)]
    for viewport in (view, reference):
        viewport.walls, viewport.windows = objects, []
        viewport.hiddenObjectIds = set()
        viewport.basePixelsPerMillimeter = .1
    Compare(view, reference, 'warm')
    retained = view.columnGeometryPreparation
    for viewport in (view, reference):
        viewport.ConnectedWallPath([wall])
    assert view.columnGeometryPreparation is retained, 'A regular-only scratch query discarded column preparation'
    Compare(view, reference, 'regular-only scratch query')
    with patch.object(geometry, 'ColumnPath', side_effect = AssertionError('Unchanged columns rebuilt')):
        wall.secondVertex += point(1, 0)
        view.ConnectedWallPath(view.walls)
    reference.ConnectedWallPath(reference.walls)
    assert Snapshot(view) == Snapshot(reference)
    with patch.object(geometry, 'ColumnPath', wraps = geometry.ColumnPath) as curves, \
            patch.object(geometry, 'ColumnPolygon', wraps = geometry.ColumnPolygon) as polygons:
        objects[-1].secondVertex += point(1, 0)
        view.ConnectedWallPath(view.walls)
        assert curves.call_count == polygons.call_count == 1
    reference.ConnectedWallPath(reference.walls)
    assert Snapshot(view) == Snapshot(reference)
    for frame in range(3):
        objects[33].secondVertex += point(.7, .3)
        Compare(view, reference, ('adaptive middle checkpoint', frame))
        assert view.columnExteriorPrefix[2] == 32
    # Drawing results remain writable without corrupting retained preparation.
    for viewport in (view, reference):
        viewport.columnMaterialPaths[id(objects[-1])].translate(17, 23)
        viewport.columnOutlinePaths[-1][0].translate(17, 23)
        viewport.columnOutlinePaths[0][1].translate(17, 23)
        viewport.wallFillPolygons[-1][1].translate(17, 23)
    wall.secondVertex += point(1, 0)
    Compare(view, reference, 'public wrapper isolation')
    # A checkpoint is optional and never retains more than 32,768 elements.
    large = QtGui.QPainterPath(point(-10000, -5000))
    for index in range(33000):
        large.lineTo(point(-10000 + index % 100, -5000 + index // 100))
    for viewport in (view, reference):
        workspace = viewport.columnWallWorkspace
        workspace.wallGeometryPath = QtGui.QPainterPath(large)
        workspace.wallGeometryKey = ('large checkpoint fixture',)
        with patch.object(workspace, 'ConnectedWallPath', return_value = large):
            viewport.wallGeometryKey = None
            viewport.ConnectedColumnWallPath(viewport.walls, True)
    assert Snapshot(view) == Snapshot(reference)
    assert 'columnExteriorPrefix' not in view.__dict__
    # In-place removal also releases preparation once the scene has no columns.
    view.walls[:] = [wall]
    view.ConnectedWallPath(view.walls)
    assert 'columnGeometryPreparation' not in view.__dict__ and 'columnExteriorPrefix' not in view.__dict__
    view.walls = [wall]
    assert 'columnGeometryPreparation' not in view.__dict__ and 'columnExteriorPrefix' not in view.__dict__
    view.ConnectedWallPath(view.walls)
    assert not view.columnOutlinePaths and not view.columnMaterialPaths
    for viewport in (view, reference):
        viewport.close()
    print(f'PASS: {matrices} frozen native column matrices, exact raster/SVG/editor frames, selective reuse, writable-result isolation and bounded checkpoint fallback.')


if __name__ == '__main__':
    Main()
