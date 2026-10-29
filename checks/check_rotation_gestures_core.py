"""Captured rotation frames and stationary selection edges without Qt."""
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.editing import PointerRotation, SelectionResizeCorrection
    point = math.cos(math.radians(23)), math.sin(math.radians(23))
    assert PointerRotation(point, 0, 17, True, True)[0] == 47
    assert PointerRotation(point, 0, 17, True, False)[0] == 45
    assert math.isclose(PointerRotation(point, 0, 17, False, True)[0], 40)
    assert PointerRotation((0, 0), 20, 17, True) is None
    assert PointerRotation((1e-8, 0), 20, 17, True) is None
    assert PointerRotation((float("nan"), 0), 20, 17, True) is None
    # Structural rotation intentionally keeps its zero-radius behavior and
    # snaps a relative delta, independently of furnishing-local coordinates.
    assert PointerRotation((0, 0), 20, snapping = True)[0] == -15
    for direction, angle in (((1, 0), 0), ((0, 1), 90), ((-1, 0), 180), ((0, -1), -90)):
        result, cosine, sine = PointerRotation(direction, 0)
        assert result == angle and math.isclose(cosine, direction[0], abs_tol = 1e-15)
        assert math.isclose(sine, direction[1], abs_tol = 1e-15)
    assert SelectionResizeCorrection((60, 20), (0, 0), 100, 100, (0, 0, 120, 40), "width", 1, False) == (-50, 0)
    assert SelectionResizeCorrection((60, 20), (0, 0), 100, 100, (0, 0, 120, 40), "width", -1, False) == (-70, 0)
    assert SelectionResizeCorrection((60, 20), (0, 0), 100, 100, (0, 0, 120, 40), "length", 1, False) == (0, -50)
    assert SelectionResizeCorrection((65, 25), (0, 0), 100, 100, (0, 0, 120, 40), "corner", (1, 1), False) == (5, 5)
    assert SelectionResizeCorrection((65, 25), (0, 0), 100, 100, (0, 0, 120, 40), "width", 1, True) == (5, 5)
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: captured local/global rotation, pivot dead zones and stationary selection edges without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
