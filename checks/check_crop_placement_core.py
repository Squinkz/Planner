"""Export crop rules and detached paste geometry work without Qt."""
import copy
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.export_crop import MoveCropOrigin, MoveCropEdge, HitCropEdge, HitCropRuler
    from planner_app.selection_placement import PlanSelectionPlacement
    assert MoveCropOrigin((0, 0), 0, -5, 10) == [-10, 0]
    assert MoveCropOrigin((0, 0), 1, 5, 10) == [0, 10]
    assert MoveCropOrigin((3, 4), 0, 7.25) == [7.25, 4]
    bounds = (0, 0, 100, 100)
    assert MoveCropEdge(bounds, 0, 150, step = 10) == (90, 0, 10, 100)
    assert MoveCropEdge(bounds, 1, -50, step = 10) == (0, 0, 10, 100)
    assert MoveCropEdge(bounds, 0, 150, reset = True) == (150, 0, 1, 100)
    assert MoveCropEdge(bounds, 3, -50, reset = True) == (0, -51, 100, 1)
    assert MoveCropEdge(bounds, 0, 150) == (99, 0, 1, 100)
    assert MoveCropEdge(bounds, 0, -1, step = 10, origin = 4) == (-6, 0, 106, 100)
    assert HitCropEdge((8, 8), (0, 0), (100, 100)) == 0
    assert HitCropEdge((9, 9), (0, 0), (100, 100)) is None
    assert HitCropRuler((50, -10), (0, 0, 100, 100), 10) == 0
    assert HitCropRuler((-10, 50), (0, 0, 100, 100), 10) == 1
    assert HitCropRuler((50, 0), (0, 0, 100, 100), 10) is None
    wall = dict(type = "Wall", selected = True, first = [0, 0], second = [100, 0], width = 100)
    opening = dict(type = "Window", selected = False, parent = 0, center = [50, 0], fraction = .5, length = 20)
    payload = dict(version = 1, center = [0, 0], objects = [wall, opening])
    before = copy.deepcopy(payload)
    plans = list(PlanSelectionPlacement(payload, (5, -7)))
    assert plans == [(0, wall, (5, -7), (105, -7), 100)]
    assert plans[0][1] is wall and payload == before
    label = dict(wall, type = "Label", width = 1e-8, second = [1e-8, 0])
    assert len(list(PlanSelectionPlacement(dict(payload, objects = [label]), (0, 0)))) == 1
    angle = dict(wall, type = "AngleGuide", width = 0, second = [0, 0])
    assert len(list(PlanSelectionPlacement(dict(payload, objects = [angle]), (0, 0)))) == 1
    for invalid, delta in ((dict(payload, version = 2), (0, 0)), (dict(payload, objects = []), (0, 0)),
            (payload, (float("inf"), 0)), (dict(payload, objects = [dict(wall, selected = 1)]), (0, 0)),
            (dict(payload, objects = [dict(wall, first = [float("nan"), 0])]), (0, 0)),
            (dict(payload, objects = [dict(label, width = 1e-9)]), (0, 0)),
            (dict(payload, objects = [dict(wall, second = [0, 0])]), (0, 0)),
            (dict(payload, objects = [dict(wall, type = "Pillar"), opening]), (0, 0)),
            (dict(payload, objects = [wall, dict(opening, parent = 2)]), (0, 0)),
            (dict(payload, objects = [wall, dict(opening, length = .5)]), (0, 0)),
            (dict(payload, objects = [dict(wall, first = [1e308, 0])]), (1e308, 0))):
        try:
            list(PlanSelectionPlacement(invalid, delta))
        except ValueError:
            pass
        else:
            raise AssertionError((invalid, delta))
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: crop crossing/reset/grid origins, ruler hits, translated paste geometry, tiny labels, host validation and overflow without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
