"""Compound resolution, SVG composition, nesting and normal furnishing behavior."""
import json
import math
import os
import shutil
import sys
import tempfile
import warnings
import xml.etree.ElementTree as ElementTree
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from furnishings import LoadFurnishings, Furnishing
from planner import MainWindow, Wall
from planner_app.graphics.furnishings import FurnishingRenderer, SelectedFurnishingRenderer
from planner_app.project_codec import DecodeProject
from planner_app.graphics.palette import themeColors


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    sourceFolder = Path(__file__).resolve().parent.parent / "planner-main/furnishings"
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        (folder / "definitions").mkdir()
        shutil.copytree(sourceFolder / "images", folder / "images")
        (folder / "images/line.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M 50 0 V 100" fill="none" stroke="#d1d8dd" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>')
        defaults = json.loads((sourceFolder / "definitions/null.json").read_text())
        children = [{"furnishing": "table", "zIndex": 1},
                    {"furnishing": "chair", "x": -320, "y": 550},
                    {"furnishing": "chair", "x": 320, "y": 550},
                    {"furnishing": "chair", "x": -320, "y": -550, "angle": 180},
                    {"furnishing": "chair", "x": 320, "y": -550, "angle": 180}]
        definitions = {
            "null": defaults,
            "table": {"image": "beveled_rectangle", "width": 1200, "length": 800},
            "chair": {"image": "chair", "width": 450, "length": 500},
            "set": {"name": "Dining Set", "children": children},
            "nested": {"children": [{"furnishing": "set", "angle": 90, "scale": .5}]},
            "inherited": {"inherits": "set", "name": "Inherited", "width": 9990, "length": 9990},
            "replaced": {"inherits": "set", "children": [{"furnishing": "chair"}]},
            "sized": {"children": [{"furnishing": "chair", "width": 800, "length": 300, "angle": 90}]},
            "missing": {"children": [{"furnishing": "removed"}]},
            "offset": {"children": [{"furnishing": "chair", "x": 3200, "y": -850, "angle": 45}]},
            "line": {"image": "line"},
            "line_set": {"children": [{"furnishing": "line", "scale": 2}]},
            "self_cycle": {"children": [{"furnishing": "self_cycle"}]},
            "cycle_a": {"children": [{"furnishing": "cycle_b"}]},
            "cycle_b": {"inherits": "cycle_a"},
            "bad_scale": {"children": [{"furnishing": "chair", "scale": 2, "width": 1000}]},
            "bad_position": {"children": [{"furnishing": "chair", "x": "bad"}]}
        }
        for key, definition in definitions.items():
            (folder / "definitions" / (key + ".json")).write_text(json.dumps(definition))
        with warnings.catch_warnings(record = True) as messages:
            loaded = {item["key"]: item for item in LoadFurnishings(folder)}
        assert len(messages) == 5
        assert not any(key in loaded for key in ("self_cycle", "cycle_a", "cycle_b", "bad_scale", "bad_position"))
        for key, width, length in (("set", 1200, 1600), ("nested", 800, 600), ("inherited", 1200, 1600),
                                   ("replaced", 450, 500), ("sized", 300, 800), ("missing", 1000, 1000)):
            assert abs(loaded[key]["width"] - width) < 1e-6 and abs(loaded[key]["length"] - length) < 1e-6
            assert QtSvg.QSvgRenderer(loaded[key]["graphicData"]).isValid()
        # Equal priorities retain definition order; table renders above chairs.
        root = ElementTree.fromstring(loaded["set"]["graphicData"])
        assert root[-1].attrib["transform"] == "translate(0.0 -0.0) rotate(-0.0)"
        renderer = FurnishingRenderer(loaded["set"]["graphicData"])
        image = QtGui.QImage(240, 320, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        renderer.render(painter, QtCore.QRectF(0, 0, 240, 320))
        painter.end()
        assert image.pixelColor(120, 50).alpha() == 0  # Gap between upper chairs.
        assert image.pixelColor(120, 160).name() == themeColors["canvas"]
        assert image.pixelColor(3, 3).alpha() == 0
        # Nested graphics and selection colors both render through SVG, not boxes.
        selected = SelectedFurnishingRenderer(loaded["nested"]["graphicData"])
        selectedImage = QtGui.QImage(320, 240, QtGui.QImage.Format.Format_ARGB32)
        selectedImage.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(selectedImage)
        selected.render(painter, QtCore.QRectF(0, 0, 320, 240))
        painter.end()
        assert any(selectedImage.pixelColor(x, y).name() == themeColors["selectionOutline"]
                   for x in range(320) for y in range(240))
        renderer = QtSvg.QSvgRenderer(loaded["line_set"]["graphicData"])
        thicknesses = []
        for width in (100, 300):
            lineImage = QtGui.QImage(width, 100, QtGui.QImage.Format.Format_ARGB32)
            lineImage.fill(QtCore.Qt.GlobalColor.transparent)
            painter = QtGui.QPainter(lineImage)
            renderer.render(painter, QtCore.QRectF(0, 0, width, 100))
            painter.end()
            thicknesses.append(sum(lineImage.pixelColor(x, 50).alpha() > 0 for x in range(width)))
        assert thicknesses[0] == thicknesses[1] and thicknesses[0] > 0
        # Later canvas edits import child assets, so retain their bytes after
        # this temporary catalog's image files are removed.
        for item in loaded.values():
            if not item.get("graphicData"):
                item["graphicData"] = Path(item["imagePath"]).read_bytes()
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.ResetView()
    v.SetSelection([])
    v.walls, v.windows, v.labels, v.furnishings = [], [], [], []
    definition = v.furnishingDefinitions["dining_set_4"]
    furnishing = Furnishing(definition)
    v.furnishings = [furnishing]
    assert abs(furnishing.width - definition["width"]) < 1e-6
    assert abs(furnishing.length - definition["length"]) < 1e-6
    assert v.furnishingRenderers[definition["key"]].isValid()
    v.SetSelection([(furnishing, None)])
    v.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots/compound-dining-set.png"))
    # A compound stays one selected entity, with separate child collision footprints.
    assert len(v.SelectionEntries()) == 1
    v.walls = [Wall(QtCore.QPointF(-500, 650), QtCore.QPointF(500, 650), 80)]
    assert not v.FurnishingFits(furnishing)
    v.walls = []
    furnishing.angle = 37
    furnishing.width *= 1.5
    furnishing.secondVertex = furnishing.firstVertex + (furnishing.secondVertex - furnishing.firstVertex) * .8
    decoded = DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)
    restored = decoded[2][0]
    assert restored.definition is definition and abs(restored.angle - 37) < 1e-6
    assert abs(restored.width - furnishing.width) < 1e-6 and abs(restored.length - furnishing.length) < 1e-6
    v.CopySelection()
    assert v.ReadClipboardSelection()["objects"][0]["definition"] == "dining_set_4"
    v.PasteSelection(v.WorldToViewport(QtCore.QPointF(1500, 0)))
    assert len(v.furnishings) == 2 and v.furnishings[-1].definition is definition
    # Decomposition accounts for rotation, independent width/length scaling,
    # the authored bounds' center, stable z-order and surrounding scene layers.
    compound = Furnishing(loaded["set"], QtCore.QPointF(300, -200))
    compound.width *= 1.5
    compound.firstVertex = QtCore.QPointF(300, -840)
    compound.secondVertex = QtCore.QPointF(300, 440)
    compound.angle = 37
    behind, ahead = Furnishing(loaded["chair"]), Furnishing(loaded["table"])
    v.furnishings = [behind, compound, ahead]
    v.objectGroups = [(compound, ahead)]
    v.groupModeEnabled = False
    v.SetSelection([(compound, None)])
    historyCount = len(v.undoHistory)
    assert v.DecomposeFurnishings([compound])
    parts = v.furnishings[1:-1]
    assert v.furnishings[0] is behind and v.furnishings[-1] is ahead
    assert [part.definition["key"] for part in parts] == ["chair"] * 4 + ["table"]
    assert v.objectGroups == [tuple(parts) + (ahead,)]
    assert len(v.undoHistory) == historyCount + 1
    assert len(v.SelectionEntries()) == 5
    components = sorted(enumerate(loaded["set"]["components"]), key = lambda entry: (entry[1]["zIndex"], entry[0]))
    for part, (index, child) in zip(parts, components):
        x, y = child["x"] * 1.5, child["y"] * .8
        radians = math.radians(37)
        expected = QtCore.QPointF(300 + x * math.cos(radians) - y * math.sin(radians),
                                 -200 + x * math.sin(radians) + y * math.cos(radians))
        assert QtCore.QLineF((part.firstVertex + part.secondVertex) / 2, expected).length() < 1e-6
        assert abs(part.width - child["width"] * 1.5) < 1e-6
        assert abs(part.length - child["length"] * .8) < 1e-6
        assert abs(part.angle - (child["angle"] + 37) % 360) < 1e-6
    v.Undo()
    assert v.furnishings == [behind, compound, ahead] and v.objectGroups == [(compound, ahead)]
    v.Redo()
    assert v.furnishings == [behind] + parts + [ahead]
    # Nested compounds unpack one level at a time, retaining their child scale.
    nested = Furnishing(loaded["nested"], QtCore.QPointF(400, 600))
    nested.angle = 30
    v.objectGroups = []
    v.furnishings = [nested]
    v.SetSelection([(nested, None)])
    assert v.DecomposeFurnishings([nested])
    child = v.furnishings[0]
    assert child.definition["key"] == "set" and abs(child.angle - 120) < 1e-6
    assert abs(child.width - 600) < 1e-6 and abs(child.length - 800) < 1e-6
    assert QtCore.QLineF((child.firstVertex + child.secondVertex) / 2, QtCore.QPointF(400, 600)).length() < 1e-6
    assert v.DecomposeFurnishings([child]) and len(v.furnishings) == 5
    offset = Furnishing(loaded["offset"], QtCore.QPointF(-150, 250))
    offset.width *= 2
    offset.firstVertex = QtCore.QPointF(-150, 250 - offset.length)
    offset.secondVertex = QtCore.QPointF(-150, 250 + loaded["offset"]["length"])
    offset.angle = 35
    v.furnishings = [offset]
    assert v.DecomposeFurnishings([offset])
    part = v.furnishings[0]
    assert QtCore.QLineF((part.firstVertex + part.secondVertex) / 2, QtCore.QPointF(-150, 250)).length() < 1e-6
    assert abs(part.angle - 80) < 1e-6
    assert abs(part.width - 900) < 1e-6 and abs(part.length - 1000) < 1e-6
    v.furnishings = [Furnishing(loaded["missing"])]
    assert v.DecomposeFurnishings(v.furnishings[:])
    assert v.furnishings[0].definition["key"] == "null"
    main.close()
    app.clipboard().clear()
    app.processEvents()


if __name__ == "__main__":
    Main()
