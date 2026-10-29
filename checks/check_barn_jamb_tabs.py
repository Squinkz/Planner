"""Both barn jambs have no wall-stroke tabs beyond the intended symbol ink."""
import json
import math
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow
from planner_app.project_codec import DecodeProject
from planner_app.models import BarnDoor
from planner_app.graphics.palette import themeColors
from planner_app.graphics.symbols import DrawOpeningSymbol
from planner_app.graphics.linework import LinePen
from planner_app.viewport.geometry import FootprintGeometry
from check_tinted_passage_outlines import AssertNoOutline


def Main():
    with ExampleWindow() as (main, folder):
        view = main.viewport
        data = json.loads((root / "checks/fixtures/dorm_opening_masks.json").read_text())
        main.ApplyProject(DecodeProject(data, view.furnishingDefinitions, validatePlacement = False), None)
        main.SetThemes(canvasTheme = "Light Canvas")
        view.showGrid = view.showMeasurements = view.showTips = False
        view.performanceTimer.stop()
        main.sessionTimer.stop()
        main.sessionPollTimer.stop()
        view.performanceLabel.hide()
        cases = 0
        for door in (obj for obj in view.windows if isinstance(obj, BarnDoor)):
            neighbors = [obj for obj in view.walls if obj is not door.parentWall]
            geometry = FootprintGeometry(view.basePixelsPerMillimeter, view)
            midpoint = (door.firstVertex + door.secondVertex) / 2
            openingEnd = door.secondVertex if door.hingeAtSecond else door.firstVertex
            for jamb in (midpoint, openingEnd):
                towardOpening = openingEnd - midpoint if jamb == midpoint else midpoint - openingEnd
                towardOpening /= math.hypot(towardOpening.x(), towardOpening.y())
                walk = QtCore.QPointF(towardOpening.x(), -towardOpening.y())
                for zoom in (.5, 1, 2.3, 5):
                    view.zoom = zoom
                    scale = view.basePixelsPerMillimeter * zoom
                    for phase in (.31, .77):
                        view.panOffset += view.DrawingRect().center() - view.WorldToViewport(jamb) + QtCore.QPointF(phase, .43)
                        for tinted in (False, True):
                            view.floors = tinted
                            actual = view.grab().toImage()
                            expected = QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32)
                            expected.fill(QtGui.QColor(themeColors["canvas"]))
                            first, second = view.WorldToViewport(door.firstVertex), view.WorldToViewport(door.secondVertex)
                            run = second - first
                            normal = QtCore.QPointF(-run.y(), run.x()) / math.hypot(run.x(), run.y())
                            with QtGui.QPainter(expected) as painter:
                                view.DrawGridBackground(painter, view.DrawingRect(), view.WorldToViewport(QtCore.QPointF()), scale)
                                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                                geometry.zoom = view.zoom
                                neighborPath = geometry.ConnectedWallPath(neighbors)
                                painter.fillPath(neighborPath, QtGui.QColor(themeColors["wallFill"]))
                                painter.setPen(LinePen(themeColors["wallOutline"], view.lineWidths["walls"]))
                                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                                painter.drawPath(neighborPath)
                                DrawOpeningSymbol(painter, first, second, door.width * scale, BarnDoor,
                                    door.hingeAtSecond, door.swingsOutwards, color = themeColors["objectOutline"],
                                    wallColor = themeColors["wallOutline"], pixelsPerMillimeter = scale,
                                    lineWidth = view.lineWidths["architectural"], wallLineWidth = view.lineWidths["walls"],
                                    drawPassageEdges = not tinted)
                            center = view.WorldToViewport(jamb)
                            for side in (-1, 1):
                                for depth in (.5, 1.25, 2):
                                    for across in (-2, -1, 0, 1, 2):
                                        point = (center + walk * (view.lineWidths["walls"] / 2 + depth)
                                                 + normal * (side * door.width * scale / 2 + across)).toPoint()
                                        difference = max(b - a for a, b in zip(actual.pixelColor(point).getRgb(), expected.pixelColor(point).getRgb()))
                                        assert difference <= 3, (door.objectId, jamb == midpoint, zoom, phase, tinted,
                                                                 point, actual.pixelColor(point).name(), expected.pixelColor(point).name())
                            cases += 1
        panel = main.exportPanel
        main.sidebarTabs.setCurrentWidget(panel)
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        panel.borderField.setCurrentText("None")
        panel.scaleField.setValue(100)
        view.exportOverlay.bounds = (-3100, -7000, 12000, 10500)
        panel.SetBounds(list(view.exportOverlay.bounds))
        # Enlarge the retained 100 px/m SVG fivefold. A subpixel source tab
        # becomes several visible pixels here, as in the reported screenshots.
        view.zoom = 2.5
        scale = view.basePixelsPerMillimeter * view.zoom
        factor = scale / .1
        fill, canvas = QtGui.QColor(themeColors["roomFill"]), QtGui.QColor(themeColors["canvas"])
        for style in ("Canvas", "Tinted"):
            panel.roomStyleField.setCurrentText(style)
            for door in (obj for obj in view.windows if isinstance(obj, BarnDoor)):
                midpoint = (door.firstVertex + door.secondVertex) / 2
                openingEnd = door.secondVertex if door.hingeAtSecond else door.firstVertex
                axis = openingEnd - midpoint
                axis /= math.hypot(axis.x(), axis.y())
                along = QtCore.QPointF(axis.x(), -axis.y())
                across = QtCore.QPointF(-along.y(), along.x())
                for jamb, walking in ((midpoint, along), (openingEnd, -along)):
                    view.panOffset += view.DrawingRect().center() - view.WorldToViewport(jamb)
                    image = view.grab().toImage()
                    center = view.WorldToViewport(jamb)
                    for side in (-1, 1):
                        for offset in (-.8, .8):
                            point = (center + walking * (view.lineWidths["walls"] * factor / 2 + 2)
                                     + across * (side * door.width * scale / 2 + offset * view.lineWidths["walls"] * factor / 2)).toPoint()
                            AssertNoOutline(image, point.x(), point.y(), 0, fill, canvas, ("SVG tab", style, door.objectId, jamb))
    print("PASS:", cases, "barn jamb tab cases across both ends, room styles, zooms and camera phases")


if __name__ == "__main__":
    Main()
