"""Frozen object render examples. Recording is explicit; normal runs never rewrite references."""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from xml.etree import ElementTree

workspace = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app import models
from planner_app.export_plan import RenderPlan
from planner_app.graphics import palette
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from planner_app.graphics.furnishings import CompoundFurnishingSvg
from fixtures.parity_examples import ExampleWindow, CreateObject, InstallScene, CompareExamples, objectTypes, openingTypes, referenceDirectory


def RenderExamples(record = False, recordCases = ()):
    recordCases = set(recordCases)
    target = referenceDirectory / "rendering"
    if record:
        target.mkdir(exist_ok = True)
    results = []
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.setUpdatesEnabled(False)
        v.unitsMode = "Millimeters"
        v.showMeasurements = True
        v.measurementVisibility = {key: True for key in v.measurementVisibility}
        v.measurementSettings = {key: 0 for key in v.measurementSettings}
        cases = [{"id": name.lower(), "type": name, "theme": "Dark Canvas", "scale": 100, "format": "png"}
                 for name in objectTypes]
        cases += [{"id": "window-well" + ("-svg" if format == "svg" else ""), "type": "Window",
                   "theme": "Dark Canvas", "scale": 100, "format": format, "windowWell": True}
                  for format in ("png", "svg")]
        for key in ("washer", "treadmill", "kitchen_sink_drainer_dbl2", "chair_office", "chair_office_armless", "table_dining_round_6"):
            # Keep the published example ID stable across catalog renames.
            definitionKey = "sink_drainer_dbl2" if key == "kitchen_sink_drainer_dbl2" else key
            cases.append({"id": key, "type": "Furnishing", "definition": definitionKey, "theme": "Light Canvas", "scale": 250, "format": "png"})
        components = []
        for key, x, y, angle, zIndex in (("table_dining_round_6", 0, 0, 0, 0),
                                        ("chair_dining", 0, 650, 180, 1), ("chair_dining", 0, -650, 0, 2)):
            definition = v.furnishingDefinitions[key]
            components.append(dict(definition = definition, definitionKey = key, x = x, y = y, angle = angle,
                                   width = definition["width"], length = definition["length"], zIndex = zIndex))
        graphic, width, length, center = CompoundFurnishingSvg(components)
        v.furnishingDefinitions["parity-compound"] = dict(v.furnishingDefinitions["table_dining_round_6"],
            key = "parity-compound", name = "Parity dining compound", width = width, length = length,
            components = components, compoundCenter = center, graphicData = graphic, isUser = True)
        cases.append({"id": "compound-dining", "type": "Furnishing", "definition": "parity-compound",
                      "theme": "Light Canvas", "scale": 250, "format": "png"})
        for architectural in (False, True):
            cases.append({"id": "washer-svg-" + ("architectural" if architectural else "digital"),
                          "type": "Furnishing", "definition": "washer", "theme": "Light Canvas", "scale": 100,
                          "format": "svg", "architecturalScale": 100 if architectural else None})
        assert not recordCases - {case["id"] for case in cases}, "Unknown render example"
        currentTheme = None
        for case in cases:
            recordCase = record or case["id"] in recordCases
            if currentTheme != case["theme"]:
                # Canvas paint roles change here; the Fusion/Dark UI font and QSS
                # remain fixed. Reapplying app-wide QSS per image is unnecessary.
                palette.SetThemes(canvasTheme = case["theme"])
                currentTheme = case["theme"]
            obj = models.Furnishing(v.furnishingDefinitions[case["definition"]]) if "definition" in case else CreateObject(v, case["type"])
            if case.get("windowWell"):
                obj.windowWell = True
            objects = [obj.parentWall, obj] if case["type"] in openingTypes else [obj]
            if isinstance(obj, models.RoomLabel):
                corners = [QtCore.QPointF(-1500, -1000), QtCore.QPointF(1500, -1000),
                           QtCore.QPointF(1500, 1000), QtCore.QPointF(-1500, 1000)]
                objects = [models.Wall(first, second, 200) for first, second in zip(corners, corners[1:] + corners[:1])] + [obj]
            InstallScene(main, objects)
            bounds = [-3500, -2000, 7000, 4000] if case["type"] in openingTypes else [-2000, -1500, 4000, 3000]
            # A fixed crop and unselected export isolate geometry, glyph placement and strokes.
            project = main.BuildProjectData(includeHistory = False)
            planName = case["id"] + ".plan"
            if recordCase:
                (target / planName).write_text(json.dumps(project, indent = 2, ensure_ascii = False), encoding = "utf-8", newline = "\n")
            else:
                saved = json.loads((target / planName).read_text(encoding = "utf-8"))
                # UI splitter state is platform layout data, covered by the control gallery.
                CompareExamples(project["scene"], saved["scene"], case["id"] + ".scene")
                project = saved
            rendered = RenderPlan(target / planName, case["scale"], bounds = bounds, projectData = project, applyTheme = False,
                                  outputFormat = case["format"], architecturalScale = case.get("architecturalScale"))
            # RenderPlan schedules its temporary viewport for deletion; this
            # batch has no normal event loop to drain those deferred deletes.
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
            svgInfo = None
            if case["format"] == "svg":
                root = ElementTree.fromstring(rendered)
                elements = list(root.iter())
                svgInfo = {"width": root.get("width"), "height": root.get("height"), "viewBox": root.get("viewBox"),
                           "paths": sum(element.tag.endswith("}path") for element in elements),
                           "images": sum(element.tag.endswith("}image") for element in elements),
                           "text": sum(element.tag.endswith("}text") for element in elements),
                           "nonScalingStrokes": rendered.count(b"non-scaling-stroke")}
                assert svgInfo["paths"] > 0 and svgInfo["images"] == 0 and svgInfo["nonScalingStrokes"] == 0, svgInfo
                renderer = SvgPreviewRenderer(rendered)
                assert renderer.isValid()
                image = QtGui.QImage(renderer.defaultSize(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(QtCore.Qt.GlobalColor.transparent)
                painter = QtGui.QPainter(image)
                try:
                    renderer.render(painter)
                finally:
                    painter.end()
                if recordCase:
                    (target / (case["id"] + ".svg")).write_bytes(rendered)
            else:
                image = rendered
            assert not image.isNull(), case["id"]
            image = image.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
            digest = hashlib.sha256(bytes(image.constBits())).hexdigest()
            result = dict(case, boundsMillimeters = bounds, plan = planName, image = case["id"] + ".png",
                          pixels = [image.width(), image.height()], rgbaSha256 = digest, svg = svgInfo)
            if recordCase:
                assert image.save(str(target / result["image"]))
            else:
                reference = QtGui.QImage(str(target / result["image"])).convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
                assert image == reference, (case["id"], "decoded pixels differ; inspect before updating")
            results.append(result)
    fonts = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted((workspace / "planner-main/assets/fonts").glob("*.ttf"))}
    return {"format": "Planner object render examples", "version": 1, "qt": QtCore.qVersion(),
            "style": "Fusion", "devicePixelRatio": 1, "fontSha256": fonts, "cases": results}


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--record", action = "store_true")
    parser.add_argument("--record-case", action = "append", dest = "recordCases", default = [])
    arguments = sys.argv[1:]
    if arguments and arguments[0] == __file__:
        arguments = arguments[1:]
    options = parser.parse_args(arguments)
    record, recordCases = options.record, options.recordCases
    actual = RenderExamples(record, recordCases)
    target = referenceDirectory / "rendering" / "manifest.json"
    if record:
        target.write_text(json.dumps(actual, indent = 2), encoding = "utf-8", newline = "\n")
    else:
        expected = json.loads(target.read_text(encoding = "utf-8"))
        if recordCases:
            replacements = {case["id"]: case for case in actual["cases"] if case["id"] in recordCases}
            expectedCases = {case["id"]: case for case in expected["cases"]}
            expectedCases.update(replacements)
            assert set(expectedCases) == {case["id"] for case in actual["cases"]}, "Unreviewed render inventory change"
            expected["cases"] = [expectedCases[case["id"]] for case in actual["cases"]]
        # Version is capture provenance. Exact pixels, geometry and fonts still
        # have to match when validating a patched Qt runtime.
        CompareExamples({**actual, "qt": expected["qt"]}, expected)
        if recordCases:
            target.write_text(json.dumps(expected, indent = 2), encoding = "utf-8", newline = "\n")
    if record or recordCases:
        print(f"Recorded {len(actual['cases']) if record else len(set(recordCases))} render examples; all other examples verified")
    else:
        print(f"PASS: {len(actual['cases'])} object PNG/SVG render examples")


if __name__ == "__main__":
    Main()
