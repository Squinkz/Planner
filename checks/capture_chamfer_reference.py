"""Explicit, synthetic chamfer render references for the porting specification."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys

workspace = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui
from planner_app.models import Wall
from planner_app.graphics import palette
from planner_app.export_plan import RenderPlan
from fixtures.parity_examples import ExampleWindow, InstallScene, referenceDirectory


def Main():
    target = referenceDirectory / "chamfers"
    target.mkdir(exist_ok = True)
    records = []
    sheet = QtGui.QImage(1080, 6 * 380, QtGui.QImage.Format.Format_ARGB32)
    sheet.fill(QtGui.QColor("#eeeeee"))
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.setUpdatesEnabled(False)
        v.showGrid = v.showMeasurements = False
        palette.SetThemes(canvasTheme = "Light Canvas")
        painter = QtGui.QPainter(sheet)
        try:
            painter.setFont(QtGui.QFont("Noto Sans", 10))
            for row, (degrees, widths) in enumerate((degrees, widths) for degrees in (30, 90, 135)
                                                   for widths in ((240, 240), (120, 360))):
                for column, amount in enumerate((0, .5, 1)):
                    angle = math.radians(degrees)
                    walls = [Wall(QtCore.QPointF(), QtCore.QPointF(5000, 0), widths[0], amount, 0, "Brick"),
                             Wall(QtCore.QPointF(), QtCore.QPointF(math.cos(angle), math.sin(angle)) * 5000,
                                  widths[1], amount, 0, "Wood")]
                    InstallScene(main, walls)
                    project = main.BuildProjectData(includeHistory = False)
                    name = f"angle{degrees}-widths{widths[0]}-{widths[1]}-chamfer{amount}"
                    path = target / (name + ".plan")
                    path.write_text(json.dumps(project, indent = 2), encoding = "utf-8", newline = "\n")
                    bounds = [-700, -600, 1400, 1400]
                    image = RenderPlan(path, 250, bounds = bounds, projectData = project, applyTheme = False)
                    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
                    assert image.save(str(target / (name + ".png")))
                    painter.drawImage(column * 360, row * 380, image)
                    painter.setPen(QtGui.QColor("#161616"))
                    painter.drawText(QtCore.QRect(column * 360, row * 380 + 350, 350, 30),
                                     QtCore.Qt.AlignmentFlag.AlignCenter, f"{degrees}° · {widths[0]}/{widths[1]} mm · {amount:g}")
                    rgba = image.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
                    records.append(dict(id = name, angleDegrees = degrees, widthsMillimeters = list(widths),
                        chamfer = amount, scalePixelsPerMeter = 250, boundsMillimeters = bounds,
                        plan = path.name, image = name + ".png", rgbaSha256 = hashlib.sha256(bytes(rgba.constBits())).hexdigest()))
        finally:
            painter.end()
    assert sheet.save(str(target / "gallery.png"))
    manifest = dict(rule = "CHAMFER-01", qt = QtCore.qVersion(), devicePixelRatio = 1,
                    theme = "Light Canvas", cases = records)
    (target / "manifest.json").write_text(json.dumps(manifest, indent = 2), encoding = "utf-8", newline = "\n")
    print("Recorded 18 angle/thickness/chamfer material render examples")


if __name__ == "__main__":
    Main()
