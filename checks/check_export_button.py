"""Export the unsaved scene with export overrides, without changing project state."""
import copy
import os
import sys
import tempfile
import re
from xml.etree import ElementTree
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner import MainWindow, Wall
from planner_app.graphics import palette
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.project_codec import DecodeProject
from planner_app.ui.color_picker import ColorPickerDialog
from planner_app.export_plan import RenderPlan


def Main():
    with tempfile.TemporaryDirectory(dir = Path(__file__).parent) as folder:
        folder = Path(folder)
        os.environ["PLANNER_SESSION_PATH"] = str(folder / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(folder / "startup.plan")
        app = QtWidgets.QApplication([])
        ApplyApplicationTheme(app)
        main = MainWindow()
        main.show()
        v = main.viewport
        v.walls = [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), 240)]
        v.EnsureObjectIds()
        v.sceneRevision += 1
        main.projectPath = folder / "unsaved.plan"
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        panel = main.exportPanel
        panel.scaleField.setValue(100)
        originalResolution = [field.value() for field in panel.resolutionFields]
        panel.scaleUnitsField.setCurrentText("px/cm")
        assert panel.scaleField.value() == 1 and panel.scaleField.decimals() == 2
        assert v.exportOverlay.scale == 100 and [field.value() for field in panel.resolutionFields] == originalResolution
        panel.scaleField.setValue(3)
        assert panel.overrides["scale"] == 300 and v.exportOverlay.scale == 300
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        assert panel.scaleUnitsField.count() == 1 and panel.scaleUnitsField.currentText() == "units/m"
        assert panel.scaleField.value() == 300 and panel.scaleField.decimals() == 2
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        assert panel.scaleUnitsField.currentText() == "px/cm" and panel.scaleField.value() == 3
        assert panel.scaleField.decimals() == 2
        panel.scaleUnitsField.setCurrentText("px/m")
        assert panel.scaleField.value() == 300
        panel.scaleField.setValue(250)
        panel.scaleUnitsField.setCurrentText("px/cm")
        assert panel.scaleField.value() == 2.5 and panel.overrides["scale"] == 250
        panel.scaleUnitsField.setCurrentText("px/m")
        panel.scaleField.setValue(100)
        assert DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)[5]["exportSettings"]["scaleUnits"] == "px/m"
        panel.showGridField.setChecked(False)
        panel.borderField.setCurrentText("Ruler")
        with patch.object(ColorPickerDialog, "GetColor", return_value = QtGui.QColor("#123456")):
            panel.canvasColorButton.click()
        panel.SetOverride("lineworkSettings", 3.0, "baseWidth")
        v.exportOverlay.MoveEdge(0, -1500)
        app.processEvents()
        before = copy.deepcopy(main.BuildProjectData(includeHistory = False))
        view = panel.CaptureView()
        themes = (palette.activeUITheme, palette.activeCanvasTheme, dict(palette.themeColors))
        data = copy.deepcopy(before)
        data["settings"].update(view)
        expected = RenderPlan(main.projectPath, 100, v.exportOverlay.bounds, ruler = True,
                              projectData = data, applyTheme = False)
        assert expected.pixelColor(v.rulerSize + 5, v.rulerSize + 5).name() == "#123456"
        outputPath = panel.OutputPath()
        main.exportButton.click()
        assert outputPath.exists() and QtGui.QImage(str(outputPath)) == expected
        assert not main.projectPath.exists(), "Export required saving the project first"
        assert panel.OutputPath() == folder / "unsaved_1.png"
        main.exportButton.click()
        assert (folder / "unsaved_1.png").exists()
        assert panel.OutputPath() == folder / "unsaved_2.png"
        panel.unitsField.setCurrentText("Centimeters")
        view = panel.CaptureView()
        before = copy.deepcopy(main.BuildProjectData(includeHistory = False))
        data = copy.deepcopy(before)
        data["settings"].update(view)
        expectedSvg = RenderPlan(main.projectPath, 100, v.exportOverlay.bounds, ruler = True,
                                 outputFormat = "svg", projectData = data, applyTheme = False)
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        svgPath = panel.OutputPath()
        # Choosing the format is now a persisted project edit. Export itself
        # must preserve the settings after that choice.
        before = copy.deepcopy(main.BuildProjectData(includeHistory = False))
        main.exportButton.click()
        renderer = QtSvg.QSvgRenderer(str(svgPath))
        assert renderer.isValid() and renderer.defaultSize() == expected.size()
        actualSvg = svgPath.read_bytes()
        actualRoot, expectedRoot = ElementTree.fromstring(actualSvg), ElementTree.fromstring(expectedSvg)
        actualElements, expectedElements = list(actualRoot.iter()), list(expectedRoot.iter())
        assert len(actualElements) == len(expectedElements)
        expectedParents = {child: parent for parent in expectedRoot.iter() for child in parent}
        for actual, expectedElement in zip(actualElements, expectedElements):
            assert actual.tag == expectedElement.tag and actual.text == expectedElement.text
            actualAttributes, expectedAttributes = dict(actual.attrib), dict(expectedElement.attrib)
            if actualAttributes.get("d") != expectedAttributes.get("d"):
                # Qt rounds unhinted ruler glyph outlines to 1/64 px differently
                # in a fresh process. Only those text outlines get this allowance;
                # every other attribute, scene path, command and position is exact.
                parent = expectedParents[expectedElement]
                assert parent.get("stroke") == "none" and parent.get("font-size") == "10.6667"
                actualPath, expectedPath = actualAttributes.pop("d"), expectedAttributes.pop("d")
                tokens = r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?|[A-Za-z]"
                actualTokens, expectedTokens = re.findall(tokens, actualPath), re.findall(tokens, expectedPath)
                assert len(actualTokens) == len(expectedTokens)
                for actualToken, expectedToken in zip(actualTokens, expectedTokens):
                    if expectedToken.isalpha():
                        assert actualToken == expectedToken
                    else:
                        assert abs(float(actualToken) - float(expectedToken)) <= .0161
            assert actualAttributes == expectedAttributes, "SVG changed export geometry, appearance or units"
        assert b"<image" not in svgPath.read_bytes(), "SVG contains raster content"
        assert panel.CaptureView() == view
        assert main.BuildProjectData(includeHistory = False) == before
        assert (palette.activeUITheme, palette.activeCanvasTheme, dict(palette.themeColors)) == themes

        # A manually chosen existing path is protected; declining changes nothing.
        panel.folderField.setText(str(svgPath.parent))
        panel.fileNameField.setText(svgPath.name)
        contents = svgPath.read_bytes()
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.No) as question:
            main.exportButton.click()
            question.assert_called_once()
            assert question.call_args.args == ("Replace Export", "Replace the existing file?", "warning")
            assert question.call_args.kwargs["informativeText"] == str(svgPath)
            assert question.call_args.kwargs["defaultButton"] == QtWidgets.QMessageBox.StandardButton.No
        assert svgPath.read_bytes() == contents
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Yes):
            main.exportButton.click()
        assert svgPath.read_bytes() == contents

        # Failed writes report an error and leave the button and cursor usable.
        panel.folderField.setText(str(svgPath))
        panel.fileNameField.setText("blocked.svg")
        with patch.object(main, "ShowAppMessage") as warning:
            main.exportButton.click()
            warning.assert_called_once()
        assert main.exportButton.isEnabled() and app.overrideCursor() is None
        assert svgPath.read_bytes() == contents
        panel.borderField.setCurrentText("Plain")
        assert v.exportOverlay.drawRuler and v.exportOverlay.borderStyle == "Plain"
        assert DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)[5]["exportSettings"]["border"] == "Plain"
        plain = panel.Render("png")
        assert plain.size() == expected.size()
        background = QtGui.QColor(palette.themeColors["rulerBackground"]).rgba()
        for row in range(plain.height()):
            for column in range(plain.width()):
                if (row < v.rulerSize or row >= plain.height() - v.rulerSize
                        or column < v.rulerSize or column >= plain.width() - v.rulerSize):
                    assert plain.pixelColor(column, row).rgba() == background
        plainSvg = panel.Render("svg")
        plainRenderer = QtSvg.QSvgRenderer(plainSvg)
        assert plainRenderer.isValid() and plainRenderer.defaultSize() == plain.size()
        assert b"<image" not in plainSvg
        v.grab()
        main.close()
        print("PASS: Export button PNG/SVG, unsaved changes, overrides, rulers, numbering, overwrite and write failure")


if __name__ == "__main__":
    Main()
