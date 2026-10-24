"""Missing compound definitions recover children, transforms and memberships."""
import copy
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtWidgets
from furnishings import Furnishing, LoadFurnishings
from planner import MainWindow
from planner_app.furnishing_parts import FurnishingParts
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    v = main.viewport
    installed = dict(v.furnishingDefinitions)
    definitions = {item["key"]: item for item in LoadFurnishings(definitionOverrides = {
        "missing_leaf": {"name": "Missing Leaf", "inherits": "desk"},
        "missing_set": {"name": "Missing Set", "children": [
            {"furnishing": "chair_dining", "x": -650, "angle": 30},
            {"furnishing": "missing_leaf", "x": 650, "zIndex": 1}]},
        "missing_nested": {"name": "Missing Nested", "children": [
            {"furnishing": "missing_set", "angle": 45}, {"furnishing": "desk", "y": -1800}]}
    })}
    compound = Furnishing(definitions["missing_nested"], QtCore.QPointF(3100, -2200))
    compound.angle = 37
    compound.width *= 1.4
    center = (compound.firstVertex + compound.secondVertex) / 2
    halfAxis = (compound.secondVertex - compound.firstVertex) * 0.35
    compound.firstVertex, compound.secondVertex = center - halfAxis, center + halfAxis
    neighbor = Furnishing(installed["desk"], QtCore.QPointF(-3000, 0))
    v.furnishings = [compound, neighbor]
    v.walls, v.windows, v.labels = [], [], []
    v.objectGroups = [(compound, neighbor)]
    v.hiddenObjects = [compound]
    v.EnsureObjectIds()
    data = main.BuildProjectData()
    data.pop("furnishingDefinitions")
    expectedParents = FurnishingParts(compound)
    expected = FurnishingParts(expectedParents[0]) + [expectedParents[1]]
    decoded = DecodeProject(data, installed)
    recovered = decoded[2]
    assert len(recovered) == 4
    for obj, original in zip(recovered, expected):
        assert obj.definitionKey == original.definitionKey
        assert QtCore.QLineF(obj.firstVertex, original.firstVertex).length() < 1e-8
        assert QtCore.QLineF(obj.secondVertex, original.secondVertex).length() < 1e-8
        assert abs(obj.width - original.width) < 1e-8
    assert recovered[1].definition["key"] == "null" and recovered[1].definitionKey == "missing_leaf"
    assert decoded[3] == [tuple(recovered)]
    assert decoded[4] == recovered[:3]
    assert len({obj.objectId for obj in recovered}) == 4
    assert "history" not in decoded[5]  # Original compound history cannot target the new children.
    main.ApplyProject(decoded, None)
    resaved = main.BuildProjectData()
    assert len(DecodeProject(resaved, installed)[2]) == 4
    assert not RenderPlan("missing.plan", 20, (-5000, -6000, 12000, 10000), projectData = data, applyTheme = False).isNull()
    # Available compounds remain intact even when the embed is absent.
    assert len(DecodeProject(data, definitions)[2]) == 2
    # Older projects without child layout can only preserve the Null placeholder.
    legacy = copy.deepcopy(data)
    legacy["scene"]["objects"][0].pop("children")
    assert len(DecodeProject(legacy, installed)[2]) == 2
    # Missing dependencies of a surviving embedded compound also get Null graphics.
    v.furnishings, v.objectGroups, v.hiddenObjects = [compound], [], []
    partial = main.BuildProjectData()
    partial["furnishingDefinitions"].pop("missing_leaf")
    embedded = DecodeProject(partial, installed)[2][0].definition
    assert embedded["components"][0]["definition"]["components"][1]["definition"]["key"] == "null"
    broken = copy.deepcopy(data)
    broken["scene"]["objects"][0]["children"][0]["children"][0]["width"] = -1
    try:
        DecodeProject(broken, installed)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid fallback child was accepted")
    main.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
