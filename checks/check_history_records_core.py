"""History record policy and replay without Qt, live models or image decoding."""
import copy
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.edit_transactions import ValidateSceneMemberships
    from planner_app.history_records import (ReadHistoryMembership, ReadHistoryOrders, ReadReferenceHistory,
                                             ApplyReferenceChanges, historyLimit, historyByteBudget)
    assert historyLimit == 200 and historyByteBudget == 16 * 1024 * 1024
    known = {1, 2, 3, 4}
    changes = [[[0, [1, 2]]], [[1, [2, 3]]]]
    before = copy.deepcopy(changes)
    assert ReadHistoryMembership(changes, known, groups = True) == (((0, (1, 2)),), ((1, (2, 3)),))
    assert changes == before
    assert ReadHistoryMembership([[[0, 3]], [[1, 2]]], known) == (((0, 3),), ((1, 2),))
    for invalid in ([], [None, []], [[[True, [1, 2]]], []], [[[0, [1]]], []],
                    [[[0, [1, 1]]], []], [[[0, [1, 99]]], []], [[[0, [1, 2]], [1, [1, 2]]], []]):
        try:
            ReadHistoryMembership(invalid, known, groups = True)
        except ValueError:
            pass
        else:
            raise AssertionError(invalid)
    assert ReadHistoryOrders({"0": [[1, 2], [2, 1]], "5": [[], []]}, known, (0, 3, 5, 8)) == {0: ((1, 2), (2, 1)), 5: ((), ())}
    for invalid in ({"2": [[], []]}, {"0": [[1], [99]]}, {"0": [[1, 1], [2]]}, {"0": [[True], [2]]}):
        try:
            ReadHistoryOrders(invalid, known, (0, 3, 5, 8))
        except ValueError:
            pass
        else:
            raise AssertionError(invalid)

    ValidateSceneMemberships(known, {1}, (1,), ((1, 2),), (3,))
    for parents, groups, hidden in (((2,), (), ()), ((), ((1,),), ()), ((), ((1, 1),), ()),
                                     ((), ((1, 99),), ()), ((), ((1, 2), (2, 3)), ()),
                                     ((), (), (3, 3)), ((), (), (99,))):
        try:
            ValidateSceneMemberships(known, {1}, parents, groups, hidden)
        except ValueError:
            pass
        else:
            raise AssertionError((parents, groups, hidden))

    record = dict(center = [1, 2], width = 100, height = 50, data = "first", visible = False)
    delta = dict(center = [[1, 2], [3, 4]], width = [100, 200], data = ["first", "second"])
    edit = dict(changes = [], orders = {}, groups = [[], []], hidden = [[], []],
                referenceImage = dict(changes = delta, pivots = [None, [10, 20]]))
    original = copy.deepcopy((record, edit))
    changes, pivots = ReadReferenceHistory(edit)
    assert changes == delta and pivots == (None, (10, 20))
    after = ApplyReferenceChanges(record, changes, True, validate = True)
    assert after["center"] == [3, 4] and after["width"] == 200 and after["data"] == "second"
    assert after["visible"] is False and after["height"] == 50
    assert ApplyReferenceChanges(after, changes, False, validate = True) == record
    after["center"][0] = 99
    assert (record, edit) == original
    for badRecord in (None, dict(record, width = 101), dict(record, data = "mismatch")):
        try:
            ApplyReferenceChanges(badRecord, changes, True, validate = True)
        except ValueError:
            pass
        else:
            raise AssertionError(badRecord)
    for replacement in (dict(changes = {"visible": [False, True]}, pivots = [None, None]),
                        dict(changes = {"width": [100]}, pivots = [None, None]),
                        dict(changes = {}, pivots = [None, [True, 0]]),
                        dict(changes = {}, pivots = [None, [float("inf"), 0]])):
        try:
            ReadReferenceHistory(dict(edit, referenceImage = replacement))
        except ValueError:
            pass
        else:
            raise AssertionError(replacement)
    from planner_app.history_records import HistoryEntryFields, ValidateHistoryHeader, PlanHistoryVariants
    wallRecord = dict(type = "Wall", id = 1, first = [0, 0], second = [100, 0], width = 100)
    openingRecord = dict(type = "Door", id = 2, parent = 1, center = .5, length = 20)
    history = dict(format = "Planner Changes", version = 1, undo = [dict(changes = [dict(category = 3, before = None, after = [0, openingRecord])], groups = [[], []], hidden = [[], []], orders = {})], redo = [])
    assert ValidateHistoryHeader(history) and not ValidateHistoryHeader(None)
    variants, records = PlanHistoryVariants(history, {1: "Wall"}, lambda key: wallRecord)
    assert len(variants) == 2 and records[0]["parent"] == 1 and records[1]["type"] == "Wall"
    entry = (None, (1, 2), (3, 4), 5, "Room", .5, "Adaptive Metric", False)
    assert HistoryEntryFields(8, entry, "RoomLabel")["unitsOverride"] == "Adaptive Metric"
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: history memberships, ordering, reference schemas and reversible deltas without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
