"""Numeric facing thresholds and ordered fireplace snaps without Qt."""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.opening_candidates import OpeningFacingChanges, FireplaceDepthSnap, FireplacePlacementCandidates
    door = (1, "swingsOutwards", -1)
    sliding = (-1, "panelsFlipped", -1)
    assert OpeningFacingChanges((-10, 0), (10, 0), (2, -2), 1, door) == {}
    assert OpeningFacingChanges((-10, 0), (10, 0), (2.01, -2.01), 1, door) == dict(hingeAtSecond = True, swingsOutwards = True)
    assert OpeningFacingChanges((-10, 0), (10, 0), (3, -3), 1, sliding) == dict(hingeAtSecond = False, panelsFlipped = True)
    assert OpeningFacingChanges((10, 0), (-10, 0), (3, -3), 1, door) == dict(hingeAtSecond = False, swingsOutwards = False)
    assert OpeningFacingChanges((0, 0), (0, 0), (3, -3), 1, door) == {}
    assert OpeningFacingChanges((-10, 0), (10, 0), (30, -30), .01, door) == {}
    assert FireplaceDepthSnap(0, [-10, 10], 1, 1, 10) == -10
    assert FireplaceDepthSnap(0, [-10, 10], 1, 1, 9.99) is None
    assert FireplaceDepthSnap(0, [], 1, 1, 10) is None
    first, second, outside, fallback = [object() for index in range(4)]
    placements = [(3, float("inf"), (0, 0), fallback), (1, 2, (10, 0), first),
                  (1, 2, (-10, 3), second), (0, 0, (100, 0), outside)]
    before = placements[:]
    plans = list(FireplacePlacementCandidates(.5, 20, 100, 0, 10, (1, 0), (0, 1), placements, -10))
    assert plans == [(.6, -10, first, True, 1), (.4, 3, second, True, 1), (.5, -10, fallback, True, 1)]
    assert placements == before
    # Tolerance admits a fraction just past the wall end and then clamps it.
    plans = list(FireplacePlacementCandidates(.1 - 1e-9, 20, 100, 0, 10, (1, 0), (0, 1),
                                             [(3, 0, (0, 0), first)], None))
    assert plans == [(.1, 0, first, False, 3)]
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: opening facing dead zones, reversed axes, depth snap ties, candidate order and bounds without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
