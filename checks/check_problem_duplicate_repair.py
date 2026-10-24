"""Coincident repair is shared across scene types and preserves unique wall children."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene, CreateObject, objectTypes
from planner_app.models import Wall, Window, Door, PocketDoor
from planner_app.scene_problems import FindSceneProblems, RepairCoincidentObjects
from check_scene_problems import SelectIssue


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        p = QtCore.QPointF
        for name in objectTypes:
            first = CreateObject(v, name)
            if isinstance(first, Window):
                second = v.CloneOpening(first, first.parentWall)
                objects = [first.parentWall, first, second]
            else:
                second = CreateObject(v, name)
                objects = [first, second]
            InstallScene(main, objects)
            issues = [issue for issue in FindSceneProblems(v, includePotential = False)
                      if issue["object"] is second and issue.get("repairKind") == "duplicates"]
            assert len(issues) == 1, name
            before = v.CaptureState()
            assert RepairCoincidentObjects(v, issues), name
            assert len(v.undoHistory) == 1
            assert id(second) not in {id(obj) for obj in v.walls + v.windows + v.furnishings + v.labels}, name
            assert id(first) in {id(obj) for obj in v.walls + v.windows + v.furnishings + v.labels}, name
            v.Undo()
            assert v.CaptureState() == before, name
            v.Redo()
            assert not v.CoincidentObjectGroups(includeHidden = True), name

        first, second = [Wall(p(-3000, 0), p(3000, 0), 240) for repeat in range(2)]
        kept = Door(first, .15, .3)
        copy = Door(second, .15, .3)
        unique = Window(second, .65, .8)
        unrelated = CreateObject(v, "Furnishing")
        InstallScene(main, [first, second, kept, copy, unique, unrelated])
        v.objectGroups = [(second, unrelated)]
        v.groupModeEnabled = v.connectedObjectsEnabled = True
        before = v.CaptureState()
        main.ShowProblems()
        window = main.problemsWindow
        issue = next(issue for issue in window.problems if issue["object"] is second and issue.get("repairKind") == "duplicates")
        SelectIssue(window, second, issue["code"])
        assert window.repairButton.isEnabled()
        window.repairButton.click()
        assert len(v.walls) == 1 and v.walls[0] is first
        assert len(v.windows) == 2 and unique.parentWall is first
        assert kept in v.windows and all(obj is not copy for obj in v.windows)
        assert unrelated in v.furnishings and len(v.undoHistory) == 1
        v.Undo()
        assert unique.parentWall is second and v.CaptureState() == before
        window.close()

        parent = Wall(p(0, -4000), p(0, 4000), 240)
        tiny = PocketDoor(parent, .499, .501)
        tiny.length = 1.0000000000000133
        InstallScene(main, [parent, tiny])
        center = v.WorldToViewport((tiny.firstVertex + tiny.secondVertex) / 2)
        v.SetSelection([(parent, None)])
        assert v.HitTest(center + p(3, 0)) == (tiny, None), "Tiny door is not selectable through its parent wall"
        v.SetSelection([(tiny, None)])
        assert v.HitTest(v.WorldToViewport(tiny.firstVertex)) == (tiny, 0), "Expanded hit area intercepted the resize handle"
        issue = next(issue for issue in FindSceneProblems(v) if issue["object"] is tiny and issue["code"] == "potential:minimum-opening")
        assert issue["potential"] and "1 mm" in issue["description"]
        for openingType in (Window, Door, PocketDoor):
            opening = openingType(parent, .499, .501)
            InstallScene(main, [parent, opening])
            for length in (1, 5, 10, 10.00000000000001, 10.01, 11):
                opening.length = length
                issues = [issue for issue in FindSceneProblems(v) if issue["object"] is opening
                          and issue["code"] == "potential:minimum-opening"]
                assert bool(issues) == (length <= 10.000001), (openingType, length, issues)
        InstallScene(main, [parent, tiny])
        tiny.length = 0
        v.SetSelection([])
        assert v.HitTest(center) == (tiny, None), "A truly collapsed opening has no hit area"
    print("Duplicate repairs: all scene types, undo/redo, preserved wall children/groups and selectable minimum-length doors passed")


if __name__ == "__main__":
    Main()
