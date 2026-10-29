"""Reference-image proposals and metadata validation without Qt or decoding."""
import copy
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.reference_state import ValidateReferenceState, EditReferenceProperty, CalibrateReferenceState
    state = dict(path = "reference.png", data = "decoder-owned", visible = True,
                 center = [10, 20], width = 200, height = 100, angle = 0, opacity = .5)
    before = copy.deepcopy(state)
    validated = ValidateReferenceState(dict(state, locked = True))
    assert validated == state and validated["center"] is not state["center"]
    invalid = [dict(center = [0]), dict(center = [True, 0]), dict(width = 0), dict(height = 1e12 + 1),
               dict(angle = float("nan")), dict(opacity = 1.01), dict(visible = 1), dict(path = "bad\0path"), dict(data = b"bytes")]
    for fields in invalid:
        try:
            ValidateReferenceState({**state, **fields})
        except ValueError:
            pass
        else:
            raise AssertionError(fields)

    moved, pivot = EditReferenceProperty(state, "x", 50, pivot = (40, 60))
    assert moved["center"] == [50, 20] and pivot == (80, 60)
    moved, pivot = EditReferenceProperty(state, "y", 50, pivot = (40, 60), rotating = True)
    assert moved["center"] == [10, 10] and pivot == (40, 50)
    rotated, pivot = EditReferenceProperty(state, "angle", 90, pivot = (0, 0), rotating = True)
    assert math.isclose(rotated["center"][0], -20) and math.isclose(rotated["center"][1], 10)
    assert rotated["angle"] == 90 and pivot == (0, 0)
    rotated, unused = EditReferenceProperty(state, "angle", 90)
    assert rotated["center"] == state["center"] and rotated["angle"] == 90
    resized, unused = EditReferenceProperty(state, "width", 400, linked = True)
    assert (resized["width"], resized["height"]) == (400, 200)
    resized, unused = EditReferenceProperty(state, "length", 200, linked = True)
    assert (resized["width"], resized["height"]) == (400, 200)
    resized, unused = EditReferenceProperty(state, "width", 0)
    assert (resized["width"], resized["height"]) == (1, 100)
    assert EditReferenceProperty(state, "width", 1, linked = True) is None
    assert EditReferenceProperty(dict(state, height = 1e12), "width", 400, linked = True) is None

    calibrated, pivot = CalibrateReferenceState(state, (2, 3), (5, 7), 10, pivot = (40, 60))
    assert calibrated["center"] == [18, 37] and pivot == (78, 117)
    assert (calibrated["width"], calibrated["height"]) == (400, 200)
    assert calibrated["angle"] == state["angle"] and calibrated["opacity"] == state["opacity"]
    # Calibration keeps the chosen anchor at the same image-relative position.
    for index, dimension in ((0, "width"), (1, "height")):
        assert ((2, 3)[index] - state["center"][index]) / state[dimension] == ((2, 3)[index] - calibrated["center"][index]) / calibrated[dimension]
    for first, second, distance in (((0, 0), (1, 0), 0), ((0, 0), (1, 0), float("inf")),
                                    ((0, 0), (1, 0), float("nan")), ((0, 0), (0, 0), 10),
                                    ((0, 0), (1, 0), 1e12), ((0, 0), (1, 0), .001)):
        try:
            CalibrateReferenceState(state, first, second, distance)
        except ValueError:
            pass
        else:
            raise AssertionError((first, second, distance))
    assert state == before
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: reference metadata, linked sizing, pivots, rotation and calibration without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
