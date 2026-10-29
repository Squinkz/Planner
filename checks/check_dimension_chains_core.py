"""Dimension-chain rounding and mixed visibility clipping without Qt."""
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.dimension_chains import ComputeStackedDimensionLengths, VisibleDimensionPieces
    inner = [((0, 0), (100.4, 0), (1,)), ((100.4, 0), (200.8, 0), (1,))]
    additional = [((0, 0), (200.8, 0), (1,), 1)]
    assert ComputeStackedDimensionLengths(inner, additional, "Millimeters", "High") == [200]
    assert ComputeStackedDimensionLengths(inner, [((200.8, 0), (0, 0), (1,), 2)], "Millimeters", "High") == [200]
    gap = [inner[0], ((101.4, 0), (200.8, 0), (1,))]
    assert ComputeStackedDimensionLengths(gap, additional, "Millimeters", "High") == [200.8]
    assert ComputeStackedDimensionLengths(inner, [((0, 0), (200.8, 0), (99,), 1)], "Millimeters", "High") == [200.8]
    offset = [((0, .02), (100.4, .02), (1,)), inner[1]]
    assert ComputeStackedDimensionLengths(offset, additional, "Millimeters", "High") == [200.8]
    assert ComputeStackedDimensionLengths([], [((0, 0), (.00001, 0), (), 1)], "Millimeters", "High") == [.00001]
    assert ComputeStackedDimensionLengths(iter(inner), [], "Millimeters", "High") == []
    inch = 25.4
    imperial = [((0, 0), (1.49 * inch, 0), (1,)), ((1.49 * inch, 0), (2.98 * inch, 0), (1,))]
    total = [((0, 0), (2.98 * inch, 0), (1,), 1)]
    assert math.isclose(ComputeStackedDimensionLengths(imperial, total, "Inches", "High")[0], 3 * inch)
    assert math.isclose(ComputeStackedDimensionLengths(imperial, total, "Inches", "Low")[0], 2 * inch)
    owners = [("a", (0, 0), (100, 0), True), ("b", (100, 0), (200, 0), False),
              ("c", (200, 0), (300, 0), True)]
    assert VisibleDimensionPieces((-10, 0), (310, 0), owners) == [((-10, 0), (100, 0), ["a"]), ((200, 0), (310, 0), ["c"])]
    assert VisibleDimensionPieces((0, 0), (0, 0), owners) == []
    assert VisibleDimensionPieces((0, 0), (100, 0), []) == []
    assert VisibleDimensionPieces((0, 0), (100, 0), [("a", (0, 0), (100, 0), False)]) == []
    overlap = [("a", (0, 0), (120, 0), True), ("b", (80, 0), (200, 0), False)]
    assert VisibleDimensionPieces((-10, 0), (210, 0), overlap) == [((-10, 0), (120, 0), ["a"])]
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: complete/gapped/reversed chains, imperial tick sums, hidden spans and corner extensions without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
