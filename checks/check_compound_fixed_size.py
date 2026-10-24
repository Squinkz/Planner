"""JSON fixed-size children agree across rendering, collisions and project storage."""
import copy
import json
import os
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from furnishings import Furnishing, LoadFurnishings
from planner_app.furnishing_parts import FurnishingParts, FurnishingCollisionFootprints
from planner_app.graphics.furnishings import FurnishingRenderer, CompoundFurnishingSvg
from planner_app.paths import furnishingsDirectory
from planner_app.project_codec import DecodeProject
from check_furnishing_fixed import RedBounds


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    v = main.viewport
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        (folder / "definitions").mkdir()
        (folder / "images").mkdir()
        shutil.copy(furnishingsDirectory / "images" / "null.svg", folder / "images" / "null.svg")
        shutil.copy(furnishingsDirectory / "definitions" / "null.json", folder / "definitions" / "null.json")
        for name, color in (("base", "blue"), ("chair", "red")):
            (folder / "images" / (name + ".svg")).write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 60"><rect width="100" height="60" fill="{color}"/></svg>')
        children = [{"furnishing": "base"}, {"furnishing": "chair", "x": 700, "y": 100, "fixedSize": True}]
        records = {"base": {"name": "Base", "image": "base", "width": 1000, "length": 600},
                   "chair": {"name": "Chair", "image": "chair", "width": 200, "length": 100},
                   "fixed_set": {"name": "Fixed Set", "children": children},
                   "invalid": {"children": [dict(children[1], fixedSize = "true")]}}
        for name, record in records.items():
            (folder / "definitions" / (name + ".json")).write_text(json.dumps(record))
        with warnings.catch_warnings(record = True) as notices:
            definitions = {definition["key"]: definition for definition in LoadFurnishings(folder)}
        assert len(notices) == 1 and "invalid" not in definitions
        definition = definitions["fixed_set"]
        definition["isUser"] = True
        assert definition["components"][1]["fixedSize"] is True
        renderer = FurnishingRenderer(definition["graphicData"], nominalSize = (definition["width"], definition["length"]))
        assert len(renderer.fixedElements) == 1
        for scaleX, scaleY in ((1, 1), (2, 2), (.5, .5), (2, .5)):
            parent = Furnishing(definition)
            parent.width = definition["width"] * scaleX
            halfLength = definition["length"] * scaleY / 2
            parent.firstVertex, parent.secondVertex = QtCore.QPointF(0, -halfLength), QtCore.QPointF(0, halfLength)
            child = FurnishingParts(parent)[1]
            shrink = min(1, scaleX, scaleY)
            assert abs(child.width - 200 * shrink) < 1e-6
            assert abs(child.length - 100 * shrink) < 1e-6
            footprints = FurnishingCollisionFootprints(parent)
            assert abs(footprints[1][0].width() - child.width) < 1e-6
            assert abs(footprints[1][0].height() - child.length) < 1e-6
            image = QtGui.QImage(600, 300, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QtCore.Qt.GlobalColor.white)
            with QtGui.QPainter(image) as painter:
                renderer.render(painter, QtCore.QRectF(20, 20, parent.width * .2, parent.length * .2),
                                worldSize = (parent.width, parent.length))
            red = RedBounds(image)
            assert abs(red.width() - child.width * .2) <= 1
            assert abs(red.height() - child.length * .2) <= 1
            center = (child.firstVertex + child.secondVertex) / 2
            assert abs(red.center().x() - (20 + (center.x() + parent.width / 2) * .2)) <= 1
            assert abs(red.center().y() - (20 + (parent.length / 2 - center.y()) * .2)) <= 1
        # Fixed rotated children remain rectangular through parent flips and unequal scaling.
        components = [definition["components"][0], dict(definition["components"][1], angle = -30)]
        graphic, width, length, compoundCenter = CompoundFurnishingSvg(components)
        angled = dict(definition, components = components, graphicData = graphic, width = width,
                       length = length, compoundCenter = compoundCenter)
        for horizontal, vertical in ((False, False), (True, False), (False, True), (True, True)):
            parent = Furnishing(angled)
            parent.width *= .75
            parent.firstVertex *= 2
            parent.secondVertex *= 2
            parent.angle = 37
            parent.flipHorizontal, parent.flipVertical = horizontal, vertical
            child = FurnishingParts(parent)[1]
            corners = FurnishingCollisionFootprints(parent)[1][1]
            expected = {(round(point.x(), 5), round(point.y(), 5)) for point in v.ObjectCorners(child)}
            assert {(round(x, 5), round(y, 5)) for x, y in corners} == expected
        # Persistent embedded metadata retains the optional flag and validates its type.
        v.furnishingDefinitions = {**v.furnishingDefinitions, **definitions}
        v.walls, v.windows, v.labels, v.objectGroups = [], [], [], []
        v.furnishings = [Furnishing(definition)]
        v.EnsureObjectIds()
        data = main.BuildProjectData(includeHistory = False)
        assert data["furnishingDefinitions"]["fixed_set"]["components"][1]["fixedSize"] is True
        decoded = DecodeProject(data, v.furnishingDefinitions)
        assert decoded[2][0].definition["components"][1]["fixedSize"] is True
        restored = decoded[2][0].definition
        restoredRenderer = FurnishingRenderer(restored["graphicData"], nominalSize = (restored["width"], restored["length"]))
        assert len(restoredRenderer.fixedElements) == 1
        invalid = copy.deepcopy(data)
        invalid["furnishingDefinitions"]["fixed_set"]["components"][1]["fixedSize"] = 1
        try:
            DecodeProject(invalid, v.furnishingDefinitions)
        except ValueError:
            pass
        else:
            raise AssertionError("Non-boolean fixedSize was accepted")
        main.projectDirty = False
        main.close()


if __name__ == "__main__":
    Main()
