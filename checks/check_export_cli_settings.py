"""CLI exports match the Export tab, with explicit density and optional crop."""
import json
import os
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
appDirectory = Path(__file__).resolve().parents[1] / "planner-main"
sys.path.insert(0, str(appDirectory))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Furnishing, Label, NorthArrow, Wall
from planner_app.export_plan import RenderPlan
from planner_app.project_codec import DecodeProject
from planner_app.graphics import palette


def Main():
    with ExampleWindow() as (main, folder):
        point = QtCore.QPointF
        v, panel = main.viewport, main.exportPanel
        wall = Wall(point(500, 1500), point(4500, 1500), 200)
        wall.material = "Brick"
        furnishing = Furnishing(v.furnishingDefinitions["desk"], point(3000, 3000))
        InstallScene(main, [wall, furnishing, NorthArrow(point(1000, 3000)), Label(point(4000, 500), "CLI")])
        v.showGrid = False
        v.showMeasurements = False
        v.visibility["World"] = False
        v.visibility["Walls"] = False
        v.unitsMode = "Inches"
        panel.overrides = {
            "bounds": [0, 0, 6000, 4500], "scale": 100, "canvasTheme": "Light Canvas",
            "canvasColor": "#e9e2ca", "linesColor": "#452b69", "gridColor": "#81918c",
            "borderColor": "#adacb9", "border": "Ruler + Reference Zones", "borderSize": 63,
            "wallStyle": "Outline", "solidObjects": False, "gridOrigin": [150, -220],
            "showGrid": True, "viewportSettings": {"overall": .6, "minor": .2},
            "lineworkSettings": {"baseWidth": 2, "walls": .8},
            "measurementVisibility": {"walls": True}, "visibility": {"Walls": True},
            "measurementPrecision": "High", "measurementSettings": {"doors": 0, "windows": 2}, "wallMeasurementMode": "All",
            "unitsMode": "Centimeters", "vignetteEnabled": True, "vignetteStrength": .4,
            "texture": "cardboard_t1_75_25_5_5.png", "textureAngle": 37,
            "textureScale": 1.3, "textureStrength": .3, "textureHighlights": .7,
            "textureMidtones": .4, "textureShadows": .2}
        main.sidebarTabs.setCurrentWidget(panel)
        main.appPreferences.update({"uiTheme": palette.activeUITheme, "canvasTheme": palette.activeCanvasTheme})
        main.SaveAppPreferences()
        planPath = Path(folder) / "cli.plan"
        data = main.BuildProjectData(includeHistory = False)
        # The mandatory CLI density overrides saved scale units and print mode.
        data["settings"]["exportSettings"].update({"scale": 900, "scaleUnits": "px/cm",
                                                  "scaleMode": "Architectural", "architecturalScale": 25, "dpi": 600})
        planPath.write_text(json.dumps(data), encoding = "utf-8")
        original = planPath.read_bytes()
        command = [sys.executable, "-m", "planner_app.export_plan", str(planPath), "100"]
        for outputFormat in ("png", "svg"):
            expected = panel.Render(outputFormat)
            result = subprocess.run(command + ["-" + outputFormat], cwd = appDirectory,
                                    capture_output = True, text = True)
            assert result.returncode == 0, result.stderr
            outputPath = planPath.parent / "renders" / ("cli_100p." + outputFormat)
            if outputFormat == "png":
                actual = QtGui.QImage(str(outputPath))
                assert actual == expected, "CLI ignored saved appearance, effects, units or crop"
            else:
                actual = ElementTree.parse(outputPath).getroot()
                expected = ElementTree.fromstring(expected)
                # The unsaved UI fixture is titled "plan"; the CLI uses its filename.
                title = "{http://www.w3.org/2000/svg}title"
                actual.find(title).text = expected.find(title).text
                resolved = ElementTree.fromstring(RenderPlan(planPath, 100, outputFormat = "svg", useExportSettings = True))
                resolved.find(title).text = expected.find(title).text
                assert ElementTree.tostring(resolved) == ElementTree.tostring(expected), "Saved-settings SVG differs from Export tab"
                # Qt can produce slightly different glyph outlines in separate
                # processes. Check CLI layout and paints exactly; the same-process
                # comparison above checks every path without a geometry tolerance.
                assert actual.attrib == expected.attrib
                assert len(list(actual.iter())) == len(list(expected.iter()))
                for left, right in zip(actual.iter(), expected.iter()):
                    assert left.tag == right.tag
                    assert {key: value for key, value in left.attrib.items() if key != "d"} == {
                        key: value for key, value in right.attrib.items() if key != "d"}
                assert actual.get("width") == actual.get("viewBox").split()[2], "CLI retained architectural scaling"
        v.exportOverlay.bounds = (-500, -500, 7000, 5500)
        panel.SetBounds(v.exportOverlay.bounds)
        expected = panel.Render("png")
        result = subprocess.run(command + ["-500", "-500", "7000", "5500", "-png"],
                                cwd = appDirectory, capture_output = True, text = True)
        assert result.returncode == 0, result.stderr
        assert QtGui.QImage(str(outputPath.with_suffix(".png"))) == expected, "CLI bounds did not override saved crop"
        assert planPath.read_bytes() == original, "CLI modified its input project"

        # With no saved crop, automatic bounds use export visibility rather than
        # the editor's disabled World/Walls state. Old ruler flags remain readable.
        data["settings"]["exportSettings"] = {"ruler": True, "visibility": {"Walls": True}, "showGrid": False}
        planPath.write_text(json.dumps(data), encoding = "utf-8")
        result = subprocess.run(command, cwd = appDirectory, capture_output = True, text = True)
        assert result.returncode == 0 and "Automatic bounds" in result.stdout, result.stderr
        cliImage = QtGui.QImage(str(outputPath.with_suffix(".png")))
        decoded = DecodeProject(data, v.furnishingDefinitions)
        assert decoded[5]["exportSettings"]["ruler"] is True
        # The shared saved-settings path is opt-in: explicit API callers retain
        # their original render arguments and are not overridden by the file.
        plain = RenderPlan(planPath, 100, (0, 0, 6000, 4500))
        assert plain.size() == QtCore.QSize(600, 450)
        assert cliImage.width() != plain.width() or cliImage.height() != plain.height()
        del data["settings"]["exportSettings"]
        data["settings"]["visibility"]["World"] = True
        planPath.write_text(json.dumps(data), encoding = "utf-8")
        result = subprocess.run(command, cwd = appDirectory, capture_output = True, text = True)
        assert result.returncode == 0 and "Automatic bounds" in result.stdout, result.stderr
        noBorder = RenderPlan(planPath, 100)
        defaultImage = QtGui.QImage(str(outputPath.with_suffix(".png")))
        assert defaultImage.size() == noBorder.size() + QtCore.QSize(112, 112), "Missing settings lost the default reference-zone border"
        # Missing unit overrides inherit the saved project units in both the UI
        # and CLI/API path, including imperial dimension and ruler formatting.
        data["settings"]["exportSettings"] = {"bounds": [0, 0, 6000, 4500], "border": "Ruler", "showGrid": True,
                                              "canvasTheme": "Light Canvas", "visibility": {"Walls": True}}
        main.ApplyProject(DecodeProject(data, v.furnishingDefinitions), planPath)
        main.sidebarTabs.setCurrentWidget(panel)
        assert panel.unitsField.currentText() == "Inches" and "unitsMode" not in panel.overrides
        for kind in ("png", "svg"):
            expected = panel.Render(kind)
            actual = RenderPlan(planPath, 100, outputFormat = kind, projectData = data, useExportSettings = True)
            assert actual == expected, f"Inherited project units differ between Export and CLI ({kind})"
    print("CLI saved settings: PNG/SVG UI parity, crop precedence, automatic crop, legacy borders and read-only input passed")


if __name__ == "__main__":
    Main()
