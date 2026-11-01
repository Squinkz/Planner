"""Fractional raster densities keep wall hatch tiles filtered and continuous."""
import math
import os
from pathlib import Path
import sys
from xml.etree import ElementTree
import numpy as np

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall
from planner_app.export_plan import RenderPlan
from planner_app.export_settings import ExportPixelSize
from planner_app.graphics.theme import BuildWallBrush


def CheckHatch(image, material, designSize, scale):
    ratioX, ratioY = image.width() / designSize[0], image.height() / designSize[1]
    # Both wall directions contain this square around their midpoint. Exclude
    # their edges/outlines so the expected pixels depend only on hatch sampling.
    sample = QtCore.QRect(math.ceil(4500 * scale * ratioX), math.ceil(3500 * scale * ratioY),
                         math.floor(1000 * scale * ratioX) - 2, math.floor(1000 * scale * ratioY) - 2)
    patches = []
    for filtered in (False, True):
        reference = QtGui.QImage(image.size(), image.format())
        reference.fill(QtCore.Qt.GlobalColor.transparent)
        with QtGui.QPainter(reference) as painter:
            painter.scale(ratioX, ratioY)
            painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, filtered)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            painter.setBrushOrigin(QtCore.QPointF(0, 8000 * scale))
            path = QtGui.QPainterPath()
            path.addRect(QtCore.QRectF(0, 0, *designSize))
            painter.fillPath(path, BuildWallBrush(material = material))
        patches.append(reference.copy(sample))
    if patches[0] == patches[1]:
        assert image.copy(sample) == patches[1], "Native-density hatch changed"
        return
    actual = image.copy(sample).convertToFormat(QtGui.QImage.Format.Format_RGB32)
    actualPixels = np.frombuffer(actual.constBits(), dtype = np.uint8).astype(np.int16)
    errors = []
    for patch in patches:
        patch = patch.convertToFormat(QtGui.QImage.Format.Format_RGB32)
        pixels = np.frombuffer(patch.constBits(), dtype = np.uint8).astype(np.int16)
        errors.append(float(np.abs(pixels - actualPixels).mean()))
    # QPainter's recorded-path replay can round texture phase slightly
    # differently from a direct rectangle. Allow that small coverage difference
    # while rejecting the much larger periodic gaps from nearest sampling.
    valid = errors[1] < 3 and errors[1] < errors[0] * .4
    if not valid:
        destination = Path(__file__).resolve().parents[1] / "diagnostics"
        image.copy(sample).save(str(destination / "hatch-actual.png"))
        patches[1].save(str(destination / "hatch-expected.png"))
    assert valid, (material, image.size(), errors, "Hatch has unfiltered gaps")


def Main():
    with ExampleWindow() as (main, folder):
        main.SetThemes(canvasTheme = "Light Canvas")
        v = main.viewport
        v.showGrid = v.showMeasurements = False
        bounds = (0, 0, 10000, 8000)
        baselineScale = 300 * 1000 / (25.4 * 100)
        designSize = ExportPixelSize(bounds, baselineScale, 0)
        for angled in (False, True):
            for material in ("Brick", "Metal", "Concrete Block"):
                first, second = ((500, 1000), (9500, 7000)) if angled else ((500, 4000), (9500, 4000))
                InstallScene(main, [Wall(QtCore.QPointF(*first), QtCore.QPointF(*second), 2000, material = material)])
                data = main.BuildProjectData(includeHistory = False, includeActivity = False)
                arguments = dict(planPath = "hatch.plan", scale = baselineScale, bounds = bounds, projectData = data,
                                 applyTheme = False, border = "None", architecturalScale = 100,
                                 furnishingDefinitions = v.furnishingDefinitions)
                for solid in (False, True):
                    for dpi, sampling in ((225, 1), (300, 1), (375, 1), (300, .75)):
                        image = RenderPlan(**arguments, dpi = dpi, preview = True, rasterSampling = sampling, solidObjects = solid)
                        CheckHatch(image, material, designSize, baselineScale / 1000)
                digital = RenderPlan(**dict(arguments, architecturalScale = None))
                CheckHatch(digital, material, designSize, baselineScale / 1000)
                overlay = v.exportOverlay
                overlay.scale, overlay.architecturalScale = baselineScale, 100
                image = overlay.CaptureRaster(QtCore.QRectF(*bounds), .75, "snapshot")
                CheckHatch(image, material, designSize, baselineScale / 1000)
                svg = ElementTree.fromstring(RenderPlan(**arguments, outputFormat = "svg"))
                namespace = {"s": "http://www.w3.org/2000/svg"}
                assert svg.find("s:defs/s:pattern", namespace) is not None
                assert not svg.findall(".//s:image", namespace), "SVG material hatch became a raster tile"
    print("Straight/angled hatches verified at fractional PPI and preview sampling; SVG stays vector")


if __name__ == "__main__":
    Main()
