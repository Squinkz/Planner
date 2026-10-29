"""Move/rotate attachment precedence and reflection policy without Qt."""
from pathlib import Path
import math
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.selection_edits import (MoveObjectRecord, ReflectionObjectRecord,
        PlanMoveSelection, PlanSelectionReflection)
    from planner_app.geometry.affine import ReflectionFrame, TransformAffinePoint
    first = MoveObjectRecord("a", ((0, 0), (100, 0)))
    second = MoveObjectRecord("b", ((100, 0), (200, 0)))
    attachments = [("a", "b", 0, (100, 0)), ("a", "g", 0, (100, 0)),
                   ("b", "g", 0, (100, 0)), ("b", "g", 1, (200, 0))]
    points, openings, offsets = PlanMoveSelection([first, second], attachments, [("g", 2, (10, 0))],
        (5, 7), 0, (0, 0), False)
    assert [entry[:2] for entry in points] == [("a", 0), ("a", 1), ("b", 0), ("b", 1), ("g", 0), ("g", 1)]
    assert points[2][2] == (105, 7) and offsets == [("g", (10, 0))]
    # The same guide's endpoints came from different local origins, so it
    # keeps its text offset unless the geometry backend considers them equal.
    points, openings, offsets = PlanMoveSelection([first, second], attachments, [("g", 2, (10, 0))],
        (0, 0), 90, (0, 0), True)
    assert offsets == []
    assert PlanMoveSelection([first, second], attachments, [("g", 2, (10, 0))],
        (0, 0), 90, (0, 0), True, originsMatch = lambda a, b: True)[2]
    opening = MoveObjectRecord("door", ((20, 0), (40, 0)), True)
    assert PlanMoveSelection([opening], [], [], (5, -7), 0, (0, 0))[1] == [("door", (35, -7), (20, 0))]
    frame = ReflectionFrame((50, 20), 0, True)
    assert TransformAffinePoint((20, 10), frame) == (80, 10)
    assert TransformAffinePoint((20, 10), ReflectionFrame((0, 0), 90, True)) == (20, -10)
    wall = ReflectionObjectRecord("wall", ((0, 0), (100, 0)), "geometry")
    door = ReflectionObjectRecord("door", ((20, 0), (40, 0)), "opening")
    edits, targets = PlanSelectionReflection([wall, door], [("door", "wall", (20, 0), (40, 0))],
        (50, 0), False, True)
    # The parent wall's local frame wins over the selected opening's own center.
    assert targets == [("door", (70, 0), (-20, 0))] and len(edits) == 1
    artwork = ReflectionObjectRecord("desk", ((0, -10), (0, 10)), "artwork", angle = 37)
    text = ReflectionObjectRecord("label", ((100, -10), (100, 10)), "text", angle = 23)
    edits, targets = PlanSelectionReflection([artwork, text], [], (50, 0), True)
    assert edits[0][1] == "artwork" and edits[0][3:] == (True, None)
    assert edits[1][1] == "text" and edits[1][3:] == (None, None)
    assert math.isclose((edits[0][2][0][0] + edits[0][2][1][0]) / 2, 100)
    assert math.isclose((edits[1][2][0][0] + edits[1][2][1][0]) / 2, 0)
    assert PlanSelectionReflection([artwork], [], (0, 0), True, value = False)[0] == []
    local = PlanSelectionReflection([artwork], [], (50, 0), True, True)[0][0]
    assert local[2] == artwork.points
    frames = []
    def Backend(operation, *values):
        assert operation == "reflection"
        frames.append(values)
        return ReflectionFrame(*values)
    PlanSelectionReflection([artwork, text, wall], [], (50, 0), True, backend = Backend)
    assert len(frames) == 1, "global selections must share one reflection frame"
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: attachment/selected-vertex precedence, guide origins, opening hosts, reflection flags and readable text without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
