"""Movement constraints and anchor priority without Qt or site packages."""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.movement_snapping import (MovementAxes, ConstraintAxes,
        ConstrainedAngle, ConstrainMovement, SnapMovement)
    assert MovementAxes((0, 0), (3, 4)) == ((.6, .8), (-.8, .6))
    assert MovementAxes((0, 0), (3, 4), True) == ((.8, -.6), (.6, .8))
    assert MovementAxes((4, 4), (4, 4), True) == ((1, 0), (0, 1))
    assert ConstrainMovement((4, 4), constrain = True) == ((4, 0), (1, 0))
    assert ConstrainMovement((-4, -5), constrain = True) == ((0, -5), (0, -1))
    assert ConstrainMovement((3, 2), constrain = True, axes = ((0, 1), (1, 0))) == ((3, 0), (1, 0))
    assert ConstrainMovement((-3, 2), (1, 0)) == ((-3, 0), (-1, 0))
    # Supplied travel vectors are deliberately not normalized, preserving the
    # caller's existing projection behavior, including degenerate vectors.
    assert ConstrainMovement((3, 2), (2, 0)) == ((12, 0), (2, 0))
    assert ConstrainMovement((3, 2), (0, 0)) == ((0, 0), (0, 0))
    assert ConstrainMovement((3, 2)) == ((3, 2), None)
    axes = ConstraintAxes((0, 0))
    assert len(axes) == 12 and axes[0] == (1, 0)
    assert ConstraintAxes((0, 1))[0][1] == 1
    assert ConstrainedAngle((1, .01), axes[0]) == 0
    anchors, targets = [(0, 0), (100, 100)], [(12, 0, True), (108, 100, True)]
    before = (anchors[:], targets[:])
    # Equidistant anchors preserve discovery order; both are exact vertex snaps.
    assert SnapMovement(anchors, (10, 0), targets, 1, 5, False, None) == ((12, 0), True, 0, [])
    assert SnapMovement(anchors[::-1], (10, 0), targets, 1, 5, False, None) == ((8, 0), True, 0, [])
    assert (anchors, targets) == before
    # A farther direct snap wins over a closer alignment or grid correction.
    assert SnapMovement([(0, 0), (100, 100)], (10, 0), [(14, 0, True), (110, 99, False)],
                        1, 5, True, 10) == ((14, 0), True, 0, [])
    assert SnapMovement([], (-10, 2), [], 1, 5, False, None, (1, 0)) == ((0, 0), False, 3, [])
    assert SnapMovement([(0, 0)], (10, 3), [], 1, 5, False, None, (1, 0)) == ((10, 0), False, 3, [])
    assert SnapMovement([(0, 0)], (11, 3), [], 1, 5, False, 10) == ((10, 0), True, 2, [])
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: movement frames, angular constraints, stable anchor priority and final ray projection without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
