"""Frozen containment/picking parity and exact scene-preparation pixels."""
import math
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app import models
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.viewport.widget import DrawingViewport
from planner_app.geometry.spatial_index import BoundsIndex
from fixtures.parity_examples import CreateObject, objectTypes
from fixtures.qt_containment_hover_reference_20261030 import ReferenceViewport, ReferenceGeometry
from check_numpy_containment import MakeWalls


def SyncReference(view, reference):
    for name in ("walls", "windows", "furnishings", "labels", "hiddenObjectIds", "visibility", "collisionSettings",
                 "zoom", "panOffset", "unitsMode", "measurementPrecision", "lineWidths", "showMeasurements",
                 "hoverPosition", "isDragging", "dragStart", "solidObjects", "pendingWall", "pendingShapeWalls",
                 "hoveredAngleGuide", "furnishingRotationObject"):
        setattr(reference, name, getattr(view, name))
    reference.SetSelection(view.SelectionEntries(), notify = False)
    reference.selectedWall, reference.selectedVertex = view.selectedWall, view.selectedVertex


def CompareHits(view, reference, positions, context):
    SyncReference(view, reference)
    for position in positions:
        expected = reference.HitTest(position)
        actual = view.HitTest(position)
        assert actual[0] is expected[0] and actual[1] == expected[1], (context, position, actual, expected)


