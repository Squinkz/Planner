"""Copy membership, transport bounds and duplicate host/group policy without Qt."""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.selection_copy import SelectionCopyObjects, BuildSelectionTransport, OpeningCopyTargets, RemapCopiedGroups
    from planner_app.record_schema import selectionObjectLimit
    wall, otherWall, opening, detached, desk, label = [object() for index in range(6)]
    selected = {id(wall), id(detached), id(desk), id(label)}
    objects, parents = SelectionCopyObjects(selected, [wall, otherWall], [(opening, wall), (detached, otherWall)], [desk], [label])
    assert objects == [wall, opening, detached, desk, label] and parents == {id(wall): 0}
    assert selected == {id(wall), id(detached), id(desk), id(label)}
    records = [dict(type = "Wall"), dict(type = "Door")]
    entries = [(records[0], iter([(-20, 10), (40, 30)])), (records[1], iter([(10, -10)]))]
    indices = {id(wall): 0, id(opening): 1}
    transport = BuildSelectionTransport(iter(entries), indices, [[id(opening), id(wall)], [id(desk)], [id(wall)]])
    assert transport == dict(version = 1, center = [10, 10], objects = records, groups = [[1, 0]])
    assert transport["objects"][0] is records[0]
    duplicate = object()
    copies = {id(wall): duplicate}
    targets = list(OpeningCopyTargets([(opening, wall), (detached, otherWall)], copies, {id(detached)}))
    assert targets == [(opening, duplicate), (detached, otherWall)]
    assert list(OpeningCopyTargets([(opening, wall)], {}, set())) == []
    copies[id(opening)] = object()
    groups = [(wall, opening, desk), (desk, label)]
    assert list(RemapCopiedGroups(groups, copies)) == [(copies[id(wall)], copies[id(opening)])]
    assert groups == [(wall, opening, desk), (desk, label)]
    assert selectionObjectLimit == 10000
    try:
        BuildSelectionTransport([], {}, [])
    except ValueError:
        pass
    else:
        raise AssertionError("empty copy bounds must be rejected")
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: parent/child membership, stable record/group order, one-pass bounds and copied-host precedence without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
