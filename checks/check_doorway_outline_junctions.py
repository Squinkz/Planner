"""Doorway cuts must not notch adjoining wall outlines beyond jamb caps."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, OpenDoorway, Door
from planner_app.export_plan import RenderPlan


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        main.SetThemes(canvasTheme = "Light Canvas")
        v.showGrid = v.showMeasurements = v.showTips = v.floors = False
        main.SetLinework(v.lineworkSettings | {"baseWidth": 4, "walls": 2, "architectural": .5})
        point = QtCore.QPointF
        for angle in (0, 90, 37):
            transform = QtGui.QTransform().rotate(angle)
            wall = Wall(transform.map(point(-1000, 0)), transform.map(point(1000, 0)), 200)
            side = Wall(transform.map(point(-500, 0)), transform.map(point(-500, 1000)), 200)
            for zoom in (5, 10):
                v.zoom = zoom
                scale = v.basePixelsPerMillimeter * zoom
                sample = transform.map(point(-400 + 1 / scale, 100 + 6 / scale))
                pixel = (v.WorldToViewport(sample) * v.devicePixelRatioF()).toPoint()
                InstallScene(main, [wall, side])
                expected = v.grab().toImage().pixelColor(pixel)
                for kind in (OpenDoorway, Door):
                    InstallScene(main, [wall, side, kind(wall, .3, .75)])
                    assert v.grab().toImage().pixelColor(pixel) == expected, (kind, angle, zoom)
        # Exercise the same junction through both export backends.
        wall = Wall(point(-1000, 0), point(1000, 0), 200)
        side = Wall(point(-500, 0), point(-500, 1000), 200)
        for kind in ("png", "svg"):
            images = []
            for openings in ([], [OpenDoorway(wall, .3, .75)]):
                InstallScene(main, [wall, side] + openings)
                result = RenderPlan(folder / "junction.plan", 500, (-1200, -400, 2400, 1800),
                                    outputFormat = kind, projectData = main.BuildProjectData(includeHistory = False),
                                    applyTheme = False, floors = False)
                if kind == "svg":
                    renderer = QtSvg.QSvgRenderer(result)
                    image = QtGui.QImage(1200, 900, QtGui.QImage.Format.Format_ARGB32)
                    image.fill(0)
                    with QtGui.QPainter(image) as painter:
                        renderer.render(painter)
                    result = image
                images.append(result)
            # x = -398, y = 112, at 0.5 pixels/mm within the old oversized cut.
            pixel = QtCore.QPoint(401, 644)
            assert images[0].pixelColor(pixel) == images[1].pixelColor(pixel), kind
    print("PASS: doorway junctions remain continuous at multiple angles/zooms and in PNG/SVG")


if __name__ == "__main__":
    Main()
