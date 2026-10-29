"""Directed stair chains, landing blocking and terminal insets without Qt."""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.stair_annotation_plans import (StairAnnotationRecord, StairEndpointNeighbors,
        PrepareStairInset, PlanStairInsetLines, PlanStairArrowRuns)
    flight = StairAnnotationRecord("a", (0, 0), (100, 0), 20)
    landing = StairAnnotationRecord("b", (100, 0), (120, 0), 20)
    last = StairAnnotationRecord("c", (120, 0), (220, 0), 20)
    stairs = [flight, landing, last]
    neighbors = StairEndpointNeighbors(stairs)
    values = {key: object() for key in ("a", "b", "c")}
    assert StairEndpointNeighbors(stairs, values = values)[("a", 1)][0] is values["b"]
    trims = dict(a = (0, 10), b = (10, 10), c = (10, 0))
    assert PlanStairArrowRuns(stairs, neighbors, trims) == [
        ("a", (0, 0), (100, 0), False), ("b", (100, 0), (120, 0), False), ("c", (120, 0), (220, 0), True)]
    reversedFlight = StairAnnotationRecord("a", (0, 0), (100, 0), 20, True)
    runs = PlanStairArrowRuns([reversedFlight, landing, last], neighbors, trims)
    assert [key for key, start, tip, showTip in runs] == ["a", "c"]
    assert all(showTip for key, start, tip, showTip in runs)
    degenerate = StairAnnotationRecord("d", (120, 0), (120, 0), 20)
    blocked = [flight, landing, degenerate]
    assert [key for key, start, tip, showTip in PlanStairArrowRuns(blocked, StairEndpointNeighbors(blocked),
        dict(a = (0, 10), b = (10, 10), d = (0, 0)))] == ["a"]
    # Two independent cycles retain one head each, in insertion order.
    points = [(0, 0), (100, 0), (100, 100), (0, 100)]
    cycles = [StairAnnotationRecord((group, index), (first[0] + group * 500, first[1]),
              (second[0] + group * 500, second[1]), 20)
              for group in range(2) for index, (first, second) in enumerate(zip(points, points[1:] + points[:1]))]
    runs = PlanStairArrowRuns(cycles, StairEndpointNeighbors(cycles), {stair.key: (5, 5) for stair in cycles})
    assert [key for key, start, tip, showTip in runs if showTip] == [(0, 0), (1, 0)]
    # Neighbor tolerance is inclusive; degenerate peer endpoints intentionally
    # retain duplicate entries, preserving branch ambiguity.
    near = StairAnnotationRecord("near", (100.01, 0), (200, 0), 20)
    assert StairEndpointNeighbors([flight, near])[("a", 1)] == []  # binary subtraction is slightly over .01
    near = StairAnnotationRecord("near", (.01, 0), (200, 0), 20)
    assert StairEndpointNeighbors([flight, near])[("a", 0)] == ["near"]
    wide = StairAnnotationRecord("wide", (0, 0), (100, 0), 40)
    inset, terminals = PrepareStairInset([wide], StairEndpointNeighbors([wide]), 1)
    assert inset == 10
    contour = [[(10, -10), (90, -10), (90, 10), (10, 10), (10, -10)]]
    lines = list(PlanStairInsetLines(contour, terminals, inset, 1, lambda point: "wide"))
    assert lines == [("wide", (0, -10), (100, -10)), ("wide", (100, 10), (0, 10))]
    assert len(list(PlanStairInsetLines(contour, [], inset, 1, lambda point: "wide"))) == 4
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: directed chains/cycles, reversed flights, blocked landings, neighbor boundaries and inset cap trimming without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
