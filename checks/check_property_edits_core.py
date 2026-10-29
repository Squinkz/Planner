"""Property edit policies and numeric resizing work without Qt."""
from pathlib import Path
import subprocess
import sys


def CheckWithoutQt():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
    from planner_app.property_edits import (PropertyScale, PlanPropertyTargets, RequestedPropertyMatches, LinkedPropertySizes, PlanLinearPropertySize)
    entries = [(1, "Wall", 0), (2, "Column", None), (1, "Wall", 1)]
    assert PlanPropertyTargets(entries, "length") == [2, 1]
    assert PlanPropertyTargets(entries, "x") == [0, 2]
    assert PlanPropertyTargets(entries[:1], "length") is None
    assert PlanPropertyTargets([(1, "Wall", None), (2, "Stair", None)], "width") is False
    assert PropertyScale("width", "Stair") == 1000 and PropertyScale("width", "Wall") == 10
    assert RequestedPropertyMatches("length", "Furnishing", 1000, 100, "Adaptive Metric")
    assert RequestedPropertyMatches("length", "Wall", 304.8, 12, "Inches")
    assert LinkedPropertySizes(100, 200, "width", 150) == (150, 300)
    assert LinkedPropertySizes(0, 200, "width", 150) is None
    assert PlanLinearPropertySize((0, 0), (100, 0), 200, 0, centered = True) == ((-50, 0), (150, 0))
    assert PlanLinearPropertySize((5, 6), (5, 6), 2, 10) == (None, (15, 6))
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: portable property units, bulk targets, requested values and linked/linear sizes")


if __name__ == "__main__":
    if "--without-qt" in sys.argv:
        CheckWithoutQt()
    else:
        result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"], capture_output = True, text = True, timeout = 10)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout.strip())
