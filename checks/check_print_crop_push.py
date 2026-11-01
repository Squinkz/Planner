"""Crop handles push the last complete sheet, then detach on outward drag."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow
from planner_app.print_layout import SelectedPrintPages


def Main():
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        overlay = v.exportOverlay
        for position in ("Right", "Bottom"):
            panel.SetOverride("titleBlock", dict(enabled = True, position = position))
            for edge in range(4):
                axis, inward = edge // 2, 1 if edge % 2 == 0 else -1
                panel.SetScaleOption("pageOrigin", [123, -456])
                width, height = panel.PrintLayout()["paperTile"]
                v.snapEnabled = False
                v.gridOrigin = (321, -789)
                original = (123, -456, width, height)
                overlay.bounds = original
                panel.SetBounds(original)
                panel.ResetExportHistory()
                panel.BeginExportGesture()
                overlay.dragEdge = edge
                boundary = original[axis] + (original[axis + 2] if edge % 2 else 0)
                delta = inward * 1379.25
                overlay.MoveEdge(edge, boundary + delta)
                pushed = list(original)
                pushed[axis] += delta
                assert all(abs(a - b) < 1e-6 for a, b in zip(overlay.bounds, pushed)), (edge, overlay.bounds, pushed)
                origin = list(original[:2])
                origin[axis] += delta
                assert overlay.pageOrigin == tuple(origin)
                # Release at the same pointer cannot add a second displacement.
                overlay.MoveEdge(edge, boundary + delta)
                assert overlay.pageOrigin == tuple(origin)
                # Reverse a little: expand the crop, leaving pages where pushed.
                outward = boundary + delta - inward * 431.75
                overlay.MoveEdge(edge, outward)
                assert overlay.pageOrigin == tuple(origin)
                bounds = overlay.bounds
                actual = bounds[axis] + (bounds[axis + 2] if edge % 2 else 0)
                assert abs(actual - outward) < 1e-6
                assert abs(bounds[axis + 2] - original[axis + 2] - 431.75) < 1e-6
                assert len(SelectedPrintPages(bounds, (width, height), overlay.pageOrigin)) == 1
                assert v.gridOrigin == (321, -789)
                overlay.dragEdge = None
                panel.EndExportGesture()
                assert len(panel.exportUndoHistory) == 1
                final = (overlay.bounds, overlay.pageOrigin)
                panel.UndoExport()
                assert overlay.bounds == original and overlay.pageOrigin == original[:2]
                panel.RedoExport()
                assert (overlay.bounds, overlay.pageOrigin) == final
                # A single jump past the opposite crop edge still follows the
                # pointer in full, rather than stopping at the positive-size clamp.
                panel.UndoExport()
                overlay.dragEdge = edge
                overlay.MoveEdge(edge, boundary + inward * original[axis + 2] * 2.5)
                actual = overlay.bounds[axis] + (overlay.bounds[axis + 2] if edge % 2 else 0)
                assert abs(actual - boundary - inward * original[axis + 2] * 2.5) < 1e-5
                assert len(SelectedPrintPages(overlay.bounds, (width, height), overlay.pageOrigin)) == 1
                overlay.dragEdge = None
        # Partial margins and multiple columns shrink normally until only the
        # final complete column remains, then translate without losing margins.
        panel.SetScaleOption("pageOrigin", [0, 0])
        width, height = panel.PrintLayout()["paperTile"]
        v.snapEnabled = False
        overlay.bounds = (-width / 4, -height / 5, width * 2.75, height * 1.7)
        panel.SetBounds(overlay.bounds)
        overlay.dragEdge = 0
        overlay.MoveEdge(0, width * .7)
        assert overlay.pageOrigin == (0, 0) and abs(overlay.bounds[0] - width * .7) < 1e-6
        overlay.MoveEdge(0, width * 1.2)
        assert abs(overlay.pageOrigin[0] - width * .2) < 1e-6
        assert abs(overlay.bounds[0] - width * 1.2) < 1e-6 and abs(overlay.bounds[2] - width * 1.5) < 1e-6
        assert len(SelectedPrintPages(overlay.bounds, (width, height), overlay.pageOrigin)) == 1
        overlay.dragEdge = None
        # Real mouse interaction must prefer the coincident crop handle, retain
        # one gesture, and resume resizing before the mouse is released.
        panel.SetScaleOption("pageOrigin", [0, 0])
        width, height = panel.PrintLayout()["paperTile"]
        overlay.bounds = (0, 0, width, height)
        panel.SetBounds(overlay.bounds)
        v.snapEnabled = False
        v.zoom = .65 * min(v.DrawingRect().width() / width, v.DrawingRect().height() / height) / v.basePixelsPerMillimeter
        v.panOffset += v.DrawingRect().center() - v.WorldToViewport(QtCore.QPointF(width / 2, height / 2))
        panel.ResetExportHistory()
        start = v.WorldToViewport(QtCore.QPointF(0, height / 2)).toPoint()
        assert overlay.HitEdge(QtCore.QPointF(start)) == 0 and overlay.HitPrintGuide(QtCore.QPointF(start)) is None
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = start)
        QtTest.QTest.mouseMove(v, start + QtCore.QPoint(45, 0))
        pushedOrigin = overlay.pageOrigin
        assert pushedOrigin[0] > 0
        QtTest.QTest.mouseMove(v, start + QtCore.QPoint(15, 0))
        assert overlay.pageOrigin == pushedOrigin and overlay.bounds[2] > width
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = start + QtCore.QPoint(15, 0))
        QtWidgets.QApplication.processEvents()
        assert overlay.dragEdge is None and len(panel.exportUndoHistory) == 1
        # The pushing phase uses the same shifted grid as page/crop guides.
        panel.SetScaleOption("pageOrigin", [123, -456])
        overlay.bounds = (123, -456, width, height)
        panel.SetBounds(overlay.bounds)
        v.snapEnabled = True
        overlay.dragEdge = 0
        step = v.GridSteps(overlay.scale / 1000)[1]
        target = v.gridOrigin[0] + step * 2
        overlay.MoveEdge(0, target + step * .1)
        assert abs(overlay.pageOrigin[0] - target) < 1e-6
        overlay.MoveEdge(0, target)
        assert abs(overlay.bounds[0] - target) < 1e-6 and abs(overlay.bounds[2] - width) < 1e-6
        overlay.dragEdge = None
    print("All crop edges push/detach at page minimum, with pointer continuity and one undo gesture")


if __name__ == "__main__":
    Main()
