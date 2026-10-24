"""Used custom furniture survives transfer without installing its catalogue."""
import copy
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtSvg, QtWidgets
from furnishings import LoadFurnishings, Furnishing
from planner import MainWindow
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    v = main.viewport
    localDefinitions = dict(v.furnishingDefinitions)
    definitions = {item["key"]: item for item in LoadFurnishings(definitionOverrides = {
        "portable_desk": {"inherits": "desk", "name": "Portable Desk", "width": 1250},
        "portable_set": {"name": "Portable Set", "children": [
            {"furnishing": "portable_desk"}, {"furnishing": "chair_dining", "y": 900}]},
        "unused_portable": {"inherits": "desk", "name": "Unused Portable"}
    })}
    v.furnishingDefinitions = definitions
    main.RefreshFurnishingRenderers()
    v.walls, v.windows, v.labels = [], [], []
    v.furnishings = [Furnishing(definitions[key], QtCore.QPointF(index * 4000, 0))
                     for index, key in enumerate(("portable_desk", "portable_desk", "portable_set", "desk"))]
    v.undoHistory, v.redoHistory = [], []
    v.EnsureObjectIds()
    before = v.CaptureState()
    v.furnishings[0].width += 50
    v.RecordEdit(before)
    data = main.BuildProjectData()
    embedded = data["furnishingDefinitions"]
    assert set(embedded) == {"portable_desk", "portable_set"}
    originalFurnishings = v.furnishings
    v.furnishings = [originalFurnishings[2]]
    compoundOnlyData = main.BuildProjectData(includeHistory = False)
    assert set(compoundOnlyData["furnishingDefinitions"]) == {"portable_set", "portable_desk"}
    assert DecodeProject(compoundOnlyData, localDefinitions)[2][0].definition["components"][0]["definition"]["key"] == "portable_desk"
    v.furnishings = originalFurnishings
    assert len(embedded["portable_set"]["components"]) == 2
    assert all(QtSvg.QSvgRenderer(record["svg"].encode("utf-8")).isValid() for record in embedded.values())
    decoded = DecodeProject(data, localDefinitions)
    assert [obj.definition["key"] for obj in decoded[2]] == [obj.definition["key"] for obj in v.furnishings]
    for original, restored in zip(v.furnishings, decoded[2]):
        assert original.width == restored.width and original.length == restored.length
        if original.definition["isUser"]:
            graphic = original.definition.get("graphicData") or Path(original.definition["imagePath"]).read_bytes()
            assert restored.definition["graphicData"].decode("utf-8") == bytes(graphic).decode("utf-8-sig")
    # Another installation may have a different custom definition with the same key.
    conflicting = dict(localDefinitions)
    conflicting["portable_desk"] = {**definitions["portable_desk"], "width": 9999}
    assert DecodeProject(data, conflicting)[2][0].definition["width"] == 1250
    # A custom asset may later become built-in; its embedded project version
    # still wins, and leaving the project restores the installed version.
    builtInConflict = {**definitions["portable_desk"], "isUser": False, "width": 9999}
    promoted = {**localDefinitions, "portable_desk": builtInConflict}
    promotedDecoded = DecodeProject(data, promoted)
    assert promotedDecoded[2][0].definition["width"] == 1250
    assert promoted["portable_desk"] is builtInConflict and builtInConflict["width"] == 9999
    v.furnishingDefinitions = v.localFurnishingDefinitions = promoted
    main.ApplyProject(promotedDecoded, None)
    assert v.furnishingDefinitions["portable_desk"]["isEmbedded"]
    plain = copy.deepcopy(data)
    plain.pop("furnishingDefinitions")
    plain.pop("history")
    plain["scene"]["objects"] = [plain["scene"]["objects"][0]]
    main.ApplyProject(DecodeProject(plain, promoted), None)
    assert v.furnishingDefinitions["portable_desk"] is builtInConflict
    v.furnishingDefinitions = v.localFurnishingDefinitions = localDefinitions
    # Installing the project is scoped to this scene, not definitions_user.
    v.furnishingDefinitions = localDefinitions
    main.ApplyProject(decoded, None)
    assert v.furnishingRenderers["portable_set"].isValid()
    assert main.BuildProjectData()["furnishingDefinitions"] == embedded
    v.Undo()
    assert v.furnishings[0].width == 1250
    v.Redo()
    assert v.furnishings[0].width == 1300
    compound = v.furnishings[2]
    assert v.DecomposeFurnishings([compound])
    assert len(v.furnishings) == 5 and v.furnishings[2].definition["key"] == "portable_desk"
    v.Undo()
    assert v.furnishings[2] is compound
    bounds = (-2000, -2000, 17000, 5000)
    png = RenderPlan("portable.plan", 30, bounds, projectData = data, applyTheme = False)
    assert not png.isNull()
    svg = RenderPlan("portable.plan", 30, bounds, outputFormat = "svg", projectData = data, applyTheme = False)
    assert QtSvg.QSvgRenderer(svg).isValid()
    installedData = copy.deepcopy(data)
    installedData.pop("furnishingDefinitions")
    with patch("planner_app.catalog.LoadFurnishings", return_value = list(definitions.values())):
        assert RenderPlan("portable.plan", 30, bounds, projectData = installedData, applyTheme = False) == png
        assert RenderPlan("portable.plan", 30, bounds, outputFormat = "svg", projectData = installedData, applyTheme = False) == svg
    # Switching projects removes the embedded catalogue and never leaks it into decoding.
    cleanData = copy.deepcopy(data)
    cleanData.pop("furnishingDefinitions")
    cleanData.pop("history")
    cleanData["scene"]["objects"] = [data["scene"]["objects"][-1]]
    main.ApplyProject(DecodeProject(cleanData, localDefinitions), None)
    assert not v.projectFurnishingDefinitions and "portable_desk" not in v.furnishingDefinitions
    assert "furnishingDefinitions" not in main.BuildProjectData()
    for field, value in (("svg", "<broken"), ("width", -1)):
        invalid = copy.deepcopy(data)
        invalid["furnishingDefinitions"]["portable_desk"][field] = value
        try:
            DecodeProject(invalid, localDefinitions)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid embedded definition was accepted")
    main.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
