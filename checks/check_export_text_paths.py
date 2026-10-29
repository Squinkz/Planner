"""Native raster text has no colour fringes; every SVG annotation is outlined."""
import copy
import json
import os
from pathlib import Path
import sys
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))

from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.export_plan import RenderPlan
from planner_app.graphics import palette
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.text import PathTextPainter


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    data = json.loads((root / "planner-main" / "startup.plan").read_text(encoding = "utf-8-sig"))
    data.pop("history", None)
    data.pop("activityLog", None)
    data["settings"].update(showGrid = False, showMeasurements = True)
    data["settings"]["visibility"] = dict.fromkeys(data["settings"]["visibility"], True)
    data["scene"] = dict(objects = [
        dict(type = "Wall", id = 1, first = [1000, 2000], second = [5000, 2000], width = 200,
             material = "Generic", firstMiter = 0, secondMiter = 0),
        dict(type = "Label", id = 2, first = [3000, 3500], second = [3000, 4200], width = 2200,
             text = "Living room\nSecond line", intensity = 1.0)], groups = [], hidden = [])
    # All source colours are neutral, so any coloured pixel is a font-rendering artefact.
    for role, value in list(palette.themeColors.items()):
        color = QtGui.QColor(value)
        level = color.lightness()
        palette.themeColors[role] = QtGui.QColor(level, level, level, color.alpha()).name(QtGui.QColor.NameFormat.HexArgb)
    for role in ("canvas", "rulerBackground", "wallFill"):
        palette.themeColors[role] = "#ffffff"
    for role in ("objectOutline", "wallOutline", "measurementLine", "rulerText", "rulerMajorTick", "rulerMinorTick", "border"):
        palette.themeColors[role] = "#000000"
    for mode in ("Millimeters", "Feet and Inches"):
        fixture = copy.deepcopy(data)
        fixture["settings"]["unitsMode"] = mode
        for border in ("Ruler", "Ruler + Reference Zones"):
            options = dict(enabled = True, projectName = "Text paths", address = "12 Oak Street\nCape Town", comments = "Reference", sheetNumber = "0001")
            args = dict(planPath = "text.plan", scale = 100, bounds = (0, 0, 6000, 5000), projectData = fixture,
                        applyTheme = False, border = border, titleBlock = options)
            raster = RenderPlan(**args)
            pixels = memoryview(raster.constBits())
            assert all(blue == green == red for blue, green, red in zip(pixels[0::4], pixels[1::4], pixels[2::4])), f"Coloured text fringes in {mode} {border}"
            svg = ElementTree.fromstring(RenderPlan(**args, outputFormat = "svg"))
            assert not any(element.tag.rsplit("}", 1)[-1] in ("text", "tspan", "textPath") for element in svg.iter()), "SVG contains live text"
            assert any(element.tag.endswith("}path") for element in svg.iter())
    # Rectangular and baseline text use the same outline renderer on a native image.
    image = QtGui.QImage(400, 180, QtGui.QImage.Format.Format_RGB32)
    image.fill(QtCore.Qt.GlobalColor.white)
    painter = PathTextPainter(image)
    painter.setPen(QtCore.Qt.GlobalColor.black)
    painter.drawText(QtCore.QRectF(0, 0, 400, 80), QtCore.Qt.AlignmentFlag.AlignCenter, "Ruler 12,345")
    painter.drawText(QtCore.QPointF(20, 130), "Dimension and label")
    painter.end()
    pixels = memoryview(image.constBits())
    assert all(blue == green == red for blue, green, red in zip(pixels[0::4], pixels[1::4], pixels[2::4]))
    print("Export text outline checks passed")


if __name__ == "__main__":
    Main()
