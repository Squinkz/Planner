"""Selection/group/hiding rules use opaque identities without Qt or models."""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.selection_policy import (ExpandSelectionGroups, FilterObjectGroups, PlanGroupSelection,
                                              PlanUngroupSelection, PlanHideSelection, PlanHideUnselected)
    class EqualValue:
        def __eq__(self, other):
            return True
    a, b, c, d = (EqualValue() for index in range(4))
    groups = [(a, b, c)]
    sceneIds = {id(a), id(b), id(c), id(d)}
    expanded = ExpandSelectionGroups([(b, None), (a, None)], groups, sceneIds, True)
    assert [id(obj) for obj, index in expanded] == [id(a), id(c), id(b)]
    assert ExpandSelectionGroups([(b, 0)], groups, sceneIds, True)[0][0] is b
    expanded = ExpandSelectionGroups([(b, None)], groups, {id(a), id(b)}, True)
    assert [id(obj) for obj, index in expanded] == [id(a), id(b)]

    def UnusedScene():
        raise AssertionError("Unneeded scene traversal")
        yield None

    assert len(ExpandSelectionGroups([(a, None), (a, None)], groups, UnusedScene(), False)) == 1
    assert len(ExpandSelectionGroups([(a, None)], [], UnusedScene(), True)) == 1
    assert FilterObjectGroups([], UnusedScene()) == []
    filtered = FilterObjectGroups(groups, {id(a), id(c)})
    assert [id(obj) for obj in filtered[0]] == [id(a), id(c)]
    assert FilterObjectGroups(groups, {id(a), id(b)}, keep = False) == []
    proposal = PlanGroupSelection([(b, None), (d, 0), (b, 1)], groups)
    assert [[id(obj) for obj in group] for group in proposal[0]] == [[id(a), id(c)], [id(b), id(d)]]
    assert [id(obj) for obj in proposal[1]] == [id(b), id(d)]
    assert PlanGroupSelection([(a, 0), (a, 1)], groups) is None
    assert PlanGroupSelection([(c, None), (b, None), (a, None)], groups) is None
    assert [id(obj) for obj in PlanUngroupSelection([(b, None)], groups)[0]] == [id(a), id(c)]
    assert PlanUngroupSelection([(d, None)], groups) is None
    assert [id(obj) for obj in groups[0]] == [id(a), id(b), id(c)]

    hidden = [d, b]
    proposal = PlanHideSelection([(a, None)], hidden, [(c, a), (b, d)])
    assert [id(obj) for obj in proposal[0]] == [id(d), id(b), id(a), id(c)]
    assert proposal[1] == sceneIds
    assert [id(obj) for obj in hidden] == [id(d), id(b)]
    assert PlanHideSelection([], hidden, UnusedScene()) is None
    proposal = PlanHideUnselected([(c, None)], iter((a, b, c, d)), set())
    assert [id(obj) for obj in proposal[0]] == [id(a), id(b), id(d)]
    assert proposal[1] == {id(a), id(b), id(d)}
    assert PlanHideUnselected([(c, None)], (a, b, c, d), proposal[1]) is None
    assert PlanHideUnselected([], UnusedScene(), set()) is None
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: selection ordering, identities, control vertices, group plans and visibility proposals without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore
    from fixtures.parity_examples import ExampleWindow, InstallScene
    from planner_app.models import Wall, Door
    with ExampleWindow() as (main, folder):
        v = main.viewport
        p = QtCore.QPointF
        a = Wall(p(-2000, 0), p(2000, 0), 120)
        b = Wall(p(0, 2000), p(2000, 2000), 120)
        c = Wall(p(0, 4000), p(2000, 4000), 120)
        door = Door(a, .2, .4)
        stale = Wall(p(0, 6000), p(2000, 6000), 120)
        InstallScene(main, [a, b, c, door])
        v.groupModeEnabled = True
        v.objectGroups = [(a, b, door, stale)]
        v.hiddenObjects, v.hiddenObjectIds = [b], {id(b)}
        expanded = v.ExpandGroupedSelection([(a, None), (c, 0)])
        assert [(id(obj), index) for obj, index in expanded] == [(id(door), None), (id(a), None), (id(c), 0)]
        v.PruneObjectGroups()
        assert [id(obj) for obj in v.objectGroups[0]] == [id(a), id(b), id(door)]
        v.hiddenObjects, v.hiddenObjectIds = [a, b], {id(a), id(b)}
        expanded = v.ExpandGroupedSelection([(a, None)])
        assert [(id(obj), index) for obj, index in expanded] == [(id(door), None)]
        main.MarkProjectClean()


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
