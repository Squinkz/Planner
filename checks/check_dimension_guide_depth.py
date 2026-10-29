"""Signed guide depth: editing, history/transport, witness lines, bounds and exports."""
import copy
import math
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import MeasurementGuide, BoundaryLine, Arrow
from planner_app.geometry.measurements import GuideDepthOffset
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan
from planner_app.export_bounds import AutomaticBounds
from planner_app.graphics.palette import themeColors
from check_pan_dpi import CompareDirect


def Main():
    assert GuideDepthOffset((0, 0), (1000, 0), 300) == (0, -300)
    for first, second in (((0, 0), (1000, 0)), ((0, 0), (0, 1000)), ((0, 0), (700, -400))):
        offset = GuideDepthOffset(first, second, 300)
        reverse = GuideDepthOffset(second, first, 300)
        negative = GuideDepthOffset(first, second, -300)
        assert all(math.isclose(a, b, abs_tol = 1e-9) for a, b in zip(offset, reverse))
        assert all(math.isclose(a, -b, abs_tol = 1e-9) for a, b in zip(offset, negative))
        assert math.isclose(math.hypot(*offset), 300)
    with ExampleWindow() as (main, folder):
        view = main.viewport
        view.performanceTimer.stop()
        main.sessionTimer.stop()
        main.sessionPollTimer.stop()
        view.unitsMode = "Meters"
        view.showGrid = view.showTips = view.showMeasurements = view.floors = False
        point = QtCore.QPointF
        guide = MeasurementGuide(point(-1000, 0), point(1000, 0))
        InstallScene(main, [guide])
        view.SetSelection([(guide, None)])
        field = main.arrowFields["depth"]
        assert guide.depth == field.value() == 0 and field.isVisible()
        main.EditArrowProperty("depth", .3)
        assert guide.depth == 300
        view.Undo()
        assert guide.depth == 0
        view.Redo()
        assert guide.depth == 300
        before = guide.depth
        main.EditArrowProperty("depth", float("inf"))
        assert guide.depth == before
        for units, displayed in (("Millimeters", 300), ("Inches", 300 / 25.4), ("Feet and Inches", 300 / 304.8), ("Meters", .3)):
            view.unitsMode = units
            main.RefreshProperties()
            assert math.isclose(field.value(), displayed, abs_tol = .001), (units, field.value())
            assert field.minimum() < 0 and field.maximum() > 0
        other = MeasurementGuide(point(-1000, 1000), point(1000, 1000), depth = -400)
        view.walls.append(other)
        view.SetSelection([(guide, None), (other, None)])
        assert field.mixedValue
        main.EditArrowProperty("depth", .25)
        assert guide.depth == other.depth == 250
        view.Undo()
        assert (guide.depth, other.depth) == (300, -400)
        for obj in (BoundaryLine(point(), point(1000, 0)), Arrow(point(), point(1000, 0))):
            view.walls.append(obj)
            view.SetSelection([(obj, None)])
            assert field.isHidden(), type(obj)
        InstallScene(main, [guide])
        view.SetSelection([(guide, None)])
        assert view.CloneLinearObject(guide).depth == 300
        assert view.CopySelection() and view.PasteSelection(inPlace = True)
        assert len(view.walls) == 2 and all(obj.depth == 300 for obj in view.walls)
        view.Undo()
        assert len(view.walls) == 1
        # Save/load a depth edit and its sparse history, not just the live model.
        InstallScene(main, [guide])
        guide.depth = 0
        view.SetSelection([(guide, None)])
        main.EditArrowProperty("depth", -.4)
        data = main.BuildProjectData()
        record = next(record for record in data["scene"]["objects"] if record["type"] == "MeasurementGuide")
        assert record["depth"] == -400
        main.ApplyProject(DecodeProject(data, view.furnishingDefinitions), None)
        guide = view.walls[0]
        assert guide.depth == -400
        view.Undo()
        assert guide.depth == 0
        view.Redo()
        assert guide.depth == -400
        legacy = copy.deepcopy(data)
        legacy.pop("history", None)
        legacy["scene"]["objects"][0].pop("depth")
        assert DecodeProject(legacy, view.furnishingDefinitions)[0][0].depth == 0
        for invalid in (True, float("nan"), float("inf"), 1e10, "bad"):
            malformed = copy.deepcopy(legacy)
            malformed["scene"]["objects"][0]["depth"] = invalid
            try:
                DecodeProject(malformed, view.furnishingDefinitions)
            except ValueError:
                pass
            else:
                raise AssertionError(invalid)
        view.zoom = 1
        view.panOffset = point()
        view.SetSelection([])
        view.performanceLabel.hide()
        canvas = QtGui.QColor(themeColors["canvas"])
        images = []
        for depth in (0, 300, -300, 0):
            guide.depth = depth
            image = view.grab().toImage()
            images.append(image)
            below = view.WorldToViewport(guide.firstVertex + point(0, -150)).toPoint()
            above = view.WorldToViewport(guide.firstVertex + point(0, 150)).toPoint()
            assert (image.pixelColor(below) != canvas) == (depth > 0), depth
            assert (image.pixelColor(above) != canvas) == (depth < 0), depth
            if depth:
                world = guide.firstVertex + point(0, -depth / 2)
                assert view.HitTest(view.WorldToViewport(world))[0] is guide
                assert view.ObjectFootprint(guide)[0].contains(world)
        assert images[0] == images[-1], "Returning to zero changed legacy pixels"
        guide.depth = 3000
        assert AutomaticBounds(view)[1] <= -4000
        view.panOffset = point(0, -700)
        image = QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32)
        image.fill(canvas)
        with QtGui.QPainter(image) as painter:
            painter.setClipRect(view.DrawingRect())
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            view.DrawScene(painter, view.DrawingRect(), view.WorldToViewport(point()), view.basePixelsPerMillimeter * view.zoom)
        sample = view.WorldToViewport(guide.firstVertex + point(0, -2250)).toPoint()
        assert view.DrawingRect().contains(sample) and image.pixelColor(sample) != canvas, "Offscreen baseline culled visible extensions"
        view.panOffset = point()
        guide.depth = 300
        view.isPanning = True
        for delta in (point(3, 1), point(.31, .43)):
            view.panOffset += delta
            CompareDirect(view)
        view.isPanning = False
        for depth in (0, 300, -300):
            guide.depth = depth
            data = main.BuildProjectData(includeHistory = False, includeActivity = False)
            for kind in ("png", "svg"):
                result = RenderPlan(folder / "depth.plan", 200, (-2000, -2000, 4000, 4000), projectData = data,
                                    outputFormat = kind, border = "None", applyTheme = False)
                if kind == "svg":
                    image = QtGui.QImage(800, 800, QtGui.QImage.Format.Format_ARGB32)
                    image.fill(0)
                    with QtGui.QPainter(image) as painter:
                        QtSvg.QSvgRenderer(result).render(painter)
                else:
                    image = result
                assert (image.pixelColor(200, 430) != canvas) == (depth > 0), (kind, depth)
                assert (image.pixelColor(200, 370) != canvas) == (depth < 0), (kind, depth)
        QtWidgets.QApplication.clipboard().clear()
    print("PASS: signed depth UI, units/mixed selection, history, clone/paste, legacy validation, hit/bounds, pan and PNG/SVG")


if __name__ == "__main__":
    Main()
