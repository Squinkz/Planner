"""Angled-room wall cuts cannot occlude interior objects as the camera changes."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import (Wall, Stair, Counter, Railing, Furnishing, Door, SwingingDoor, DoubleDoor,
    SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway, Fireplace)
from planner_app.graphics.palette import themeColors
from planner_app.graphics.symbols import WallOpeningPolygons
from planner_app.export_plan import RenderPlan
from planner_app.viewport.rendering import RenderingMixin
from unittest.mock import patch


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        themeColors.update(canvas = "#ffffff", roomFill = "#eeeeee", wallFill = "#cccccc",
                           wallOutline = "#000000", objectOutline = "#000000")
        v.showGrid = v.showMeasurements = v.showTips = False
        v.lineWidths.update(walls = 4, architectural = 1)
        points = [p(-2200, -2200), p(3000, -1850), p(2100, 2700), p(-2000, 3100)]
        walls = [Wall(first, second, 300) for first, second in zip(points, points[1:] + points[:1])]
        stairs = [Stair(p(-900, 800), p(1300, 700), 700), Stair(p(1300, 700), p(1250, -800), 700)]
        center = p(0, 400)
        samples = [p(x, y) for x in (-1000, 0, 1000) for y in (-1000, 0, 1000)]
        door = SwingingDoor(walls[2], .2, .6)
        fireplace = Fireplace(walls[0], .55, .85)
        InstallScene(main, walls + stairs + [door, fireplace])
        oldFailures = 0
        for index in range(20, 101):
            v.zoom = index / 100
            v.panOffset = p(-center.x(), center.y()) * v.basePixelsPerMillimeter * v.zoom
            v.grab()
            origin = v.WorldToViewport(p())
            assert all(v.stairWallClip.contains(v.WorldToViewport(sample)) for sample in samples), index
            # Document a real regression: exactly tangent cuts can flip Qt's
            # subtraction topology. The new clip must remain correct there.
            wallPath = QtGui.QTransform().scale(v.zoom, v.zoom).map(v.wallGeometryPath)
            stroke = QtGui.QPainterPathStroker()
            stroke.setWidth(4)
            stroke.setJoinStyle(QtCore.Qt.PenJoinStyle.BevelJoin)
            stroke.setCapStyle(QtCore.Qt.PenCapStyle.SquareCap)
            openings = QtGui.QPainterPath()
            openings.setFillRule(QtCore.Qt.FillRule.WindingFill)
            for opening in (door, fireplace):
                for polygon in WallOpeningPolygons(opening, v.WorldToViewport(opening.firstVertex) - origin,
                    v.WorldToViewport(opening.secondVertex) - origin, v.basePixelsPerMillimeter * v.zoom, 4):
                    openings.addPolygon(polygon)
                    openings.closeSubpath()
            old = wallPath.united(stroke.createStroke(wallPath)).subtracted(openings)
            oldFailures += old.contains(v.WorldToViewport(center) - origin)
        assert oldFailures, "Fixture must exercise the original tangent-cut failure"
        # Every opening cut variant, including the narrow pocket half, shares
        # the same semantics. Camera translation must reuse the cached mask.
        for kind in (Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway, Fireplace):
            opening = kind(walls[2], .2, .6)
            InstallScene(main, walls + stairs + [opening, fireplace])
            for zoom in (.22, .3, .42, .47, .62, .88, 1.3):
                v.zoom = zoom
                v.grab()
                occlusion = v.stairWallOcclusion
                for pan in (p(0, 0), p(13.25, -7.75)):
                    v.panOffset = pan
                    v.grab()
                    assert v.stairWallOcclusion is occlusion
                    assert all(v.stairWallClip.contains(v.WorldToViewport(sample)) for sample in samples), (kind, zoom, pan)
        # Check the other object layers rather than assuming the bug is shared.
        for kind in (Stair, Counter, Railing, Furnishing):
            objects = ([Furnishing(v.furnishingDefinitions["desk"], center)] if kind is Furnishing else
                       [kind(p(-900, 800), p(1300, 700), 700), kind(p(1300, 700), p(1250, -800), 700)])
            InstallScene(main, walls + objects + [door, fireplace])
            for floors in (False, True):
                v.floors = floors
                for zoom in (.22, .3, .42, .47, .62, .88):
                    v.zoom = zoom
                    v.panOffset = p(-center.x(), center.y()) * v.basePixelsPerMillimeter * zoom
                    image = v.grab().toImage()
                    region = QtCore.QRectF(v.WorldToViewport(p(-1300, 1400)), v.WorldToViewport(p(1800, -1400))).normalized().toAlignedRect().intersected(image.rect())
                    crop = image.copy(region).convertToFormat(QtGui.QImage.Format.Format_RGB32)
                    ink = sum(value < 80 for value in bytes(crop.constBits())[0::4])
                    assert ink > 20, (kind, floors, zoom, ink)
        # File renders use the same stable clip; assert interior visibility in
        # both raster and vector paths at scales that previously failed.
        InstallScene(main, walls + stairs + [door, fireplace])
        data = main.BuildProjectData()
        draw = RenderingMixin.DrawScene
        exported = []

        def CheckExport(viewport, *args, **kwargs):
            result = draw(viewport, *args, **kwargs)
            assert all(viewport.stairWallClip.contains(viewport.WorldToViewport(sample)) for sample in samples)
            exported.append(True)
            return result

        with patch.object(RenderingMixin, "DrawScene", CheckExport):
            for outputFormat in ("png", "svg"):
                assert RenderPlan(folder / "angled.plan", 180, [-3000, -3000, 7000, 7000],
                                  projectData = data, outputFormat = outputFormat, applyTheme = False)
        assert len(exported) == 2
    print("PASS: angled room cuts, zoom/pan stability, all opening variants, stairs/counters/railings/furnishings, floors and PNG/SVG")


if __name__ == "__main__":
    Main()
