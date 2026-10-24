"""Verify world crop placement, repeatable scale, labels and CLI errors."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
appDirectory = Path(__file__).resolve().parent.parent / "planner-main"
sys.path.insert(0, str(appDirectory))
from PySide6 import QtCore, QtGui, QtWidgets, QtSvg
from planner_app.export_plan import RenderPlan


def Main():
    app = QtWidgets.QApplication([])
    data = json.loads((appDirectory / "startup.plan").read_text(encoding = "utf-8"))
    data.pop("history", None)
    data["settings"]["showGrid"] = False
    data["settings"]["showMeasurements"] = False
    data["settings"]["visibility"] = dict.fromkeys(data["settings"]["visibility"], True)
    data["settings"]["exportSettings"] = {"border": "None"}
    data["scene"] = {"objects": [
        {"type": "Wall", "id": 1, "first": [1000, 2000], "second": [3000, 2000],
         "width": 200, "material": "Generic", "firstMiter": 0, "secondMiter": 0},
        {"type": "Label", "id": 2, "first": [1500, 3000], "second": [1500, 3500],
         "width": 1000, "text": "Export", "intensity": 1.0}], "groups": [], "hidden": []}
    with tempfile.TemporaryDirectory(dir = Path(__file__).resolve().parent) as tempDirectory:
        planPath = Path(tempDirectory) / "fixture.plan"
        planPath.write_text(json.dumps(data), encoding = "utf-8")
        fullImage = RenderPlan(planPath, 100, (0, 0, 4000, 4000))
        assert (fullImage.width(), fullImage.height()) == (400, 400)
        rulerImage = RenderPlan(planPath, 100, (0, 0, 4000, 4000), ruler = True)
        assert (rulerImage.width(), rulerImage.height()) == (456, 456)
        # The shared frame covers the crop's boundary pixels, not its interior.
        assert rulerImage.copy(29, 29, 398, 398) == fullImage.copy(1, 1, 398, 398), "Rulers change scale or crop placement"
        from planner_app.graphics.palette import themeColors
        assert rulerImage.pixelColor(50, 28) == QtGui.QColor(themeColors["rulerMinorTick"]), "Top separator missing"
        assert rulerImage.pixelColor(28, 50) == QtGui.QColor(themeColors["rulerMinorTick"]), "Left separator missing"
        assert rulerImage.pixelColor(50, 428) == QtGui.QColor(themeColors["rulerMinorTick"]), "Bottom separator missing"
        assert rulerImage.pixelColor(428, 50) == QtGui.QColor(themeColors["rulerMinorTick"]), "Right separator missing"
        assert rulerImage.pixelColor(0, 0) == QtGui.QColor(themeColors["border"]), "Outer frame missing"
        assert rulerImage.pixelColor(0, 0) != fullImage.pixelColor(0, 0), "Ruler background is missing"
        assert len({rulerImage.pixel(px, py) for px in range(28, 428) for py in range(28)}) > 1, "Top ruler ticks are missing"
        assert len({rulerImage.pixel(px, py) for px in range(28) for py in range(28, 428)}) > 1, "Left ruler ticks are missing"
        assert len({rulerImage.pixel(px, py) for px in range(28, 428) for py in range(429, 455)}) > 1, "Bottom ruler ticks are missing"
        assert len({rulerImage.pixel(px, py) for px in range(429, 455) for py in range(28, 428)}) > 1, "Right ruler ticks are missing"
        cropImage = RenderPlan(planPath, 100, (1000, 1000, 2000, 2000))
        assert cropImage == fullImage.copy(100, 100, 200, 200), "World crop is misplaced"
        assert fullImage.pixelColor(200, 200) != fullImage.pixelColor(200, 250), "Wall is missing"
        largerImage = RenderPlan(planPath, 200, (0, 0, 4000, 4000))
        assert (largerImage.width(), largerImage.height()) == (800, 800)
        assert largerImage.pixelColor(400, 400) == fullImage.pixelColor(200, 200)
        negativeImage = RenderPlan(planPath, 100, (-1000, -1000, 6000, 6000))
        assert negativeImage.copy(100, 100, 400, 400) == fullImage
        fractionalImage = RenderPlan(planPath, 100, (0, 0, 1001, 1001))
        assert (fractionalImage.width(), fractionalImage.height()) == (101, 101)
        for scale, bounds in ((0, (0, 0, 1000, 1000)), (100, (0, 0, -1, 1000)),
                              (float("nan"), (0, 0, 1000, 1000)), (1e9, (0, 0, 1000, 1000))):
            try:
                RenderPlan(planPath, scale, bounds)
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid inputs were accepted")
        command = [sys.executable, "-m", "planner_app.export_plan", str(planPath),
                   "100", "0", "0", "4000", "4000"]
        result = subprocess.run(command, cwd = appDirectory, capture_output = True, text = True)
        assert result.returncode == 0, result.stderr
        outputPath = planPath.parent / "renders" / "fixture_100p.png"
        assert QtGui.QImage(str(outputPath)) == fullImage, "CLI PNG differs from renderer"
        autoImage = RenderPlan(planPath, 100)
        assert autoImage == RenderPlan(planPath, 100, (0, 900, 4000, 3600)), "Auto bounds omit width or padding"
        autoCommand = command[:5]
        result = subprocess.run(autoCommand, cwd = appDirectory, capture_output = True, text = True)
        assert result.returncode == 0, result.stderr
        assert QtGui.QImage(str(outputPath)) == autoImage
        data["settings"]["exportSettings"]["border"] = "Ruler"
        planPath.write_text(json.dumps(data), encoding = "utf-8")
        result = subprocess.run(autoCommand, cwd = appDirectory, capture_output = True, text = True)
        assert result.returncode == 0, result.stderr
        autoRulerImage = QtGui.QImage(str(outputPath))
        assert autoRulerImage.copy(29, 29, autoImage.width() - 2, autoImage.height() - 2) == autoImage.copy(1, 1, autoImage.width() - 2, autoImage.height() - 2)
        result = subprocess.run(command, cwd = appDirectory, capture_output = True, text = True)
        assert result.returncode == 0, result.stderr
        assert QtGui.QImage(str(outputPath)) == rulerImage
        svgCommand = command + ["-svg"]
        result = subprocess.run(svgCommand, cwd = appDirectory, capture_output = True, text = True)
        assert result.returncode == 0, result.stderr
        svgPath = outputPath.with_suffix(".svg")
        svgRoot = ElementTree.parse(svgPath).getroot()
        svgNamespace = "{http://www.w3.org/2000/svg}"
        assert svgRoot.get("viewBox") == "0 0 456 456"
        assert svgRoot.get("width") == "456" and svgRoot.get("height") == "456"
        assert svgRoot.findall(f".//{svgNamespace}clipPath"), "SVG lost crop masks"
        for clipPath in svgRoot.findall(f".//{svgNamespace}clipPath"):
            assert clipPath.get("clipPathUnits") == "userSpaceOnUse"
            for shape in clipPath:
                assert shape.get("clip-rule") == shape.get("fill-rule", "nonzero"), "Clip holes use the wrong winding rule"
        assert not svgRoot.findall(f".//{svgNamespace}image"), "SVG contains raster content"
        assert not svgRoot.findall(f".//{svgNamespace}text"), "SVG text still depends on installed fonts"
        assert svgRoot.findall(f".//{svgNamespace}path"), "Vector drawing paths missing"
        svgRenderer = QtSvg.QSvgRenderer(str(svgPath))
        assert svgRenderer.isValid()
        svgImage = QtGui.QImage(svgRenderer.defaultSize(), QtGui.QImage.Format.Format_ARGB32)
        svgImage.fill(QtCore.Qt.GlobalColor.transparent)
        svgPainter = QtGui.QPainter(svgImage)
        svgRenderer.render(svgPainter)
        svgPainter.end()
        # Compare broad areas while allowing rasterizer differences at glyph edges.
        mismatches = sum(svgImage.pixelColor(px, py) != rulerImage.pixelColor(px, py)
                         for px in range(0, 456, 4) for py in range(0, 456, 4))
        assert mismatches / (114 * 114) < .08, "SVG layout differs substantially from PNG"
        result = subprocess.run(command + ["-svg", "-png"], cwd = appDirectory, capture_output = True, text = True)
        assert result.returncode != 0, "Conflicting output formats accepted"
        data["settings"]["exportSettings"]["border"] = "None"
        from planner_app.graphics.theme import materialPatternSpacings
        for material, spacing in materialPatternSpacings.items():
            data["scene"]["objects"][0]["material"] = material
            planPath.write_text(json.dumps(data), encoding = "utf-8")
            for patternScale in (100, 200):
                svgData = RenderPlan(planPath, patternScale, (0, 0, 4000, 4000), outputFormat = "svg")
                materialRoot = ElementTree.fromstring(svgData)
                patterns = materialRoot.findall(f".//{svgNamespace}pattern")
                assert len(patterns) == 1
                assert patterns[0].get("width") == str(spacing) and patterns[0].get("height") == str(spacing)
                assert patterns[0].get("patternUnits") == "userSpaceOnUse"
                assert not materialRoot.findall(f".//{svgNamespace}image"), f"{material} contains raster tiles"
                assert QtSvg.QSvgRenderer(svgData).isValid()
        data["scene"]["objects"][0]["material"] = "Generic"
        # Qt's own SVG reader can hide a clip-restore export bug. Inspect the
        # effective masks on actual opening geometry rather than only rasterizing.
        originalScene = data["scene"]
        data["scene"] = {"objects": [
            {"type": "Wall", "id": 1, "first": [1000, 2000], "second": [5000, 2000],
             "width": 200, "material": "Generic", "firstMiter": 0, "secondMiter": 0},
            {"type": "Window", "id": 2, "parent": 0, "center": .25, "length": 1000,
             "swingsOutwards": False, "measurementFlipped": False},
            {"type": "BifoldDoor", "id": 3, "parent": 0, "center": .75, "length": 1000,
             "swingsOutwards": False, "measurementFlipped": False}], "groups": [], "hidden": []}
        planPath.write_text(json.dumps(data), encoding = "utf-8")
        openingRoot = ElementTree.fromstring(RenderPlan(planPath, 50, (0, 0, 6000, 4000), outputFormat = "svg"))
        clipDefinitions = {clip.get("id"): clip for clip in openingRoot.findall(f".//{svgNamespace}clipPath")}
        openingSegments = 0
        bifoldPanels = 0
        pending = [(openingRoot, [])]
        while pending:
            element, inheritedClips = pending.pop()
            activeClips = inheritedClips + ([element.get("clip-path")[5:-1]] if element.get("clip-path") else [])
            isWindowEdge = (element.tag == svgNamespace + "polyline" and
                            element.get("points", "").strip() in ("75,105 125,105", "75,95 125,95"))
            isBifoldPanel = element.tag == svgNamespace + "polygon"
            if isWindowEdge or isBifoldPanel:
                openingSegments += int(isWindowEdge)
                bifoldPanels += int(isBifoldPanel)
                assert activeClips, "Opening geometry lost the crop mask"
                for clipId in activeClips:
                    paths = clipDefinitions[clipId].findall(f"{svgNamespace}path")
                    assert all(path.get("d", "").count("M") == 1 for path in paths), "Opening inherits a wall mask with cutouts"
            pending.extend((child, activeClips) for child in element)
        assert openingSegments == 2 and bifoldPanels == 4, "Window or bifold geometry missing"
        data["scene"] = originalScene
        for removedOption in ("-auto", "--auto", "-ruler", "--ruler"):
            result = subprocess.run(command + [removedOption], cwd = appDirectory, capture_output = True, text = True)
            assert result.returncode != 0 and "unrecognized arguments" in result.stderr
        result = subprocess.run(command[:6], cwd = appDirectory, capture_output = True, text = True)
        assert result.returncode != 0 and "all four bounds" in result.stderr
        data["scene"]["hidden"] = [1]
        planPath.write_text(json.dumps(data), encoding = "utf-8")
        assert RenderPlan(planPath, 100) == RenderPlan(planPath, 100, (0, 900, 4000, 2200)), "Hidden labels enlarge bounds"
        data["scene"]["hidden"] = []
        data["scene"]["objects"].pop()
        planPath.write_text(json.dumps(data), encoding = "utf-8")
        assert RenderPlan(planPath, 100, (0, 0, 4000, 4000)) != fullImage, "Label is missing"
        data["scene"]["objects"][0]["second"] = [3000, 4000]
        planPath.write_text(json.dumps(data), encoding = "utf-8")
        rotatedImage = RenderPlan(planPath, 100)
        assert (rotatedImage.width(), rotatedImage.height()) == (415, 415), "Rotated footprint width omitted"
        data["settings"]["visibility"]["Walls"] = False
        planPath.write_text(json.dumps(data), encoding = "utf-8")
        result = subprocess.run(autoCommand, cwd = appDirectory, capture_output = True, text = True)
        assert result.returncode != 0 and "no visible objects" in result.stderr
        command[4] = "0"
        result = subprocess.run(command, cwd = appDirectory, capture_output = True, text = True)
        assert result.returncode != 0 and "greater than zero" in result.stderr
        from planner_app.graphics import palette
        appThemes = (palette.activeUITheme, palette.activeCanvasTheme)
        for uiTheme, canvasTheme in (("Neutral UI", "Dark Canvas"), ("Dark UI", "Light Canvas")):
            palette.SetThemes(*appThemes)
            data["settings"]["uiTheme"] = uiTheme
            data["settings"]["canvasTheme"] = canvasTheme
            data.setdefault("settings", {}).setdefault("exportSettings", {}).pop("canvasTheme", None)
            planPath.write_text(json.dumps(data), encoding = "utf-8")
            image = RenderPlan(planPath, 100, (0, 0, 4000, 4000))
            assert (palette.activeUITheme, palette.activeCanvasTheme) == appThemes
            data["settings"]["exportSettings"]["canvasTheme"] = canvasTheme
            planPath.write_text(json.dumps(data), encoding = "utf-8")
            image = RenderPlan(planPath, 100, (0, 0, 4000, 4000))
            assert (palette.activeUITheme, palette.activeCanvasTheme) == (appThemes[0], canvasTheme)
            assert image.pixelColor(0, 0).name() == palette.themeDefinitions[canvasTheme]["colors"]["canvas"]
            assert QtSvg.QSvgRenderer(RenderPlan(planPath, 100, (0, 0, 4000, 4000), outputFormat = "svg")).isValid()
        planPath.write_text("{}", encoding = "utf-8")
        command[4] = "100"
        result = subprocess.run(command, cwd = appDirectory, capture_output = True, text = True)
        assert result.returncode != 0 and "supported Planner project" in result.stderr
    print("Export checks passed")


if __name__ == "__main__":
    Main()
