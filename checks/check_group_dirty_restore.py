"""Exact frozen group frames with dirty restoration and mutable baselines."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.viewport.widget import DrawingViewport
from planner_app.models import Wall, Furnishing, Label
from fixtures.group_restore_reference_20261031 import ReferenceViewport
from check_drag_fitting_preparation import Setup, Snapshot
from planner_app.graphics.fonts import LoadApplicationFonts


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    LoadApplicationFonts(app)
    point, modifiers = QtCore.QPointF, QtCore.Qt.KeyboardModifier
    view = DrawingViewport()
    reference = ReferenceViewport(furnishingDefinitions = view.furnishingDefinitions)
    frames = 0
    for case in range(32):
        for viewport in (view, reference):
            viewport.CancelInteraction()
            viewport.resize(1000, 750)
            viewport.showMeasurements = viewport.showTips = False
            Setup(viewport, case, True)
        for frame in range(8):
            modifier = modifiers.ShiftModifier if frame in (2, 3) and case % 2 else modifiers.NoModifier
            for viewport in (view, reference):
                if frame == 1:
                    # Unselected edits still restore exactly as the full walk.
                    viewport.walls[-1].secondVertex += point(.13, .71)
                    viewport.furnishings[-1].flipHorizontal = not viewport.furnishings[-1].flipHorizontal
                    viewport.labels[-1].text = "external edit"
                if frame == 4:
                    viewport.connectedEnabled = not viewport.connectedEnabled
                if frame == 5:
                    viewport.interactionBefore[5][-1][1].setX(17.25)
                    viewport.interactionBefore[8][-1][2].setY(-.0)
                if frame == 6 and case % 2:
                    captured = viewport.interactionBefore
                    viewport.interactionBefore = (tuple(list(row) for row in captured[0]), *captured[1:])
                viewport.UpdateInteraction(viewport.dragStart + point(70 + frame * 23, 20 - frame * 3), modifier)
            assert Snapshot(view) == Snapshot(reference), (case, frame)
            frames += 1
        if case % 8 == 1:
            images = []
            for viewport in (view, reference):
                image = QtGui.QImage(viewport.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                viewport.render(image)
                images.append(image)
            assert images[0] == images[1], (case, "pixels")
    for viewport in (view, reference):
        viewport.CancelInteraction()
    assert Snapshot(view) == Snapshot(reference), "cancelled state"
    assert view.renderChanges.dirtyObjects is None and "groupRestoreCache" not in view.__dict__
    # Warm tiny groups must not visit all furnishing/label restoration rows.
    view.snapEnabled = view.connectedEnabled = False
    view.walls = [Wall(point(index * 6000, 0), point(index * 6000 + 4000, 0), 200) for index in range(256)]
    view.furnishings = [Furnishing(view.furnishingDefinitions["desk"], point(index * 6000, 10000)) for index in range(256)]
    view.labels = [Label(point(index * 6000, 15000), "Label") for index in range(256)]
    view.SetSelection([(view.furnishings[0], None), (view.labels[0], None)], notify = False)
    view.interactionBefore = view.CaptureState()
    view.dragStart, view.isDragging = point(400, 300), True
    view.StartGroupDrag()
    view.UpdateGroupDrag(point(450, 330), modifiers.NoModifier)
    with patch.object(view, "RestoreFurnishingStates", wraps = view.RestoreFurnishingStates) as furnishings, \
            patch.object(view, "RestoreLabelStates", wraps = view.RestoreLabelStates) as labels:
        view.UpdateGroupDrag(point(460, 340), modifiers.NoModifier)
        assert len(furnishings.call_args.args[0]) == len(labels.call_args.args[0]) == 1
    view.CancelInteraction()
    assert view.renderChanges.dirtyObjects is None and "groupRestoreCache" not in view.__dict__
    for viewport in (view, reference):
        viewport.close()
        viewport.deleteLater()
    print(f"PASS: {frames} frozen group frames, external/mutable edits, copy/connection changes, exact pixels, affected-row counts and cancellation cleanup.")


if __name__ == "__main__":
    Main()
