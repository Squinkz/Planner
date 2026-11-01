"""Print viewport/page rulers shift the export origin without moving paper or crop."""
import copy
import math
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_history import Drag
from planner_app.models import Wall
from planner_app.export_plan import RenderPlan
from planner_app.project_codec import DecodeProject


def Main():
    with ExampleWindow() as (main, folder):
        panel, view = main.exportPanel, main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), 200)])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetScaleOption("dpi", 96)
        panel.SetScaleOption("pageOrigin", [-3000, -4000])
        overlay = view.exportOverlay
        width, height = panel.PrintLayout()["paperTile"]
        overlay.bounds = (-3000, -4000, width * 2, height * 2)
        panel.SetBounds(overlay.bounds)
        bounds, origin = tuple(overlay.bounds), tuple(overlay.pageOrigin)
        scene = copy.deepcopy(main.BuildProjectData()["scene"])
        count = 0
        for kind in ("PNG", "SVG"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
            for titlePosition in ("Right", "Bottom"):
                panel.SetTitleBlockOption("enabled", True)
                panel.SetTitleBlockOption("position", titlePosition)
                for style in ("Ruler", "Marked", "Ruler + Reference Zones"):
                    panel.SetBorder(style)
                    layout = panel.PrintLayout()
                    page = (*origin, width, height)
                    # One design pixel per viewport pixel makes each ruler
                    # distinct from nearby crop/page boundary hit targets.
                    view.zoom = overlay.scale / (1000 * view.basePixelsPerMillimeter)
                    target = overlay.PrintPageRect(page)
                    factor = target.width() / layout["baselinePixels"][0]
                    border = overlay.borderSize * factor
                    ruler = (overlay.borderSize // 2 if style == "Ruler + Reference Zones" else overlay.borderSize) * factor
                    plot = QtCore.QRectF(target.topLeft() + QtCore.QPointF(border, border),
                                        QtCore.QSizeF(*(value * factor for value in layout["drawingPixels"])))
                    positions = ((QtCore.QPointF(view.DrawingRect().center().x(), view.rulerSize / 2), 0, False),
                                 (QtCore.QPointF(view.rulerSize / 2, view.DrawingRect().center().y()), 1, False),
                                 (QtCore.QPointF(plot.center().x(), plot.top() - ruler / 2), 0, True),
                                 (QtCore.QPointF(plot.center().x(), plot.bottom() + ruler / 2), 0, True),
                                 (QtCore.QPointF(plot.left() - ruler / 2, plot.center().y()), 1, True),
                                 (QtCore.QPointF(plot.right() + ruler / 2, plot.center().y()), 1, True))
                    # Convert page points to world coordinates before camera moves.
                    positions = [(view.ViewportToWorld(position) if onPage else position, axis, onPage)
                                 for position, axis, onPage in positions]
                    for position, axis, onPage in positions:
                        if onPage:
                            view.panOffset += view.DrawingRect().center() - view.WorldToViewport(position)
                            position = view.WorldToViewport(position)
                        panel.SetOverride("gridOrigin", [337.25, -123.75])
                        panel.ResetExportHistory()
                        assert overlay.HitRuler(position) == axis, (kind, titlePosition, style, position, axis)
                        before = view.gridOrigin
                        delta = QtCore.QPoint(31, 0) if axis == 0 else QtCore.QPoint(0, -29)
                        modifiers = QtCore.Qt.KeyboardModifier.AltModifier if onPage else QtCore.Qt.KeyboardModifier.NoModifier
                        start = position.toPoint()
                        Drag(view, start, start + delta, modifiers)
                        panel.EndExportGesture()
                        expected = before[axis] + (31 if axis == 0 else 29) / (view.basePixelsPerMillimeter * view.zoom)
                        if not onPage:
                            step = view.GridSteps(overlay.scale / 1000)[1]
                            expected = math.copysign(math.floor(abs(expected) / step + .5) * step, expected)
                        assert abs(view.gridOrigin[axis] - expected) < 1e-6
                        assert view.gridOrigin[axis ^ 1] == before[axis ^ 1]
                        assert tuple(overlay.bounds) == bounds and tuple(overlay.pageOrigin) == origin
                        assert len(panel.exportUndoHistory) == 1
                        view.Undo()
                        assert view.gridOrigin == before
                        view.Redo()
                        shifted = view.gridOrigin
                        camera = view.zoom, QtCore.QPointF(view.panOffset)
                        QtTest.QTest.mouseDClick(view, QtCore.Qt.MouseButton.LeftButton, pos = start)
                        QtTest.QTest.mouseMove(view, start + QtCore.QPoint(15, 15))
                        QtTest.QTest.mouseRelease(view, QtCore.Qt.MouseButton.LeftButton, pos = start)
                        panel.EndExportGesture()
                        assert view.gridOrigin[axis] == 0 and view.gridOrigin[axis ^ 1] == shifted[axis ^ 1]
                        assert overlay.dragRuler is None and overlay.dragPage is None
                        assert (view.zoom, view.panOffset) == camera
                        assert tuple(overlay.bounds) == bounds and tuple(overlay.pageOrigin) == origin
                        view.Undo()
                        assert view.gridOrigin == shifted
                        view.Redo()
                        assert view.gridOrigin[axis] == 0
                        count += 1
        assert main.BuildProjectData()["scene"] == scene
        for kind in ("png", "svg"):
            panel.SetOverride("gridOrigin", [0, 0])
            baseline = RenderPlan(**panel.ExportJobs(folder / ("origin." + kind), kind)[0][1])
            panel.SetOverride("gridOrigin", [1250, -750])
            shifted = RenderPlan(**panel.ExportJobs(folder / ("origin." + kind), kind)[0][1])
            assert baseline != shifted, (kind, "Export ignored the shifted ruler origin")
            view.grab()
            assert not overlay.previewError, overlay.previewError
        panel.SetOverride("gridOrigin", [1250, -750])
        saved = main.BuildProjectData(includeHistory = False)
        assert saved["settings"]["exportSettings"]["gridOrigin"] == [1250, -750]
        main.ApplyProject(DecodeProject(saved, view.furnishingDefinitions), None)
        assert view.gridOrigin == (0, 0)
        main.sidebarTabs.setCurrentWidget(panel)
        assert view.gridOrigin == (1250, -750)
        assert overlay.pageOrigin == origin and overlay.bounds == bounds
    print("PASS:", count, "Print ruler drag/reset cases across axes, page sides, border styles, title positions and PNG/SVG; snapping, history and persistence")


if __name__ == "__main__":
    Main()
