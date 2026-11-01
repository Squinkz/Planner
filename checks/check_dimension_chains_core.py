"""Dimension-chain rounding and mixed visibility clipping without Qt."""
import math
import random
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.dimension_chains import ComputeStackedDimensionLengths, VisibleDimensionPieces
    inner = [((0, 0), (100.4, 0), (1,)), ((100.4, 0), (200.8, 0), (1,))]
    additional = [((0, 0), (200.8, 0), (1,), 1)]
    assert ComputeStackedDimensionLengths(inner, additional, "Millimeters", "High") == [201]
    assert ComputeStackedDimensionLengths(inner, [((200.8, 0), (0, 0), (1,), 2)], "Millimeters", "High") == [201]
    pieces, overall = ComputeStackedDimensionLengths(inner, additional, "Millimeters", "High", includeInner = True)
    assert sorted(pieces) == [100, 101] and sum(pieces) == overall[0] == 201
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
    assert math.isclose(ComputeStackedDimensionLengths(imperial, total, "Inches", "Low")[0], 3 * inch)
    # Opposite sides have different subdivisions but the same measured overall.
    top = [3690, 710, 2150, 380, 900, 520, 520, 900, 380, 2150, 710, 3690]
    bottom = [4606.6, 7486.8, 4606.6]
    for lengths in (top, bottom):
        stops = [0]
        for length in lengths:
            stops.append(stops[-1] + length)
        spans = [((first, 0), (second, 0), (1,)) for first, second in zip(stops, stops[1:])]
        totals = [((0, 0), (16700, 0), (1,), 2)]
        pieces, overall = ComputeStackedDimensionLengths(spans, totals, "Millimeters", "Medium", includeInner = True)
        assert overall == [16700] and sum(pieces) == 16700
        assert pieces == list(reversed(pieces)), "A symmetric chain lost its symmetry"
        assert all(abs(displayed - actual) < 5 for displayed, actual in zip(pieces, lengths))
        if lengths is bottom:
            assert pieces == [4605, 7490, 4605]
        else:
            assert pieces == lengths, "Exact opening sizes were changed"
    # Exercise independent subdivisions and nominal openings after arbitrary
    # rotations/translations, rather than relying on one favorable rounding tie.
    generator = random.Random(20261101)
    for case in range(150):
        mode, precision, step = generator.choice((("Millimeters", "High", 1), ("Millimeters", "Medium", 5),
            ("Millimeters", "Low", 20), ("Inches", "High", 25.4 / 16), ("Inches", "Low", 25.4)))
        lengths = [generator.uniform(10, 3000) for index in range(generator.randrange(3, 30))]
        lengths[1] = 36 * step
        angle = generator.uniform(-math.pi, math.pi)
        direction = math.cos(angle), math.sin(angle)
        points = [(generator.uniform(-100000, 100000), generator.uniform(-100000, 100000))]
        for length in lengths:
            points.append((points[-1][0] + direction[0] * length, points[-1][1] + direction[1] * length))
        spans = [(first, second, (1,)) for first, second in zip(points, points[1:])]
        middle = len(spans) // 2
        totals = [(points[0], points[middle], (1,), 1), (points[middle], points[-1], (1,), 1),
                  (points[0], points[-1], (1,), 2)]
        pieces, rows = ComputeStackedDimensionLengths(spans, totals, mode, precision, includeInner = True)
        actual = math.dist(points[0], points[-1])
        expected = math.floor(actual / step + .5 + 1e-9) * step
        assert math.isclose(rows[-1], expected, abs_tol = 1e-7)
        assert math.isclose(sum(pieces[:middle]), rows[0], abs_tol = 1e-7)
        assert math.isclose(sum(pieces[middle:]), rows[1], abs_tol = 1e-7)
        assert math.isclose(rows[0] + rows[1], expected, abs_tol = 1e-7)
        assert math.isclose(pieces[1], lengths[1], abs_tol = 1e-7), "Nominal opening width changed"
        assert all(abs(displayed - length) < step + 1e-7 for displayed, length in zip(pieces, lengths))
        reversedSpans = [(second, first, owners) for first, second, owners in reversed(spans)]
        mirroredPieces, mirroredRows = ComputeStackedDimensionLengths(reversedSpans, list(reversed(totals)), mode, precision, includeInner = True)
        assert mirroredPieces == list(reversed(pieces)) and mirroredRows == list(reversed(rows))
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
