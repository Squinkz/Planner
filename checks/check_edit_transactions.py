"""Sparse edit extraction preserves record identity, errors, bytes and no-op rules."""
import os
from pathlib import Path
import random
import subprocess
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))


def CheckWithoutQt():
    from planner_app.edit_transactions import SparseSceneEdit
    class Edit(SparseSceneEdit):
        def ValidateState(self, state):
            members = {id(entry[0]) for category in (0, 3, 5, 8) for entry in state[category]}
            assert all(id(obj) in members for obj in state[7])
            assert all(len(group) >= 2 and all(id(obj) in members for obj in group) for group in state[6])
    rng = random.Random(14259)
    for case in range(600):
        objects = [object() for i in range(20)]
        records = [(obj, index, index * .1) for index, obj in enumerate(objects)]
        before = (tuple(records[:8]), objects[0], None, (), (), tuple(records[8:15]), (), (), tuple(records[15:]))
        after = list(before)
        for category in (0, 5, 8):
            entries = list(before[category])
            rng.shuffle(entries)
            if case % 3 == 0: entries.pop()
            entries[0] = (entries[0][0], case, case * .2)
            if case % 4 == 0: entries.append((object(), 99, .3))
            after[category] = tuple(entries)
        members = [entry[0] for category in (0, 5, 8) for entry in after[category]]
        after[1], after[4] = members[-1], ((members[-1], None),)
        after[6], after[7] = ((members[0], members[-1]),), (members[1],)
        after = tuple(after)
        edit = Edit.Between(before, after)
        assert edit.Apply(before, True, validate = True) == after
        assert edit.Apply(after, False, validate = True) == before
        assert Edit.Between(before, before) is None
        selectionOnly = list(before);selectionOnly[1] = None
        assert Edit.Between(before, tuple(selectionOnly)) is None
    assert not any(name.startswith(("PySide", "PyQt")) for name in sys.modules)
    print("PASS: 600 headless sparse edits, reverse replay, ordering, memberships and selection-only no-ops")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"], capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtWidgets
    from planner_app.models import Wall, Door, Fireplace, Furnishing, Label
    from planner_app.viewport.widget import DrawingViewport
    from planner_app.history_edits import SceneEdit
    from fixtures.qt_edit_transactions_reference_20261017 import SceneEdit as FrozenEdit
    app = QtWidgets.QApplication([])
    p = QtCore.QPointF
    view = DrawingViewport()
    rng = random.Random(14259)
    comparisons = 0
    for case in range(160):
        view.CancelInteraction()
        view.objectGroups, view.hiddenObjects = [], []
        view.hiddenObjectIds = set()
        view.walls = [Wall(p(i * 3000, 0), p(i * 3000 + 2000, 0), 240) for i in range(8)]
        # Equal-by-value walls must remain distinct attachment identities.
        view.walls[1].firstVertex, view.walls[1].secondVertex = p(view.walls[0].firstVertex), p(view.walls[0].secondVertex)
        view.windows = [Door(view.walls[0], .2, .4), Fireplace(view.walls[2], .2, .6)]
        view.furnishings = [Furnishing({"key": "test", "name": "Test", "width": 500, "length": 600}, p(i * 1000, 3000)) for i in range(4)]
        view.labels = [Label(p(0, 5000), "Edit")]
        view.SetSelection([(view.walls[0], None)])
        before = view.CaptureState()
        view.walls[0].width += case % 7
        view.windows[0].parentWall = view.walls[1]
        view.furnishings[0].firstVertex.setX(view.furnishings[0].firstVertex.x() + (1e-13 if case % 2 else 7))
        view.labels[0].text = str(case)
        if case % 3 == 0: view.walls.reverse()
        if case % 4 == 0: view.walls.pop(-1)
        if case % 5 == 0: view.walls.append(Wall(p(-4000, 2000), p(-2000, 2000)))
        view.objectGroups = [(view.walls[0], view.furnishings[0])]
        view.hiddenObjects = [view.furnishings[-1]]
        view.SetSelection([(view.furnishings[0], None)])
        after = view.CaptureState()
        edits = [cls.Between(before, after) for cls in (SceneEdit, FrozenEdit)]
        actual, frozen = edits
        assert (actual.changes, actual.groups, actual.hidden, actual.orders, actual.selection) == (frozen.changes, frozen.groups, frozen.hidden, frozen.orders, frozen.selection)
        assert actual.byteSize == frozen.byteSize
        assert sys.getsizeof(actual) == sys.getsizeof(frozen)
        assert actual.Apply(before, True, validate = True) == frozen.Apply(before, True, validate = True) == after
        assert actual.Apply(after, False, validate = True) == frozen.Apply(after, False, validate = True) == before
        for state, forward in [(after, True), (before, False)]:
            errors = []
            for edit in edits:
                try: edit.Apply(state, forward, validate = True)
                except Exception as error: errors.append((type(error), str(error)))
                else: errors.append(None)
            assert errors[0] == errors[1], (case, errors)
        comparisons += 1
    # Final model validation remains mandatory in the desktop adapter.
    for index, invalid in [(6, ((view.walls[0], view.walls[0]),)), (7, (object(),))]:
        broken = list(after);broken[index] = invalid
        errors = []
        for cls in (SceneEdit, FrozenEdit):
            edit = cls([], ((), ()), ((), ()), {})
            try: edit.Apply(tuple(broken), True, validate = True)
            except Exception as error: errors.append((type(error), str(error)))
        assert len(errors) == 2 and errors[0] == errors[1]
    broken = list(after)
    badOpening = list(after[3][0]);badOpening[1] = object()
    broken[3] = (tuple(badOpening), *after[3][1:])
    errors = []
    for cls in (SceneEdit, FrozenEdit):
        edit = cls([], ((), ()), ((), ()), {})
        try: edit.Apply(tuple(broken), True, validate = True)
        except Exception as error: errors.append((type(error), str(error)))
    assert len(errors) == 2 and errors[0] == errors[1] == (ValueError, "History opening has no parent wall.")
    # Keep the desktop point provider's equality; numeric tuple conversion would
    # incorrectly make this small difference into a new furnishing edit.
    pointBefore = p(1e8, 1000)
    pointAfter = p(1e8 + 1e-7, 1000)
    assert pointBefore == pointAfter
    base = list(before)
    entry = before[5][0]
    base[5] = ((entry[0], pointBefore, *entry[2:]), *before[5][1:])
    changed = list(base)
    changed[5] = ((entry[0], pointAfter, *entry[2:]), *before[5][1:])
    assert SceneEdit.Between(tuple(base), tuple(changed)) is None
    assert FrozenEdit.Between(tuple(base), tuple(changed)) is None
    view.close()
    print(f"PASS: {comparisons} frozen Qt-valued edit pairs, equal-valued parent identity, fuzzy-point comparisons, replay errors and exact byte sizes")


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