def Frame(view):
    image = QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    view.render(image)
    return image


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    LoadApplicationFonts(app)
    view = DrawingViewport()
    reference = ReferenceViewport(furnishingDefinitions = view.furnishingDefinitions)
    for viewport in (view, reference):
        viewport.resize(1000, 700)
        viewport.showTips = False
        viewport.hoveredAngleGuide = None
    point = QtCore.QPointF
    rng = random.Random(20261031)
    index = BoundsIndex(100)
    rectangles = []
    for position in range(200):
        left, top = rng.uniform(-5000, 5000), rng.uniform(-5000, 5000)
        size = 20000 if position % 11 == 0 else rng.uniform(0, 400)
        rectangles.append((left, top, left + size, top + size / 2))
        index.Insert(rectangles[-1], position)
    for left, top, right, bottom in rectangles:
        for target in ((left, top), (right, bottom), ((left + right) / 2, (top + bottom) / 2)):
            candidates = index.PointCandidates(target)
            assert candidates == sorted(set(candidates)), "Point candidates changed source order or duplicated entries"
            assert all(position in candidates for position, rect in enumerate(rectangles)
                       if rect[0] <= target[0] <= rect[2] and rect[1] <= target[1] <= rect[3])
    # Both sparse and dense paths preserve the pre-pass NumPy method's order.
    for count in (63, 64, 65, 128, 512, 1024, 2048):
        matrices = [MakeWalls(count),
                    [models.Wall(point(-1000, 0), point(1000, 0), 200) for index in range(count)]]
        if count >= 2048:
            matrices.append([models.Wall(point((index % 32) * 2000, (index // 32) * 2000),
                                        point((index % 32) * 2000 + 1000, (index // 32) * 2000), 200)
                             for index in range(count)])
        for walls in matrices:
            view.walls = walls
            view.containedWallKey = None
            expected = ReferenceGeometry.ContainedWalls(view, walls)
            view.containedWallKey = None
            assert view.ContainedWalls(walls) == expected
            cached = view.ContainedWalls()
            with patch.object(view, "ObjectFootprint", side_effect = AssertionError("Warm scene containment walked footprints")):
                assert view.ContainedWalls() is cached
            # Explicit subsets must not replace the complete-scene result.
            subset = walls[::2]
            view.ContainedWalls(subset)
            assert view.ContainedWalls() is cached
            walls[0].width += 2
            assert view.ContainedWalls() == ReferenceGeometry.ContainedWalls(view, walls)

    hitQueries = 0
    for matrix in range(28):
        objects = [CreateObject(view, name) for name in objectTypes]
        parents = [obj.parentWall for obj in objects if isinstance(obj, models.Window)]
        for index, obj in enumerate(objects):
            if isinstance(obj, models.Window):
                continue
            offset = point((index % 5) * 1700 - 3400, (index // 5) * 1000 - 2500)
            obj.firstVertex += offset
            obj.secondVertex += offset
            if isinstance(obj, models.AngleGuide):
                obj.middleVertex += offset
                obj.textOffset = point(300, 200)
            elif isinstance(obj, models.MeasurementGuide):
                obj.textOffset = point(600, 400)
                if type(obj) is models.MeasurementGuide:
                    obj.depth = 350
        view.walls = parents + [obj for obj in objects if isinstance(obj, models.Wall)]
        view.windows = [obj for obj in objects if isinstance(obj, models.Window)]
        view.furnishings = [obj for obj in objects if isinstance(obj, models.Furnishing) and not isinstance(obj, models.Label)]
        view.labels = [obj for obj in objects if isinstance(obj, models.Label)]
        view.zoom = (.08, .37, 1, 2.5)[matrix % 4]
        view.panOffset = point(matrix * .37, matrix * -.71)
        view.unitsMode = ("Millimeters", "Meters", "Feet and Inches", "Inches")[matrix % 4]
        view.measurementPrecision = "Low" if matrix % 2 else "High"
        selected = objects[matrix % len(objects)]
        view.SetSelection([(selected, None)] if matrix % 3 else [], notify = False)
        view.hiddenObjectIds = {id(objects[4])} if matrix % 5 == 0 else set()
        view.windows[0].length = 0 if matrix % 2 else 700
        view.windows[1].windowWell = True
        view.windows[1].wellDepth = 1400
        positions = [point(rng.uniform(-200, 1200), rng.uniform(-200, 900)) for index in range(24)]
        for obj in objects:
            for vertex in models.ObjectControlPoints(obj):
                position = view.WorldToViewport(vertex)
                positions.extend((position, position + point(4.99, .01), position + point(10.01, 0)))
            positions.append(view.WorldToViewport((obj.firstVertex + obj.secondVertex) / 2))
        CompareHits(view, reference, positions, matrix)
        hitQueries += len(positions)
        # Moving a cached point or changing label precision must refresh picking.
        if not isinstance(selected, models.Window):
            selected.firstVertex.setX(selected.firstVertex.x() + 13.7)
        view.measurementPrecision = "High" if view.measurementPrecision == "Low" else "Low"
        view.lineWidths = {**view.lineWidths, "dimensions": 20}
        CompareHits(view, reference, positions[::9], (matrix, "edited"))
        if matrix < 8:
            view.hoverPosition = positions[matrix]
            view.showMeasurements = matrix % 2 == 0
            SyncReference(view, reference)
            assert Frame(view) == Frame(reference), ("editor pixels", matrix)

    view.windows, view.furnishings, view.labels = [], [], []
    view.hiddenObjectIds = set()
    view.SetSelection([], notify = False)
    for width in (0, .000001, 100):
        wall = models.Wall(point(-1500, 0), point(1500, 0), width)
        view.walls = [wall]
        for zoom in (.02, .37, 1, 10):
            view.zoom = zoom
            middle = view.WorldToViewport(point())
            CompareHits(view, reference, [middle + point(0, offset) for offset in (-5, -4.99999, 0, 4.99999, 5)],
                        ("degenerate/boundary", width, zoom))

    wall = models.Wall(point(1e11, 1e11), point(1e11 + 3000, 1e11), 200)
    view.walls = [wall]
    view.zoom = 100
    scale = view.basePixelsPerMillimeter * view.zoom
    view.panOffset = point(-1e11 * scale, 1e11 * scale)
    probe = view.WorldToViewport(wall.firstVertex) - point(view.vertexSnapRange - .2, 0)
    assert view.HitTest(probe) == (wall, 0)
    oldRevision = view.renderChanges.geometry
    target = wall.firstVertex + point(.02, 0)
    assert wall.firstVertex == target, "Fixture must exercise Qt's fuzzy point equality"
    wall.firstVertex = target
    assert view.renderChanges.geometry > oldRevision, "Small far-origin assignment bypassed geometry revisions"
    CompareHits(view, reference, [probe], "far-origin point assignment")
    assert view.HitTest(probe) == (None, None), "A cached endpoint survived its exact coordinate edit"
    view.zoom, view.panOffset = 1, point()

    # Actual warm queries should neither reread every footprint nor rebuild
    # complete connected paths. The exact predicates still run near targets.
    view.walls = [models.Wall(point(index * 2000, 0), point(index * 2000 + 1000, 0)) for index in range(128)]
    view.windows, view.furnishings, view.labels = [], [], []
    view.SetSelection([], notify = False)
    view.hiddenObjectIds = set()
    view.HitTest(point(-100000, -100000))
    with patch.object(view, "ObjectFootprint", side_effect = AssertionError("Warm hover reread footprints")), \
            patch.object(view, "ConnectedWallPath", side_effect = AssertionError("Warm hover remapped the full wall path")):
        for index in range(20):
            assert view.HitTest(point(-100000 + index, -100000)) == (None, None)
    state = view.hitTestScene[1]
    view.ZoomBy(1.1, point(300, 250))
    view.HitTest(point(-100000, -100000))
    assert view.hitTestScene[1] is state, "Camera navigation rebuilt world-space picking data"
    view.isDragging, view.dragStart = True, point(400, 300)
    view.selectedWall, view.selectedVertex = view.walls[0], None
    view.walls[0].width += 1
    with patch.object(view, "CoincidentObjectGroups", wraps = view.CoincidentObjectGroups) as groups:
        Frame(view)
        assert groups.call_count == 1, "A paint serialized coincident objects twice"
    SyncReference(view, reference)
    assert Frame(view) == Frame(reference), "Drag preparation changed pixels"
    view.walls = []
    view.selectedWall = view.dragStart = None
    view.isDragging = False
    view.hoverPosition = None
    Frame(view)
    assert view.hitTestScene is None, "Clearing the scene retained its picking snapshot"
    for viewport in (view, reference):
        viewport.close()
    print(f"PASS: sparse/dense containment, {hitQueries} frozen picking queries, cache invalidation and exact editor frames.")


if __name__ == "__main__":
    Main()
