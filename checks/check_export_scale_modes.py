"""Linked pixel dimensions, separate scale modes and physical export metadata."""
import math
import os
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.project_codec import DecodeProject


def Main():
    with tempfile.TemporaryDirectory(dir = Path(__file__).parent) as folder:
        os.environ["PLANNER_SESSION_PATH"] = str(Path(folder) / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(Path(folder) / "startup.plan")
        app = QtWidgets.QApplication([])
        ApplyApplicationTheme(app)
        main = MainWindow()
        main.show()
        panel, v = main.exportPanel, main.viewport
        main.sidebarTabs.setCurrentWidget(panel)
        assert panel.scaleField.value() == 100 and panel.ScalePerMeter() == 100
        assert panel.architecturalScaleField.currentText() == "1:100"
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        assert panel.scaleField.value() == 100 and panel.ScalePerMeter() == 100
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        v.exportOverlay.bounds = (0, 0, 10000, 5000)
        panel.borderField.setCurrentText("None")
        panel.scaleField.setValue(123.45)
        assert panel.scaleField.decimals() == 2 and panel.ScalePerMeter() == 123.45
        assert not panel.digitalScaleRow.isHidden() and not panel.resolutionRow.isHidden()
        assert panel.architecturalRow.isHidden() and panel.dpiRow.isHidden()
        panel.scaleUnitsField.setCurrentText("px/cm")
        assert panel.ScalePerMeter() == 123.45, "Unit conversion rounded the export density"
        panel.scaleUnitsField.setCurrentText("px/m")
        panel.resolutionFields[0].setValue(1367)
        assert panel.ScalePerMeter() == 136.7 and panel.resolutionFields[1].value() == 684
        assert panel.Render("png").size() == QtCore.QSize(1367, 684)
        v.exportOverlay.bounds = (0, 0, 12345.67, 5678.9)
        panel.resolutionFields[0].setValue(777)
        assert panel.Render("png").width() == 777
        assert panel.resolutionFields[0].value() == 777
        v.exportOverlay.bounds = (0, 0, 10000, 5000)
        panel.resolutionFields[1].setValue(500)
        assert panel.ScalePerMeter() == 100 and panel.resolutionFields[0].value() == 1000
        panel.borderField.setCurrentText("Plain")
        panel.resolutionFields[0].setValue(1056)
        assert panel.ScalePerMeter() == 100
        assert panel.resolutionFields[1].value() == 556
        assert panel.Render("png").size() == QtCore.QSize(1056, 556)
        panel.borderField.setCurrentText("None")
        panel.scaleModeTabs.setCurrentIndex(1)
        assert panel.digitalScaleRow.isHidden() and panel.resolutionRow.isHidden()
        assert not panel.architecturalRow.isHidden() and not panel.dpiRow.isHidden()
        assert abs(panel.ScalePerMeter() - 300 * 1000 / (25.4 * 100)) < .000001
        image = panel.Render("png")
        assert image.size() == QtCore.QSize(1182, 591)
        assert abs(image.dotsPerMeterX() * .0254 - 300) < .02
        path = Path(folder) / "architectural.png"
        assert image.save(str(path))
        assert QtGui.QImage(str(path)).dotsPerMeterX() == image.dotsPerMeterX()
        panel.architecturalScaleField.setCurrentText("1:100")
        panel.SetArchitecturalScale()
        panel.dpiField.setCurrentText("600")
        panel.SetDpi()
        assert abs(panel.ScalePerMeter() - 600 * 1000 / (25.4 * 100)) < .000001
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        assert panel.dpiRow.isHidden() and panel.resolutionRow.isHidden()
        assert not panel.architecturalRow.isHidden()
        density = 96 * 1000 / (25.4 * 100)
        assert abs(panel.ScalePerMeter() - density) < .000001
        root = ElementTree.fromstring(panel.Render("svg"))
        v.grab()
        assert not v.exportOverlay.previewError, v.exportOverlay.previewError
        assert v.exportOverlay.svgRenderer is not None and v.exportOverlay.svgNavigationImage is not None
        assert v.exportOverlay.svgRenderer.defaultSize() == QtCore.QSize(math.ceil(float(root.get("viewBox").split()[2])),
                                                                        math.ceil(float(root.get("viewBox").split()[3])))
        assert root.get("width").endswith("mm") and root.get("height").endswith("mm")
        unitsWidth = float(root.get("viewBox").split()[2])
        widthMm = float(root.get("width")[:-2])
        assert abs(widthMm / unitsWidth * density / 1000 - .01) < 1e-10
        assert abs(widthMm - 100) < .3
        panel.scaleModeTabs.setCurrentIndex(0)
        assert not panel.digitalScaleRow.isHidden() and panel.resolutionRow.isHidden()
        assert panel.ScalePerMeter() == 100
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        assert not panel.resolutionRow.isHidden() and panel.scaleField.value() == 100
        panel.scaleModeTabs.setCurrentIndex(1)
        assert panel.architecturalScaleField.currentText() == "1:100" and panel.dpiField.currentText() == "600"
        settings = DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)[5]["exportSettings"]
        assert settings["scale"] == 100 and settings["scaleMode"] == "Architectural"
        assert settings["architecturalScale"] == 100 and settings["dpi"] == 600
        panel.architecturalScaleField.setCurrentText("invalid")
        panel.SetArchitecturalScale()
        assert panel.architecturalScaleField.currentText() == "1:100"
        panel.dpiField.setCurrentText("0")
        panel.SetDpi()
        assert panel.dpiField.currentText() == "600"
        main.close()
        print("PASS: decimal scale, linked dimensions, mode visibility, remembered values, PNG DPI and SVG physical scale")


if __name__ == "__main__":
    Main()
