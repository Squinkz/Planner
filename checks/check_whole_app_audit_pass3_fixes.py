"""Portable decomposition and host-direction-aware opening clipboard records."""
import copy
import json
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.catalog import LoadFurnishings
from planner_app.models import Wall, Fireplace, Furnishing
from planner_app.object_schema import openingFields
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan
from planner_app.viewport.clipboard import clipboardMimeType


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.snapEnabled = v.connectedEnabled = False
        for cls, fields in openingFields.items():
            for reverse in (False, True):
                wall = Wall(p(-3000, 0), p(3000, 0), 120)
                opening = cls(wall, .4, .6)
                opening.measurementFlipped = True
                for flag in ("hingeAtSecond", "swingsOutwards", "panelsFlipped"):
                    if flag in fields:
                        setattr(opening, flag, True)
                if cls is Fireplace:
                    opening.depth, opening.depthOffset = 600, 150
                InstallScene(main, [wall, opening])
                v.SetSelection([(opening, None)])
                assert v.CopySelection()
                old = {field: getattr(opening, field) for field in fields}
                target = Wall(p(3000, 0), p(-3000, 0), 120) if reverse else Wall(p(-3000, 0), p(3000, 0), 120)
                InstallScene(main, [target])
                assert v.PasteSelection(inPlace = True), cls
                pasted = v.windows[0]
                for field, value in old.items():
                    expected = not value if reverse and field in ("hingeAtSecond", "swingsOutwards", "panelsFlipped") else -value if reverse and field == "depthOffset" else value
                    assert getattr(pasted, field) == expected, (cls, field)
                DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)
                v.Undo()
                assert not v.windows
                v.Redo()
                assert v.windows[0] is pasted

        # Rotated hosts use the same tangent comparison; parent-included paste
        # retains its copied host's orientation without a second rebase.
        wall = Wall(p(0, -3000), p(0, 3000), 120)
        opening = Fireplace(wall, .4, .6)
        opening.depth, opening.depthOffset = 600, 150
        InstallScene(main, [wall, opening])
        v.SetSelection([(opening, None)])
        assert v.CopySelection()
        payload = v.ReadClipboardSelection()
        InstallScene(main, [Wall(p(0, 3000), p(0, -3000), 120)])
        assert v.PasteSelection(inPlace = True) and v.windows[0].depthOffset == -150
        for invalid in ([0, 0], [1, float("nan")], [True, 0], [1, 0, 0]):
            data = copy.deepcopy(payload)
            data["objects"][0]["wallDirection"] = invalid
            assert v.ReadClipboardSelection(json.dumps(data).encode()) is None
        # Older records have no direction, so their flags retain old semantics.
        payload["objects"][0].pop("wallDirection")
        mime = QtCore.QMimeData()
        mime.setData(clipboardMimeType, json.dumps(payload).encode())
        QtWidgets.QApplication.clipboard().setMimeData(mime)
        InstallScene(main, [Wall(p(0, 3000), p(0, -3000), 120)])
        assert v.PasteSelection(inPlace = True) and v.windows[0].depthOffset == 150
        v.SetSelection([(v.walls[0], None)])
        assert v.CopySelection()
        InstallScene(main, [])
        assert v.PasteSelection(inPlace = True) and v.windows[0].depthOffset == 150

        local = dict(v.furnishingDefinitions)
        definitions = {item["key"]: item for item in LoadFurnishings(definitionOverrides = {
            "audit_inner": {"name": "Inner", "children": [{"furnishing": "desk"}]},
            "audit_root": {"name": "Root", "children": [{"furnishing": "audit_inner"}]}})}
        private = dict(local["desk"], width = 1234, isUser = True)
        private["graphicData"] = Path(private["imagePath"]).read_bytes()
        definitions["audit_inner"]["components"][0]["definition"] = private
        root = definitions["audit_root"]
        v.furnishingDefinitions = {**local, "audit_root": root}
        main.RefreshFurnishingRenderers()
        parent = Furnishing(root, p(2500, 1000))
        neighbor = Furnishing(local["desk"], p(-2500, 0))
        InstallScene(main, [parent, neighbor])
        assert v.DecomposeFurnishings([parent])
        inner = v.furnishings[0]
        assert inner.definition["key"] in v.furnishingRenderers
        assert v.furnishingDefinitions["desk"] is local["desk"] and neighbor.definition is local["desk"]
        assert v.DecomposeFurnishings([inner])
        leaf = v.furnishings[0]
        assert leaf.definition["key"] != "desk" and leaf.definition["width"] == 1234
        assert leaf.definition is v.furnishingDefinitions[leaf.definitionKey]
        assert leaf.definition["key"] in v.furnishingRenderers
        v.grab()
        importedKeys = set(v.projectFurnishingDefinitions)
        v.Undo()
        v.Undo()
        assert v.furnishings[0] is parent
        v.grab()
        assert v.DecomposeFurnishings([parent])
        assert set(v.projectFurnishingDefinitions) == importedKeys
        assert v.DecomposeFurnishings([v.furnishings[0]])
        path = folder / "decomposed.plan"
        assert main.SaveProject(path) and main.OpenProject(path)
        assert v.furnishings[0].definition["width"] == 1234
        assert v.furnishings[1].definition["width"] == local["desk"]["width"]
        v.Undo()
        v.Undo()
        v.grab()
        v.Redo()
        v.Redo()
        v.grab()
        assert v.furnishings[0].definition["width"] == 1234
        v.SetSelection([(v.furnishings[0], None)])
        assert v.CopySelection()
        data = main.BuildProjectData(includeHistory = False)
        assert not RenderPlan("decomposed.plan", 20, (-5000, -3000, 10000, 6000), projectData = data, applyTheme = False).isNull()
        assert b"<svg" in RenderPlan("decomposed.plan", 20, (-5000, -3000, 10000, 6000),
                                    projectData = data, applyTheme = False, outputFormat = "svg")
        InstallScene(main, [])
        QtWidgets.QApplication.clipboard().clear()
        main.MarkProjectClean()


if __name__ == "__main__":
    Main()
