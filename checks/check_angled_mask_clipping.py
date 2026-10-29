"""Angled wall masks preserve interior ink in editor, PNG and SVG at varied scales."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Stair, Counter, Railing, Furnishing, Door, Window, Column, Fireplace
from planner_app.graphics.palette import themeColors
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from planner_app.export_plan import RenderPlan


def CheckInk(reference, actual, rect, context):
    rect = rect.intersected(reference.rect()).intersected(actual.rect())
    reference = reference.copy(rect).convertToFormat(QtGui.QImage.Format.Format_RGB32)
    actual = actual.copy(rect).convertToFormat(QtGui.QImage.Format.Format_RGB32)
    expected = bytes(reference.constBits())[0::4]
    observed = bytes(actual.constBits())[0::4]
    ink = [index for index, value in enumerate(expected) if value < 32]
    assert len(ink) > 10, (context, "Reference must contain visible object ink", len(ink))
    missing = sum(observed[index] >= 100 for index in ink)
    assert missing == 0, (context, "Mask removed interior ink", missing, len(ink))


def ExportImage(main, folder, scale, output, bounds, solid):
    result = RenderPlan(folder / "masks.plan", scale, bounds, projectData = main.BuildProjectData(),
                        outputFormat = output, applyTheme = False, solidObjects = solid)
    if output == "png":
        return result
    renderer = SvgPreviewRenderer(result)
    assert renderer.isValid()
    image = QtGui.QImage(renderer.size, QtGui.QImage.Format.Format_RGB32)
    image.fill(QtCore.Qt.GlobalColor.white)
    with QtGui.QPainter(image) as painter:
        renderer.render(painter)
    return image


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        themeColors.update(canvas = "#ffffff", roomFill = "#eeeeee", wallFill = "#cccccc",
                           wallOutline = "#000000", objectOutline = "#000000", grid = "#000000")
        v.showGrid = v.showMeasurements = v.showTips = False
        v.lineWidths.update(walls = 4, architectural = 1)
        points = [p(-2200, -2200), p(3000, -1850), p(2100, 2700), p(-2000, 3100)]
        walls = [Wall(a, b, 300) for a, b in zip(points, points[1:] + points[:1])]
        column = Column(p(-2050, 700), p(-2050, 1300), 500)
        openings = [Door(walls[2], .2, .6), Window(walls[1], .25, .65), Fireplace(walls[0], .5, .8)]
        # Keep a nonempty wall path in the reference without covering the crop.
        # Qt's SVG backend can stroke a move-only empty path as a dot at origin.
        referenceWall = Wall(p(10000, 10000), p(11000, 10000))
        # A real window plus a door/fireplace exercises both outline holes and
        # wall-fill cuts. An overlapping column exercises curved material masks.
        for kind in (Stair, Counter, Railing, Furnishing):
            objects = ([Furnishing(v.furnishingDefinitions["desk"], p(0, 400))] if kind is Furnishing else
                       [kind(p(-900, 800), p(1300, 700), 700), kind(p(1300, 700), p(1250, -800), 700)])
            for zoom, pan in ((.22, p()), (.42, p(13.25, -7.75)), (.47, p(-41.5, 23.25)),
                              (.88, p(.37, .71)), (1.3, p(-100, -50))):
                v.zoom, v.panOffset = zoom, pan
                InstallScene(main, objects + [referenceWall])
                reference = v.grab().toImage()
                InstallScene(main, walls + [column] + openings + objects)
                region = QtCore.QRectF(v.WorldToViewport(p(-1300, 1400)),
                                      v.WorldToViewport(p(1800, -1400))).normalized().toAlignedRect()
                ratio = reference.devicePixelRatioF()
                region = QtGui.QTransform().scale(ratio, ratio).mapRect(region)
                for floors in (False, True):
                    v.floors = floors
                    actual = v.grab().toImage()
                    CheckInk(reference, actual, region, (kind.__name__, zoom, pan, floors))
            # Crop through the enclosing walls as well as around the entire
            # room. SVG is parsed and painted, rather than merely validated.
            for bounds, scale in (([-3000, -3000, 6500, 6500], 84), ([-1500, -1500, 3500, 3500], 176)):
                x, y, _, height = bounds
                ppm = scale / 1000
                region = QtCore.QRectF((-1300 - x) * ppm, (y + height - 1400) * ppm,
                                      3100 * ppm, 2800 * ppm).toAlignedRect()
                for solid in (False, True):
                    for output in ("png", "svg"):
                        InstallScene(main, objects + [referenceWall])
                        reference = ExportImage(main, folder, scale, output, bounds, solid)
                        InstallScene(main, walls + [column] + openings + objects)
                        actual = ExportImage(main, folder, scale, output, bounds, solid)
                        CheckInk(reference, actual, region, (kind.__name__, bounds, solid, output))
        # Solid-room grid masks have a separate stroke-subtraction path. Check
        # its interior and exterior independently, without object ink over it.
        InstallScene(main, walls + [column] + openings)
        v.showGrid, v.floors = True, False
        v.gridIntensities = dict(overall = 1.0, origin = 1.0, major = 1.0, minor = 1.0)
        for zoom in (.22, .47, .88):
            v.zoom = zoom
            v.roomDetection.Refresh(force = True)
            origin = v.WorldToViewport(p())
            ppm = v.basePixelsPerMillimeter * zoom
            room = QtGui.QTransform().translate(origin.x(), origin.y()).scale(ppm, -ppm).map(v.roomDetection.path)
            stroke = QtGui.QPainterPathStroker()
            stroke.setWidth(4)
            edge = stroke.createStroke(room)
            images = []
            for solid in (False, True):
                v.solidRooms = solid
                image = QtGui.QImage(v.size(), QtGui.QImage.Format.Format_RGB32)
                image.fill(QtCore.Qt.GlobalColor.white)
                with QtGui.QPainter(image) as painter:
                    v.DrawGridBackground(painter, v.DrawingRect(), origin, ppm, gridOnly = True)
                images.append(image)
            changed = 0
            for x in range(30, v.width() - 2, 3):
                for y in range(30, v.height() - 2, 3):
                    point = p(x + .5, y + .5)
                    if edge.contains(point):
                        continue
                    before, after = (image.pixelColor(x, y) for image in images)
                    if room.contains(point):
                        assert after == QtGui.QColor("white"), (zoom, point, "Interior grid leaked")
                        changed += before != after
                    else:
                        assert before == after, (zoom, point, "Exterior grid was clipped")
            assert changed > 10, (zoom, "Probe must intersect interior grid lines", changed,
                                  room.boundingRect(), themeColors["grid"], v.showGrid, v.GridSteps())
    print("PASS: angled masks retain isolated-object ink across editor zoom/pan, floors, columns, PNG/SVG, transparency and crops")


if __name__ == "__main__":
    Main()
