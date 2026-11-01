"""Frozen complete-state and pixel parity for drag rollback and opening fitting."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'planner-main'))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app import models
from planner_app.scene_changes import SceneObject
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.viewport.widget import DrawingViewport
from fixtures.qt_drag_fitting_reference_20261030 import ReferenceViewport


def Snapshot(view):
    references = {id(obj): (category, index) for category, objects in enumerate((view.walls, view.windows, view.furnishings, view.labels))
                  for index, obj in enumerate(objects)}
    def Normalize(value):
        if isinstance(value, SceneObject):
            return references.get(id(value), type(value).__name__)
        if isinstance(value, QtCore.QPointF):
            return value.x().hex(), value.y().hex()
        if isinstance(value, float):
            return value.hex()
        if isinstance(value, (list, tuple)):
            return tuple(Normalize(item) for item in value)
        return value
    previews = [(type(obj).__name__, references.get(id(obj.parentWall)), obj.centerFraction, obj.length)
                for obj in view.groupOpeningPreviews]
    return Normalize((view.CaptureState(), view.alignmentGuides, view.snapApplied, getattr(view, 'snapPriority', None), previews,
                      view.groupMovedVertices, view.groupMovedOpenings))


def Setup(view, case, group = False):
    point = QtCore.QPointF
    view.CancelInteraction()
    view.snapEnabled = False
    view.connectedEnabled = case % 4 == 0
    view.connectedVerticesEnabled = view.connectedObjectsEnabled = True
    offset = point(1e8, -1e8) if case % 7 == 0 else point()
    host = models.Wall(offset, offset + point(6000, 0), 200)
    neighbor = models.Wall(offset + point(6000, 0), offset + point(10000, 0), 200)
    view.walls = [host, neighbor] + [models.Wall(offset + point(12000 + index * 6000, 0),
        offset + point(16000 + index * 6000, 0), 200) for index in range(40)]
    cls = (models.Door, models.Window, models.SlidingDoor, models.SilledWindow, models.Fireplace,
           models.PocketDoor, models.BarnDoor, models.BifoldDoor)[case % 8]
    view.windows = [cls(host, .2, .35)] if case % 9 else []
    if case % 3:
        view.windows += [models.Door(wall, .25, .5) for wall in view.walls[2::3]]
    view.furnishings = [models.Furnishing(view.furnishingDefinitions['desk'], offset + point(index * 6000, 5000)) for index in range(32)]
    view.labels = [models.Label(offset + point(index * 6000, 8000), 'Label') for index in range(32)]
    selected = [(host, None if case % 2 else 1)]
    if group:
        selected = [(view.furnishings[0], None), (view.labels[0], None)] if case % 3 == 0 else [(host, None), (neighbor, 0)]
        if case % 5 == 0 and view.windows:
            selected = [(view.windows[0], None), (view.labels[0], None)]
    view.SetSelection(selected, notify = False)
    view.interactionBefore = view.CaptureState()
    view.dragStart, view.isDragging = point(400, 300), True
    view.dragVertices = (point(view.selectedWall.firstVertex), point(view.selectedWall.secondVertex))
    view.dragSource = view.selectedWall
    if group:
        view.StartGroupDrag()
    else:
        view.dragAttachments = view.AttachedVertices(host, captureAll = True)
    view.zoom, view.panOffset = .3, point(.37, .71)


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle('Fusion')
    LoadApplicationFonts(app)
    view = DrawingViewport()
    reference = ReferenceViewport(furnishingDefinitions = view.furnishingDefinitions)
    for viewport in (view, reference):
        viewport.resize(1000, 750)
        viewport.showMeasurements = viewport.showTips = False
    point, modifier = QtCore.QPointF, QtCore.Qt.KeyboardModifier
    frames = 0
    for group in (False, True):
        for case in range(32):
            for viewport in (view, reference):
                Setup(viewport, case, group)
            for frame, delta in enumerate((point(80, 40), point(-700, 0), point(1000, -200), point(150, 70), point(-30, 10))):
                for viewport in (view, reference):
                    if frame == 2:
                        viewport.connectedEnabled = not viewport.connectedEnabled
                    if frame == 3 and case % 16 == 1:
                        viewport.snapEnabled = True
                    viewport.UpdateInteraction(viewport.dragStart + delta, modifier.NoModifier)
                assert Snapshot(view) == Snapshot(reference), ('drag', group, case, frame)
                frames += 1
            if case % 8 == 1:
                images = []
                for viewport in (view, reference):
                    image = QtGui.QImage(viewport.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                    viewport.render(image)
                    images.append(image)
                assert images[0] == images[1], ('editor pixels', group, case)
    # Warm fits must follow changing values, parent assignments and membership,
    # while immutable captured maps can be reused by identity.
    for case in range(16):
        for viewport in (view, reference):
            Setup(viewport, case, False)
        for frame in range(7):
            results = []
            for viewport in (view, reference):
                if not viewport.windows:
                    viewport.windows = [models.Door(viewport.walls[0], .2, .4)]
                opening = viewport.windows[0]
                if frame == 1:
                    opening.parentWall = viewport.walls[1]
                elif frame == 2:
                    viewport.windows.append(models.Door(viewport.walls[3], .3, .5))
                elif frame == 3:
                    viewport.windows.reverse()
                elif frame == 4:
                    viewport.walls.reverse()
                    viewport.windows[0].length *= 1.2
                elif frame == 5:
                    viewport.walls.append(viewport.walls[-1])
                    viewport.windows.append(viewport.windows[-1])
                elif frame == 6:
                    viewport.windows = []
                results.append(viewport.FitWallOpenings(viewport.interactionBefore, validateScene = False))
            assert results[0] == results[1] and Snapshot(view) == Snapshot(reference), ('fitting', case, frame)
    # Mutable snapshot sequences must be read afresh, including mutable rows
    # inside a tuple. This is intentionally separate from normal captured tuples.
    for viewport in (view, reference):
        Setup(viewport, 1)
        captured = viewport.CaptureState()
        before = (tuple(list(row) for row in captured[0]), *captured[1:])
        viewport.FitWallOpenings(before, validateScene = False)
        before[0][0][1] += 100
        viewport.FitWallOpenings(before, validateScene = False)
    assert Snapshot(view) == Snapshot(reference), 'mutable snapshot rows'
    # Untracked geometry adapters cannot rely on a viewport topology revision.
    for viewport in (view, reference):
        Setup(viewport, 1)
        viewport.__dict__['walls'] = list(viewport.walls)
        viewport.__dict__['windows'] = list(viewport.windows)
        viewport.FitWallOpenings(viewport.interactionBefore, validateScene = False)
        viewport.windows.append(models.Door(viewport.walls[3], .3, .5))
        viewport.walls.reverse()
        viewport.FitWallOpenings(viewport.interactionBefore, validateScene = False)
    assert Snapshot(view) == Snapshot(reference), 'untracked scene lists'
    # Force rollback after the fit has changed geometry, and prove the wall
    # path no longer captures unused furnishing/label state per update.
    for viewport in (view, reference):
        Setup(viewport, 1)
        fit = viewport.FitWallOpenings
        def FailFit(*args, **kwargs):
            fit(*args, **kwargs)
            return False
        with patch.object(viewport, 'FitWallOpenings', side_effect = FailFit):
            viewport.UpdateInteraction(viewport.dragStart + point(200, 0), modifier.NoModifier)
    assert Snapshot(view) == Snapshot(reference), 'last-valid rollback'
    Setup(view, 1)
    with patch.object(view, 'CaptureState', side_effect = AssertionError('Wall preview captured unrelated state')):
        view.UpdateInteraction(view.dragStart + point(200, 0), modifier.NoModifier)
    Setup(view, 1)
    view.SetSelection([(view.furnishings[0], None), (view.labels[0], None)], notify = False)
    with patch.object(view, 'CaptureState', side_effect = AssertionError('Group setup captured unrelated state')):
        view.StartGroupDrag()
    view.windows = []
    with patch.object(view, 'OpeningsValid', return_value = False) as validate:
        assert not view.FitWallOpenings(validateScene = True)
        assert validate.call_count == 1
        assert view.FitWallOpenings(validateScene = False)
        assert validate.call_count == 1
    assert not any(name in view.__dict__ for name in ('openingFitGroups', 'openingFitBeforeWalls', 'openingFitBeforeCenters'))
    for viewport in (view, reference):
        viewport.close()
    print(f'PASS: {frames} frozen drag frames, host/parent/membership/order/duplicate changes, mutable baselines, rollback and exact editor pixels.')


if __name__ == '__main__':
    Main()
