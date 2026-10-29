"""Numeric sizing and landing geometry run without Qt or site packages."""
import copy
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.sizing import (RailingPostCount, StairLandingTrims, StairStepLayout,
                                             StairCountForStepSize, sizingCountLimit)
    bounds = (900, 1500, 1200)
    assert RailingPostCount(2400, bounds) == 3
    assert RailingPostCount(0, bounds) == 2
    assert RailingPostCount(100, bounds) == 2
    assert RailingPostCount(3000, bounds, manualCount = 7) == 7
    assert RailingPostCount(3000, bounds, manualCount = 1) == 2
    for length in (899.9, 900, 1200, 1500, 1500.1, 1800, 10000):
        count = RailingPostCount(length, bounds)
        intervals = count - 1
        actual = (max(bounds[0] - length / intervals, 0, length / intervals - bounds[1]),
                  abs(length / intervals - bounds[2]))
        for alternative in range(1, 20):
            candidate = (max(bounds[0] - length / alternative, 0, length / alternative - bounds[1]),
                         abs(length / alternative - bounds[2]))
            assert actual <= candidate

    first, second = (0, 0), (2500, 0)
    neighbors = [((0, 0), (0, 2500), 1000), ((2500, 0), (2500, -2500), 1200)]
    before = copy.deepcopy(neighbors)
    assert StairLandingTrims(first, second, 800, iter(neighbors)) == (500, 600)
    assert neighbors == before
    assert StairLandingTrims(first, second, 800, []) == (0, 0)
    assert StairLandingTrims(first, second, 800, [((0, 0), (0, 0), 1000)]) == (0, 0)
    assert StairLandingTrims(first, second, 800, [((0, 0), (-2500, 0), 1000)]) == (0, 0)
    assert StairLandingTrims(first, second, 800, [((0, .0101), (0, 2500), 1000)]) == (0, 0)
    assert StairLandingTrims((0, 0), (100, 0), 800, neighbors) == (100, 0)
    angle = math.radians(179)
    assert StairLandingTrims(first, second, 800, [((0, 0), (2500 * math.cos(angle), 2500 * math.sin(angle)), 1200)]) == (0, 0)
    # A rigid rotation/translation cannot alter the physical landing lengths.
    for degrees in (0, 37, 90, 179):
        cosine, sine = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
        def Transform(point):
            return (1e6 + point[0] * cosine - point[1] * sine, -2e6 + point[0] * sine + point[1] * cosine)
        moved = [(Transform(a), Transform(b), width) for a, b, width in neighbors]
        trims = StairLandingTrims(Transform(first), Transform(second), 800, moved)
        assert all(math.isclose(actual, expected, abs_tol = 1e-7) for actual, expected in zip(trims, (500, 600)))

    assert StairStepLayout(2200, (0, 0), (250, 300)) == (8, 275, 0)
    assert StairStepLayout(2500, (0, 500), (250, 300)) == (7, 2000 / 7, 1)
    assert StairStepLayout(2500, (500, 500), (250, 300), manualCount = 8) == (6, 250, 2)
    assert StairStepLayout(2500, (500, 500), (250, 300), manualCount = 1) == (1, 1500, 2)
    assert StairStepLayout(100, (0, 0), (250, 300)) == (1, 100, 0)
    assert StairStepLayout(0, (0, 0), (250, 300)) == (0, 0, 0)
    assert StairStepLayout(100, (100, 100), (250, 300)) == (0, 0, 2)
    assert StairCountForStepSize(2500, (500, 500), 250) == 8
    assert StairCountForStepSize(20000, (0, 500), .1) == sizingCountLimit
    assert StairCountForStepSize(0, (0, 0), 250) == 1
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: standalone railing/stair counts, spacing, landing joins, limits and rigid-transform invariance")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
