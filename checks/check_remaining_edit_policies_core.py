"""Remaining dimension, opening transfer and run-target rules without Qt."""
import math
from pathlib import Path
import random
import subprocess
import sys


def CheckWithoutQt():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
    from planner_app.dimension_actions import ImmediateDimensionActions, PlanDimensionActions
    from planner_app.geometry.group_movement import OpeningTransferLength, PlanOpeningTransfer
    from planner_app.geometry.endpoint_snapping import NearestRunControlTarget
    visibility = dict(walls = True, stairs = True, counters = True, railings = True)
    for kind in ("BoundaryLine", "DashedLine", "SolidLine"):
        assert ImmediateDimensionActions(kind, True, False, visibility).canHide is False
    assert ImmediateDimensionActions("MeasurementGuide", True, False, visibility).canHide is True
    assert ImmediateDimensionActions("Wall", True, True, visibility) is None
    settings = dict(doors = 1, windows = 1, stairs = 2, counters = 2)
    early, split, flip = PlanDimensionActions("Door", "All", settings, False)
    assert early is None and flip
    assert PlanDimensionActions("Door", "All", settings, False, parentHidden = True)[0] is not None
    assert OpeningTransferLength((1000, 0), (0, 1), 1, 1) is None
    assert OpeningTransferLength((1000, 0), (0, 2), 1, 1) == 1000
    randomizer = random.Random(391)
    for index in range(1000):
        sourceLength, targetLength = randomizer.uniform(10, 10000), randomizer.uniform(10, 10000)
        sourceFraction, targetFraction = randomizer.random(), randomizer.uniform(-1, 2)
        openings = [(randomizer.random(), randomizer.uniform(1, 1000)) for item in range(1 + index % 5)]
        reverse = bool(index % 2)
        offsets = [(fraction - sourceFraction) * sourceLength * (-1 if reverse else 1) for fraction, length in openings]
        lower = max(length / 2 - offset for (fraction, length), offset in zip(openings, offsets))
        upper = min(targetLength - length / 2 - offset for (fraction, length), offset in zip(openings, offsets))
        expected = None
        if lower <= upper:
            distance = max(lower, min(upper, targetFraction * targetLength))
            expected = ([(distance + offset) / targetLength for offset in offsets], abs(distance - targetFraction * targetLength) > .01)
        assert PlanOpeningTransfer(sourceLength, sourceFraction, targetLength, targetFraction, openings, reverse) == expected
    targets = [(-1, 0), (1, .01), (1, .011), (2, 0)]
    assert NearestRunControlTarget((0, 0), (1, 0), targets, True, lambda index: 1) == (1, 1)
    assert NearestRunControlTarget((0, 0), (1, 0), targets, True, lambda index: 1, limit = 1) is None
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: portable dimension actions, 1,000 opening transfer plans, ray eligibility and stable target ties")


if __name__ == "__main__":
    if "--without-qt" in sys.argv:
        CheckWithoutQt()
    else:
        result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"], capture_output = True, text = True, timeout = 10)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout.strip())
