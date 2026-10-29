"""Numeric resize snapping, proportional limits and arbitrary edge contacts."""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.resize_snapping import SnapResize
    arguments = ((0, 1), (0, 0), 100, 100, 110, 100, "width", 1, False, 1)
    targets = [(65, 25, True)]
    before = targets[:]
    assert SnapResize(*arguments, targets, 1, 10, False, None) == (115, 100, True, 0, [])
    assert targets == before
    assert SnapResize(*arguments, [(65, 51, True)], 1, 10, False, None) == (110, 100, False, 3, [])
    assert SnapResize(*arguments, [(70, 25, True)], 1, 10, False, None) == (110, 100, False, 3, [])
    # Alignment-only targets cannot become direct contacts halfway along an edge.
    assert SnapResize(*arguments, [(65, 25, False)], 1, 10, False, None) == (110, 100, False, 3, [])
    assert SnapResize((0, 1), (0, 0), 100, 100, 110, 100, "width", 1, True, 1,
                      [(60, 25, True)], 1, 10, False, None) == (120, 100, True, 0, [])
    result = SnapResize((0, 1), (0, 0), 100, 200, 110, 220, "corner", (1, 1), False, 1,
                        [(70, 140, True)], 1, 30, False, None)
    assert result == (120, 240, True, 0, [])
    assert SnapResize((0, 1), (0, 0), 100, 200, -10, -20, "corner", (1, 1), False, .001,
                      [], 1, 10, False, None) == (.001, .002, False, 3, [])
    # No grid intersection on the forward ray retains priority 2, even though
    # no snap was applied. This is part of the desktop's existing state contract.
    assert SnapResize((0, 1), (0, 0), 100, 100, -10, 100, "width", 1, False, 1,
                      [], 1, 10, False, 1) == (-10, 100, False, 2, [])
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: proportional corners, label minimums, centered/edge contacts, strict thresholds and snap state without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
