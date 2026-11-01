"""Mixed selections copy valid objects while skipping missing or errored assets."""
import json
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall
from furnishings import Furnishing
from planner_app.viewport.clipboard import clipboardMimeType


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.walls, v.windows, v.labels, v.objectGroups = [], [], [], []
    valid = Furnishing(v.furnishingDefinitions["desk"])
    missing = Furnishing(v.furnishingDefinitions["null"], QtCore.QPointF(2000, 0))
    missing.definitionKey = "Missing Stove"
    v.furnishings = [valid, missing]
    v.EnsureObjectIds()
    v.SetSelection([(valid, None)])
    assert v.CanCopySelection() and v.CopySelection()
    original = bytes(app.clipboard().mimeData().data(clipboardMimeType))
    for entries in ([(missing, None)], [(valid, None), (missing, None)]):
        v.SetSelection(entries)
        before = v.CaptureState()
        history = len(v.undoHistory)
        if len(entries) == 1:
            assert not v.CanCopySelection()
            assert not v.CopySelection() and not v.CutSelection()
        else:
            assert v.CanCopySelection() and v.CopySelection()
            assert len(v.ReadClipboardSelection()["objects"]) == 1
        assert bytes(app.clipboard().mimeData().data(clipboardMimeType)) == original
        assert v.CaptureState() == before and len(v.undoHistory) == history
        assert v.DuplicateSelectionObjects([obj for obj, index in entries], []) == {}
        v.NudgeSelection(QtCore.Qt.Key.Key_Right, duplicate = True)
        assert len(v.furnishings) == 2
        assert {id(obj) for obj, index in v.SelectionEntries()} == {id(obj) for obj, index in entries}
    # Shift rotation is blocked for solo, mixed and structural selections.
    wall = Wall(QtCore.QPointF(-4000, 0), QtCore.QPointF(-3000, 0), 100)
    for entries in ([(missing, None)], [(valid, None), (missing, None)], [(wall, None), (missing, None)]):
        v.walls = [wall] if any(obj is wall for obj, index in entries) else []
        v.SetSelection(entries)
        v.furnishingRotationObject = missing
        box = v.FurnishingSelectionBox() if len(entries) > 1 else missing
        handle = next(handle for handle in v.FurnishingHandles(box) if handle[0] == "rotate")
        center = (box.firstVertex + box.secondVertex) / 2
        offset = v.ViewportToWorld(handle[3]) - center
        end = v.WorldToViewport(center + QtCore.QPointF(-offset.y(), offset.x()))
        v.BeginFurnishingHandleDrag(box, handle, handle[3])
        v.UpdateFurnishingHandleDrag(end, QtCore.Qt.KeyboardModifier.ShiftModifier)
        assert not v.furnishingHandleDrag["copies"] and len(v.furnishings) == 2
        assert len(v.walls) == (1 if any(obj is wall for obj, index in entries) else 0)
        v.CancelInteraction()
    v.walls = []
    v.SetSelection([(missing, None)])
    main.ShowHeaderMenu("Edit")
    assert not main.menuButtons["Copy"].isEnabled() and not main.menuButtons["Cut"].isEnabled()
    main.headerMenus["Edit"].hide()
    # Old clipboard payloads containing unresolved assets are rejected as well.
    payload = json.loads(original)
    payload["objects"][0]["definition"] = "Missing Stove"
    mime = QtCore.QMimeData()
    mime.setData(clipboardMimeType, json.dumps(payload).encode())
    app.clipboard().setMimeData(mime)
    assert v.ReadClipboardSelection() is None
    assert not v.PasteSelection()
    # Compounds with missing children and recovered Null artwork are errors too.
    definition = dict(valid.definition, key = "Broken Compound", components = [
        {"definition": missing.definition, "definitionKey": "Missing Child"}])
    v.furnishingDefinitions["Broken Compound"] = definition
    assert v.FurnishingAssetHasErrors("Broken Compound")
    definition = dict(valid.definition, key = "Damaged SVG", graphicData = Path(missing.definition["imagePath"]).read_bytes())
    v.furnishingDefinitions["Damaged SVG"] = definition
    assert v.FurnishingAssetHasErrors("Damaged SVG")
    assert v.FurnishingAssetHasErrors("null")
    damaged = Furnishing(v.furnishingDefinitions["Damaged SVG"], QtCore.QPointF(4000, 0))
    v.furnishings.append(damaged)
    v.objectGroups = [(valid, missing, damaged)]
    v.EnsureObjectIds()
    v.SetSelection([(valid, None)])
    before = v.CaptureState()
    history = len(v.undoHistory)
    assert len(v.SelectionEntries()) == 3 and v.CanCopySelection()
    assert v.CopySelection()
    payload = v.ReadClipboardSelection()
    assert [record["definition"] for record in payload["objects"]] == ["desk"]
    assert payload["groups"] == []
    assert v.CaptureState() == before and len(v.undoHistory) == history
    main.ShowHeaderMenu("Edit")
    assert main.menuButtons["Copy"].isEnabled() and main.menuButtons["Cut"].isEnabled()
    main.headerMenus["Edit"].hide()
    assert v.CutSelection()
    assert v.furnishings == [missing, damaged], "Cut deleted skipped error objects"
    assert len(v.undoHistory) == history + 1
    v.Undo()
    assert v.CaptureState() == before
    v.Redo()
    assert v.furnishings == [missing, damaged]
    v.Undo()
    v.objectGroups = []
    v.SetSelection([(valid, None)])
    assert v.CopySelection() and v.ReadClipboardSelection() is not None
    del v.furnishingDefinitions["Broken Compound"]
    del v.furnishingDefinitions["Damaged SVG"]
    app.clipboard().clear()
    main.projectDirty = False
    main.close()


if __name__ == "__main__":
    Main()
