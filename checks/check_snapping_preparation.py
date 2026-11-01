"""Exact frozen snapping parity, lookup reuse, invalidation and editor pixels."""
import math
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'planner-main'))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.geometry.snapping import PrepareTargetIndex, PrepareRayTargets
from planner_app.geometry.resize_snapping import SnapResize
from planner_app.geometry.movement_snapping import SnapMovement
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.viewport import snapping
from planner_app.viewport.widget import DrawingViewport
from planner_app import models
from fixtures.parity_examples import CreateObject, objectTypes
from fixtures.qt_snapping_preparation_reference_20261030 import (
    ReferenceViewport, SnapResize as ReferenceResize, SnapMovement as ReferenceMovement)


def State(view):
    return view.snapApplied, view.snapPriority, list(view.alignmentGuides)


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle('Fusion')
    LoadApplicationFonts(app)
    rng = random.Random(20261030)
    # Keep target duplicates/source order, strict distance boundaries, arbitrary
    # edge contacts, normalized/unnormalized rays and label minimum sizes.
    for case in range(2400):
        offset = (0, 1e8, 1e12)[case % 3]
        count = (0, 8, 31, 32, 33, 64, 129, 256)[case % 8]
        targets = [(offset + rng.uniform(-1000, 1000), -offset + rng.uniform(-1000, 1000), bool(index % 3)) for index in range(count)]
        if case % 4 == 0 and targets:
            targets += targets[:10]
        angle = case * .137
        north = ((0, 1), (.6, .8), (math.sin(angle), math.cos(angle)), (1, 1e-11), (1, 1))[case % 5]
        field = ('width', 'length', 'corner')[case % 3]
        args = (north, (offset, -offset), 250, 700, rng.uniform(1, 1000), rng.uniform(1, 1800), field,
                (-1, 1) if field == 'corner' else (-1, 1)[case % 2], bool(case % 2), .001 if case % 7 == 0 else 1,
                targets, (.0001, .03, .2, 1, 12)[case % 5], (0, 14, 20)[case % 3], bool(case % 4), 25.4 if case % 3 else None)
        prepared = PrepareRayTargets(targets) if len(targets) > 32 else None
        assert SnapResize(*args, rayTargets = prepared) == ReferenceResize(*args), ('resize', case)
        if case < 400:
            anchors = [(offset + index * 83, -offset + index * 29) for index in range(1 + case % 6)]
            direction = None if case % 2 else north
            movementArgs = (anchors, (case * .37, case * .17), targets, .2, 14, bool(case % 3), 25.4, direction)
            assert SnapMovement(*movementArgs, targetIndex = PrepareTargetIndex(targets) if direction is None and len(targets) > 32 else None,
                                rayTargets = prepared if direction is not None and len(anchors) >= 3 else None) == ReferenceMovement(*movementArgs), ('movement', case)
    for bad in (float('nan'), float('inf'), -float('inf')):
        targets = [(index, index * .5, True) for index in range(40)] + [(bad, 0, True)]
        args = ((0, 1), (0, 0), 100, 200, 110, 220, 'width', 1, False, 1, targets, .2, 14, True, 25.4)
        assert SnapResize(*args, rayTargets = PrepareRayTargets(targets)) == ReferenceResize(*args)

    view = DrawingViewport()
    reference = ReferenceViewport(furnishingDefinitions = view.furnishingDefinitions)
    point, modifier = QtCore.QPointF, QtCore.Qt.KeyboardModifier
    objects = [CreateObject(view, name) for name in objectTypes]
    objects += list({id(obj.parentWall): obj.parentWall for obj in objects if isinstance(obj, models.Window)}.values())
    selected = next(obj for obj in objects if type(obj) is models.Furnishing)
    for viewport in (view, reference):
        viewport.resize(1000, 750)
        viewport.showMeasurements = viewport.showTips = False
        viewport.walls = [obj for obj in objects if isinstance(obj, models.Wall)]
        viewport.windows = [obj for obj in objects if isinstance(obj, models.Window)]
        viewport.furnishings = [obj for obj in objects if isinstance(obj, models.Furnishing) and not isinstance(obj, models.Label)]
        viewport.labels = [obj for obj in objects if isinstance(obj, models.Label)]
        viewport.SetSelection([(selected, None)], notify = False)
        viewport.dragStart, viewport.isDragging = point(400, 300), True
    for case in range(120):
        selected.secondVertex += point(.13, .17)
        if case % 9 == 0:
            objects[0].firstVertex += point(3, -7)
        results = []
        for viewport in (view, reference):
            viewport.snapEnabled = bool(case % 7)
            viewport.vertexSnapEnabled, viewport.cornerSnapEnabled = bool(case % 3), bool(case % 4)
            viewport.midpointSnapEnabled, viewport.alignmentSnapEnabled, viewport.gridSnapEnabled = bool(case % 2), bool(case % 5), bool(case % 6)
            viewport.unitsMode = 'Feet and Inches' if case % 3 else 'Millimeters'
            viewport.zoom = (.03, .5, 2)[case % 3]
            viewport.panOffset = point(case * .37, -case * .71)
            viewport.hiddenObjectIds = {id(objects[case % len(objects)])} if case % 4 else set()
            viewport.visibility['Walls'] = bool(case % 8)
            viewport.visibility['World'] = bool(case % 11)
            state = dict(object = selected, members = [], north = point(.6, .8), center = point(),
                         width = 1200, length = 600, handle = ('resize', ('width', 'length', 'corner')[case % 3],
                             (1, -1) if case % 3 == 2 else 1), centeredResize = bool(case % 2))
            viewport.furnishingHandleDrag = state
            attachments = [(objects[0], case % 2, point(objects[0].firstVertex))] if case % 2 else []
            with patch.object(viewport, 'ActiveAttachments', return_value = attachments):
                vertices = [(type(vertex).__name__, vertex.x(), vertex.y()) for vertex in viewport.SnapVertices()]
                footprints = [(vertex.x(), vertex.y()) for vertex in viewport.StairSnapTargets(selected)]
                midpoints = [(vertex.x(), vertex.y()) for vertex in viewport.SnapMidpoints()]
                targets = viewport.StairSnapTargets(selected) + list(viewport.SnapVertices())
                modifiers = (modifier.NoModifier, modifier.ControlModifier, modifier.AltModifier)[case % 3]
                travel = viewport.SnapObjectMovement([point(), point(83, 29), point(166, 58), point(249, 87)],
                    point(case * 3.7, case * 1.3), modifiers, snapTargets = targets)
                movement = travel.x(), travel.y(), State(viewport)
                size = viewport.SnapFurnishingResize(state, 1200 + case, 600 + case / 2, modifiers)
                results.append((vertices, footprints, midpoints, movement, size, State(viewport)))
        assert results[0] == results[1], ('desktop', case)
        if case % 30 == 1:
            images = []
            for viewport in (view, reference):
                viewport.furnishingHandleDrag = None
                image = QtGui.QImage(viewport.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                viewport.render(image)
                images.append(image)
            assert images[0] == images[1], ('editor pixels', case)
    # Explicit mutable caller targets are validated by value, not list identity.
    view.visibility['World'] = view.visibility['Walls'] = True
    view.snapEnabled = view.vertexSnapEnabled = view.cornerSnapEnabled = True
    view.midpointSnapEnabled = False
    targets = [point(index * 137, index * 73) for index in range(100)]
    view.numericSnapPreparation = None
    with patch.object(snapping, 'PrepareTargetIndex', wraps = PrepareTargetIndex) as prepare:
        for case in range(5):
            view.SnapObjectMovement([point(), point(1, 1), point(2, 2)], point(case, case), modifier.NoModifier, targets)
        assert prepare.call_count == 1
        targets[0].setX(500)
        view.SnapObjectMovement([point()], point(), modifier.NoModifier, targets)
        assert prepare.call_count == 2
    with patch.object(snapping, 'PrepareRayTargets', wraps = PrepareRayTargets) as prepare:
        for case in range(5):
            view.SnapObjectMovement([point(), point(1, 1), point(2, 2)], point(case, case), modifier.ControlModifier, targets)
        assert prepare.call_count == 0, "Unchanged point/coordinate lookups should also serve constrained movement"
    view.VisibleSnapObjects()
    with patch.object(view, 'IsObjectVisible', side_effect = AssertionError('Unchanged visibility was recalculated')):
        list(view.SnapVertices())
        list(view.SnapMidpoints())
    added = models.Wall(point(10000, 10000), point(11000, 10000), 200)
    view.walls.append(added)
    assert added in view.VisibleSnapObjects()
    view.walls.reverse()
    expected = tuple(obj for obj in view.walls + view.windows + view.furnishings + view.labels if view.IsObjectVisible(obj))
    assert view.VisibleSnapObjects() == expected
    view.hiddenObjectIds.add(id(added))
    assert added not in view.VisibleSnapObjects()
    view.visibility['World'] = False
    assert view.VisibleSnapObjects() == ()
    view.snapEnabled = False
    with patch.object(view, 'SnapTargetPreparation', side_effect = AssertionError('Disabled snapping prepared targets')):
        view.SnapObjectMovement([point()], point(1, 2), modifier.NoModifier)
        view.SnapFurnishingResize(state, 1200, 600, modifier.NoModifier)
    view.walls = []
    assert getattr(view, 'numericSnapPreparation', None) is None
    assert getattr(view, 'visibleSnapObjects', None) is None
    for viewport in (view, reference):
        viewport.close()
    print('PASS: 2,400 frozen resize and 400 movement matrices; 120 desktop policy/invalidation cases; exact editor frames and bounded lookup reuse.')


if __name__ == '__main__':
    Main()
