"""Regression cases for project rollback, portable cuts, paint bounds and rebasing."""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.catalog import LoadFurnishings
from planner_app.models import Wall, Door, DoubleDoor, SwingingDoor, SilledWindow, Arrow, Fireplace, Label, RoomLabel, Furnishing
from planner_app.project_codec import DecodeProject
from planner_app.geometry_recovery import GeometryLoadCancelled
from planner_app.export_bounds import AutomaticBounds
from planner_app.graphics.symbols import DrawOpeningSymbol
from planner_app.graphics.arrows import ArrowPaths
from planner_app.geometry.opening_placement import BlockedOpeningIntervals


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        main.show()
        v, panel = main.viewport, main.exportPanel
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetOverride("roomStyle", "Canvas")
        panel.SetOverride("solidRooms", True)
        panel.UndoExport()
        main.MarkProjectClean()
        expected = panel.ExportHistoryState()
        journals = [tuple(map(id, stack)) for stack in (panel.exportUndoHistory, panel.exportRedoHistory)]
        links = dict(main.activityLog.exportLinks)
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Discard):
            assert not main.OpenProject(folder / "missing.plan")
            assert panel.ExportHistoryState() == expected
            assert [tuple(map(id, stack)) for stack in (panel.exportUndoHistory, panel.exportRedoHistory)] == journals
            assert main.activityLog.exportLinks == links
            cancelled = folder / "cancelled.plan"
            cancelled.write_text("{}", encoding = "utf-8")
            with patch("planner_app.project_recovery.RecoverProject", side_effect = GeometryLoadCancelled):
                assert not main.OpenProject(cancelled)
            assert panel.ExportHistoryState() == expected
            assert main.activityLog.exportLinks == links
            with patch.object(main, "LoadStartupProject", return_value = False):
                assert not main.NewProject()
            assert panel.ExportHistoryState() == expected
            assert [tuple(map(id, stack)) for stack in (panel.exportUndoHistory, panel.exportRedoHistory)] == journals
        panel.RedoExport()
        assert panel.overrides["solidRooms"]
        panel.UndoExport()
        assert panel.ExportHistoryState() == expected
        main.sidebarTabs.setCurrentIndex(0)

        for cls in (Label, RoomLabel):
            label = cls(text = "Small")
            label.SetPointSize(.05)
            InstallScene(main, [label])
            DecodeProject(main.BuildProjectData(includeHistory = False), v.furnishingDefinitions)
            v.SetSelection([(label, None)])
            assert label.length < 1 and v.CutSelection() and not v.labels
            assert v.ReadClipboardSelection() is not None and v.PasteSelection(inPlace = True)
            assert len(v.labels) == 1 and type(v.labels[0]) is cls
            assert abs(v.labels[0].length - label.length) < 1e-8
            v.Undo()
            v.Undo()
            assert v.labels == [label]
        clipboard = bytes(QtWidgets.QApplication.clipboard().mimeData().data("application/x-planner-selection"))
        v.SetSelection([])
        walls = [Wall(p(index * 10, 0), p(index * 10 + 5, 0), 120) for index in range(10001)]
        v.walls, v.labels = walls, []
        with patch.object(v, "SelectionEntries", return_value = [(wall, None) for wall in walls]):
            assert not v.CutSelection()
        assert len(v.walls) == 10001
        assert bytes(QtWidgets.QApplication.clipboard().mimeData().data("application/x-planner-selection")) == clipboard
        InstallScene(main, [])

        local = dict(v.localFurnishingDefinitions)
        source = {item["key"]: item for item in LoadFurnishings(definitionOverrides = {
            "audit_leaf": {"inherits": "desk", "name": "Audit Leaf", "width": 1250},
            "audit_parent": {"name": "Audit Parent", "children": [
                {"furnishing": "audit_leaf", "x": -900}, {"furnishing": "chair_dining", "x": 900}]}})}
        v.furnishingDefinitions = source
        v.projectFurnishingDefinitions = {key: definition for key, definition in source.items() if definition.get("isUser")}
        main.RefreshFurnishingRenderers()
        InstallScene(main, [Furnishing(source["audit_parent"], p())])
        portable = main.BuildProjectData(includeHistory = False)
        main.ApplyProject(DecodeProject(portable, local), None)
        v.SetSelection([(v.furnishings[0], None)])
        assert v.CopySelection()
        data = bytes(QtWidgets.QApplication.clipboard().mimeData().data("application/x-planner-selection"))
        main.MarkProjectClean()
        assert main.CloseProject()
        assert "audit_parent" not in v.furnishingDefinitions
        assert v.PasteSelection(inPlace = True)
        assert v.furnishings[0].definition["key"] == "audit_parent"
        assert v.furnishings[0].definition["components"][1]["definition"] is local["chair_dining"]
        main.MarkProjectClean()
        assert main.CloseProject()

        # A conflicting child forces the matching parent to receive a new key,
        # without changing any existing destination object or definition.
        destinationLeaf = dict(source["audit_leaf"], name = "Destination Leaf", width = 1800)
        destinationParent = copy.deepcopy(source["audit_parent"])
        destinationParent["components"][0]["definition"] = destinationLeaf
        v.projectFurnishingDefinitions = {"audit_leaf": destinationLeaf, "audit_parent": destinationParent}
        v.furnishingDefinitions = {**local, **v.projectFurnishingDefinitions}
        main.RefreshFurnishingRenderers()
        existing = Furnishing(destinationLeaf, p(10000, 0))
        InstallScene(main, [existing])
        assert v.PasteSelection(inPlace = True)
        pasted = v.furnishings[-1]
        key = pasted.definition["key"]
        assert key != "audit_parent" and pasted.definition["components"][0]["definition"]["key"] != "audit_leaf"
        assert v.furnishingDefinitions["audit_leaf"] is destinationLeaf and existing.definition is destinationLeaf
        assert v.furnishingDefinitions["audit_parent"] is destinationParent
        definitionsBefore = dict(v.projectFurnishingDefinitions)
        assert v.PasteSelection(inPlace = True)
        assert v.furnishings[-1].definition is pasted.definition
        assert v.projectFurnishingDefinitions == definitionsBefore
        v.Undo()
        v.Undo()
        assert v.furnishings == [existing]
        v.Redo()
        assert v.furnishings[-1] is pasted
        reopened = DecodeProject(main.BuildProjectData(), local)
        assert reopened[2][0].definition["name"] == "Destination Leaf"
        assert reopened[2][-1].definition["components"][0]["definition"]["name"] == "Audit Leaf"

        main.MarkProjectClean()
        assert main.CloseProject()
        wall = Wall(p(-4000, 0), p(4000, 0), 120)
        InstallScene(main, [wall])
        definitionsBefore = dict(v.furnishingDefinitions)
        assert not v.PasteSelection(inPlace = True), "A blocked paste unexpectedly succeeded"
        assert v.furnishingDefinitions == definitionsBefore and not v.projectFurnishingDefinitions
        assert v.walls == [wall] and not v.furnishings
        # Invalid portable SVG must be rejected before any catalog/scene changes.
        import json
        bad = json.loads(data)
        bad["furnishingDefinitions"]["audit_leaf"]["svg"] = "<invalid/>"
        assert v.ReadClipboardSelection(json.dumps(bad).encode()) is None
        QtWidgets.QApplication.clipboard().clear()

        for cls in (Door, DoubleDoor, SwingingDoor, SilledWindow):
            for reversedWall in (False, True):
                for facing in (False, True):
                    wall = Wall(p(5000, 0) if reversedWall else p(-5000, 0), p(-5000, 0) if reversedWall else p(5000, 0), 120)
                    opening = cls(wall, .2, .8)
                    if hasattr(opening, "swingsOutwards"):
                        opening.swingsOutwards = facing
                    if cls is SilledWindow:
                        opening.sillDepth = 2500
                    InstallScene(main, [wall, opening])
                    crop = QtCore.QRectF(*AutomaticBounds(v))
                    picture = QtGui.QPicture()
                    first, second = opening.firstVertex, opening.secondVertex
                    with QtGui.QPainter(picture) as painter:
                        DrawOpeningSymbol(painter, p(first.x(), -first.y()), p(second.x(), -second.y()), opening.width, cls,
                                          swingsOutwards = facing, sillDepth = getattr(opening, "sillDepth", 40), pixelsPerMillimeter = 1)
                    paint = picture.boundingRect()
                    world = QtCore.QRectF(p(paint.left(), -paint.bottom()), p(paint.right(), -paint.top())).normalized()
                    assert crop.contains(world), (cls, reversedWall, facing, crop, world)
        for solid in (False, True):
            arrow = Arrow(p(), p(6000, 0), 20)
            arrow.tipSize, arrow.solidTip = 4000, solid
            InstallScene(main, [arrow])
            crop = QtCore.QRectF(*AutomaticBounds(v))
            for path in ArrowPaths(arrow.firstVertex, arrow.secondVertex, arrow.width, solid, arrow.tipSize, 1):
                assert path.isEmpty() or crop.contains(path.boundingRect())

        for reversedHost in (False, True):
            left = Wall(p(-2000, 0), p(), 120)
            right = Wall(p(2000, 0), p(), 120) if reversedHost else Wall(p(), p(2000, 0), 120)
            fireplace = Fireplace(right, .25, .75)
            fireplace.depth, fireplace.depthOffset = 500, 80
            InstallScene(main, [left, right, fireplace])
            center = v.ObjectFootprint(fireplace)[0].center()
            assert v.DissolveWalls(p())
            assert QtCore.QLineF(center, v.ObjectFootprint(fireplace)[0].center()).length() < 1e-8
            for action in (v.Undo, v.Redo):
                action()
                assert QtCore.QLineF(center, v.ObjectFootprint(fireplace)[0].center()).length() < 1e-8

        for offset in (0, 1e9, 1e11, -1e11, 9e11):
            parent = [(offset, offset - 60), (offset + 4000, offset - 60), (offset + 4000, offset + 60), (offset, offset + 60)]
            obstacle = [(offset + 1500, offset - 120), (offset + 2500, offset - 120), (offset + 2500, offset + 120), (offset + 1500, offset + 120)]
            for corners in (parent, parent[::-1]):
                assert BlockedOpeningIntervals(corners, (offset, offset), (4000, 0), 16000000, [obstacle]) == [(.375, .625)]
        main.MarkProjectClean()
    print("PASS: rollback journals, safe portable cuts, definition conflicts, atomic paste, paint bounds, fireplace rebasing and coordinate invariance")


if __name__ == "__main__":
    Main()
