"""Page boundaries snap to the shifted export grid, including interior boundaries."""
import math
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow
from check_history import Drag
from planner_app.print_layout import SelectedPrintPages


def Main():
    with ExampleWindow() as (main, folder):
        panel, view = main.exportPanel, main.viewport
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetScaleOption("dpi", 96)
        overlay = view.exportOverlay
        panel.SetOverride("gridOrigin", [337.25, -123.75])
        cases = 0
        for kind in ("PNG", "SVG"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
            for axis in (0, 1):
                for snap in (False, True):
                    for alt in (False, True):
                        panel.SetScaleOption("pageOrigin", [123.4, -456.7])
                        width, height = panel.PrintLayout()["paperTile"]
                        beforeOrigin = tuple(overlay.pageOrigin)
                        overlay.bounds = (beforeOrigin[0] - width / 4, beforeOrigin[1] - height / 4, width * 2.5, height * 2.5)
                        panel.SetBounds(overlay.bounds)
                        beforeBounds = tuple(overlay.bounds)
                        view.zoom = .65 * min(view.DrawingRect().width() / width, view.DrawingRect().height() / height) / view.basePixelsPerMillimeter
                        boundary = beforeOrigin[axis] + (width if axis == 0 else height)
                        point = QtCore.QPointF(beforeOrigin[0] + width, beforeOrigin[1] + height * .4) if axis == 0 else QtCore.QPointF(beforeOrigin[0] + width * .4, beforeOrigin[1] + height)
                        view.panOffset += view.DrawingRect().center() - view.WorldToViewport(point)
                        start = view.WorldToViewport(point).toPoint()
                        assert overlay.HitPrintGuide(QtCore.QPointF(start)) == axis
                        view.snapEnabled = snap
                        modifiers = QtCore.Qt.KeyboardModifier.AltModifier if alt else QtCore.Qt.KeyboardModifier.NoModifier
                        delta = QtCore.QPoint(37, 0) if axis == 0 else QtCore.QPoint(0, -29)
                        distance = (37 if axis == 0 else 29) / (view.basePixelsPerMillimeter * view.zoom)
                        expected = boundary + distance
                        if snap != alt:
                            step = view.GridSteps(overlay.scale / 1000)[1]
                            relative = expected - view.gridOrigin[axis]
                            expected = view.gridOrigin[axis] + math.copysign(math.floor(abs(relative) / step + .5) * step, relative)
                        panel.ResetExportHistory()
                        Drag(view, start, start + delta, modifiers)
                        panel.EndExportGesture()
                        actual = overlay.pageOrigin[axis] + (width if axis == 0 else height)
                        assert abs(actual - expected) < 1e-6, (kind, axis, snap, alt, actual, expected)
                        displacement = overlay.pageOrigin[axis] - beforeOrigin[axis]
                        assert abs(overlay.bounds[axis] - beforeBounds[axis] - displacement) < 1e-6
                        assert overlay.bounds[2:] == beforeBounds[2:] and view.gridOrigin == (337.25, -123.75)
                        assert len(SelectedPrintPages(overlay.bounds, (width, height), overlay.pageOrigin)) == 4
                        assert len(panel.exportUndoHistory) == 1
                        after = tuple(overlay.pageOrigin), tuple(overlay.bounds)
                        view.Undo()
                        assert overlay.pageOrigin == beforeOrigin and overlay.bounds == beforeBounds
                        view.Redo()
                        assert (overlay.pageOrigin, overlay.bounds) == after
                        cases += 1
        # Modifier changes while the pointer is held re-evaluate the same raw
        # position immediately, matching crop/ruler drag interaction.
        view.snapEnabled = True
        point = QtCore.QPointF(overlay.pageOrigin[0] + width, overlay.pageOrigin[1] + height * .4)
        view.panOffset += view.DrawingRect().center() - view.WorldToViewport(point)
        start = view.WorldToViewport(point).toPoint()
        QtTest.QTest.mousePress(view, QtCore.Qt.MouseButton.LeftButton, pos = start)
        end = start + QtCore.QPoint(31, 0)
        move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(end), QtCore.QPointF(view.mapToGlobal(end)),
                                QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(view, move)
        snapped = tuple(overlay.pageOrigin)
        QtTest.QTest.keyPress(view, QtCore.Qt.Key.Key_Alt)
        assert overlay.pageOrigin != snapped
        QtTest.QTest.keyRelease(view, QtCore.Qt.Key.Key_Alt)
        assert overlay.pageOrigin == snapped
        QtTest.QTest.mouseRelease(view, QtCore.Qt.MouseButton.LeftButton, pos = end)
    print("PASS:", cases, "page-boundary grid snaps across axes, PNG/SVG, shifted origins, snap/Alt policies, interior boundaries, crop following and history")


if __name__ == "__main__":
    Main()
