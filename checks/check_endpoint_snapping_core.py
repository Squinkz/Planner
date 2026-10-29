"""Footprint-cap geometry and endpoint snap decisions without Qt."""
from pathlib import Path
import math
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.endpoint_snapping import CapEndpoint, AlignmentPlacementCandidates, SelectEndpointSnap
    for side in (-1, 1):
        target = CapEndpoint((1000, side * 100), (0, 0), (0, side * 100), (0, 100), 200, False)
        assert math.isclose(target[0], 1000, abs_tol = 1e-10) and abs(target[1]) < 1e-10
    assert CapEndpoint((1000, 120), (0, 0), (0, 100), (0, 100), 200, True) == (1000, 20)
    assert CapEndpoint((100, 0), (0, 0), (0, 100), (0, 100), 200, False) is None
    assert CapEndpoint((0, 0), (0, 0), (0, 100), (0, 100), 200, False) is None
    for offset in (0, 1e8, -1e8):
        target = CapEndpoint((offset + 1000, offset + 100), (offset, offset), (0, 100), (0, 100), 200, False)
        assert math.isclose(target[0], offset + 1000, abs_tol = 1e-8)
        assert math.isclose(target[1], offset, abs_tol = 1e-8)
    firstGuides, secondGuides, controlGuides = [(0, 10)], [(1, 20)], [(0, 30)]
    candidates = [(2, (10, 10), firstGuides), (1, (20, 20), secondGuides), (1, (20, 20), firstGuides)]
    before = candidates[:]
    assert list(AlignmentPlacementCandidates(candidates, (20, 20), (30, 30), controlGuides)) == [
        ((20, 20), secondGuides), ((10, 10), firstGuides), ((30, 30), controlGuides)]
    assert candidates == before
    # Exact candidate equality retains the existing straight-wall preference,
    # even when a footprint candidate duplicates the control alignment.
    direct = (0, 100, (100, 100), [])
    aligned = (1, 10, (30, 0), [(1, 0)])
    closer = (1, 1, (20, 30), [(0, 20)])
    grid = (2, 0, (0, 0), [])
    assert SelectEndpointSnap((1, 2), (0, 0), [grid, closer, aligned], [aligned], True) == ((30, 0), True, 1, [(1, 0)])
    assert SelectEndpointSnap((1, 2), (0, 0), [grid, closer, aligned], [aligned], False) == ((20, 30), True, 1, [(0, 20)])
    assert SelectEndpointSnap((1, 2), (0, 0), [grid, closer, aligned, direct], [aligned], True) == ((100, 100), True, 0, [])
    assert SelectEndpointSnap((1, 2), (0, 0), [], [], True) == ((1, 2), False, 3, [])
    stale = (1, 0, (20, 30), [(0, 20), (1, 0)])
    assert SelectEndpointSnap((1, 2), (0, 0), [stale], [stale], True) == ((20, 30), True, 1, [(0, 20)])
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: cap geometry, collision fallback order, stable snap priority and straight-wall guides without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
