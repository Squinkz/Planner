"""Real dorm geometry: barn jamb face contact and complex SVG stroke clipping."""
import json
import math
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtSvg
from fixtures.parity_examples import ExampleWindow
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan
from planner_app.graphics.palette import themeColors
from planner_app.models import BarnDoor, Wall


def Main():
    with ExampleWindow() as (main, folder):
        view = main.viewport
        data = json.loads((root / "checks/fixtures/dorm_opening_masks.json").read_text())
        main.ApplyProject(DecodeProject(data, view.furnishingDefinitions, validatePlacement = False), None)
        main.SetThemes(canvasTheme = "Light Canvas")
        view.showGrid = view.showMeasurements = view.showTips = False
        view.floors = True
        view.performanceTimer.stop()
        main.sessionTimer.stop()
        main.sessionPollTimer.stop()
        view.performanceLabel.hide()
        openings = list(view.windows)
        wallColor = QtGui.QColor(themeColors["wallOutline"])
        jambCases = 0
        for door in (obj for obj in openings if isinstance(obj, BarnDoor)):
            midpoint = (door.firstVertex + door.secondVertex) / 2
            run = door.secondVertex - door.firstVertex
            run /= math.hypot(run.x(), run.y())
            normal = QtCore.QPointF(-run.y(), run.x())
            along, across = QtCore.QPointF(run.x(), -run.y()), QtCore.QPointF(normal.x(), -normal.y())
            for zoom in (.5, 1, 2.3, 5):
                view.zoom = zoom
                for phase in (0, .31, .77):
                    view.panOffset += view.DrawingRect().center() - view.WorldToViewport(midpoint) + QtCore.QPointF(phase, .43)
                    view.windows = [obj for obj in openings if obj is not door]
                    baseline = view.grab().toImage()
                    view.windows = openings
                    image = view.grab().toImage()
                    center = view.WorldToViewport(midpoint)
                    half = door.width * view.basePixelsPerMillimeter * zoom / 2
                    for tangent in (-1, 0, 1):
                        for offset in range(-math.ceil(half) - 5, math.ceil(half) + 6):
                            # The panel intentionally occludes the wall on its
                            # own face. The rear jamb surface must remain whole.
                            if offset * (1 if not door.swingsOutwards else -1) >= half - 1:
                                continue
                            point = (center + along * tangent + across * offset).toPoint()
                            if baseline.pixelColor(point) == wallColor:
                                assert image.pixelColor(point).lightness() <= wallColor.lightness() + 25, (
                                    door.objectId, zoom, phase, point, image.pixelColor(point).name())
                    jambCases += 1
        data = main.BuildProjectData(includeHistory = False, includeActivity = False)
        bounds = (-3100, -7000, 12000, 10500)
        for scale in (60, 100, 200):
            raster = RenderPlan(folder / "masks.plan", scale, bounds, projectData = data, applyTheme = False, border = "None")
            floor = QtGui.QColor(themeColors["roomFill"]).rgba()
            wall = QtGui.QColor(themeColors["wallOutline"]).rgba()
            wallFill = QtGui.QColor(themeColors["wallFill"]).rgba()
            canvas = QtGui.QColor(themeColors["canvas"]).rgba()
            for preview in (False, True):
                svg = RenderPlan(folder / "masks.plan", scale, bounds, outputFormat = "svg", projectData = data,
                                 applyTheme = False, border = "None", preview = preview, previewScene = preview)
                vector = QtGui.QImage(raster.size(), QtGui.QImage.Format.Format_ARGB32)
                vector.fill(0)
                with QtGui.QPainter(vector) as painter:
                    QtSvg.QSvgRenderer(svg).render(painter)
                first, second = memoryview(raster.constBits()).cast("I"), memoryview(vector.constBits()).cast("I")
                filledRoom = sum(a == floor and b == wall for a, b in zip(first, second))
                assert filledRoom == 0, (scale, preview, filledRoom)
                erasedWall = sum(a == wallFill and b in (floor, canvas) for a, b in zip(first, second))
                if erasedWall:
                    raster.save(str(root / "diagnostics/dorm-mask-native.png"))
                    vector.save(str(root / "diagnostics/dorm-mask-vector.png"))
                    (root / "diagnostics/dorm-mask-failure.svg").write_bytes(bytes(svg))
                assert erasedWall == 0, ("missing wall fill", scale, preview, erasedWall)
        # Exercise the actual SVG viewport preview and its recoloring path.
        panel = main.exportPanel
        main.sidebarTabs.setCurrentWidget(panel)
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        panel.borderField.setCurrentText("None")
        panel.scaleField.setValue(100)
        view.exportOverlay.bounds = bounds
        panel.SetBounds(list(bounds))
        view.roomDetection.Check()
        region = max((region for region in view.roomDetection.regions if region["area"] > 1000000),
                     key = lambda region: (region["bounds"].center().x(), region["bounds"].center().y()))
        center = region["bounds"].center()
        for zoom in (.5, 1.5):
            view.zoom = zoom
            view.panOffset += view.DrawingRect().center() - view.WorldToViewport(center)
            image = view.grab().toImage()
            sample = view.WorldToViewport(center).toPoint()
            assert image.pixelColor(sample) == QtGui.QColor(themeColors["roomFill"]), (zoom, image.pixelColor(sample).name())
            assert not view.exportOverlay.previewError
            for spacer in (obj for obj in view.walls if type(obj) is Wall and obj.width >= 400):
                point = (spacer.firstVertex + spacer.secondVertex) / 2
                view.panOffset += view.DrawingRect().center() - view.WorldToViewport(point)
                image = view.grab().toImage()
                sample = view.WorldToViewport(point).toPoint()
                assert image.pixelColor(sample) == QtGui.QColor(themeColors["wallFill"]), (
                    "live SVG spacer fill", spacer.objectId, zoom, image.pixelColor(sample).name())
    print("PASS:", jambCases, "real dorm barn-jamb cases, complete SVG wall fills at three scales and live preview")


if __name__ == "__main__":
    Main()
