"""Project values and portable selection validation run without Qt."""
import copy
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.record_validation import ValidateNumber, ValidateCoordinates, ValidateFlags, projectFileLimit
    from planner_app.record_schema import ReadArrowTipSize, openingFieldsByType
    from planner_app.selection_records import ValidateSelectionPayload
    assert projectFileLimit == 64 * 1024 * 1024
    assert ValidateNumber(4) == 4.0 and ValidateCoordinates([1, -2]) == (1.0, -2.0)
    assert ValidateNumber(0, minimum = 0, maximum = 1) == 0
    assert ValidateFlags({"enabled": False}, ("enabled",)) == {"enabled": False}
    for value in (True, "3", None, float("nan"), float("inf"), 1e12 + 1):
        try:
            ValidateNumber(value)
        except ValueError:
            pass
        else:
            raise AssertionError(value)
    for point in ((1, 2), [1], [1, True], [1, float("inf")]):
        try:
            ValidateCoordinates(point)
        except ValueError:
            pass
        else:
            raise AssertionError(point)
    for flags in ({"enabled": 1}, {}, []):
        try:
            ValidateFlags(flags, ("enabled",))
        except ValueError:
            pass
        else:
            raise AssertionError(flags)
    assert "wellDepth" in openingFieldsByType["Window"]
    assert ReadArrowTipSize(dict(solidTip = True, tipSize = 2), 100) == 200
    assert ReadArrowTipSize(dict(solidTip = False, tipSize = 2), 100) == 35
    assert ReadArrowTipSize(dict(solidTip = False, tipSize = 2, tipSizeMode = "millimeters"), 100) == 2

    wall = dict(type = "Wall", selected = False, first = [-1000, 0], second = [1000, 0], width = 240,
                material = "Generic", firstMiter = 0, secondMiter = 0)
    window = dict(type = "Window", selected = True, center = [0, 0], length = 600, fraction = .5,
                  parent = 0, swingsOutwards = False)
    payload = dict(version = 1, center = [0, 0], objects = [wall, window], groups = [[0, 1]])
    before = copy.deepcopy(payload)
    normalized = ValidateSelectionPayload(payload, {}, {"Generic"}, {"Millimeters"}, {"Objects"})
    assert normalized is not None and normalized["objects"][1]["wellDepth"] == 600
    assert normalized["objects"][1]["measurementFlipped"] is False
    assert normalized["objects"][1]["windowWell"] is False
    assert payload == before  # Legacy defaults must not mutate caller-owned records.
    malformed = [None, [], {}, dict(payload, version = 2), dict(payload, objects = []),
                 dict(payload, groups = [[0, 0]]), dict(payload, groups = [[0, 2]]),
                 dict(payload, groups = [[False, 1]]), dict(payload, groups = [[0, 1], [0, 1]]),
                 dict(payload, objects = [dict(wall, selected = False)]),
                 dict(payload, objects = [wall, dict(window, parent = True)]),
                 dict(payload, objects = [wall, dict(window, length = 3000)]),
                 dict(payload, objects = [wall, dict(window, wallDirection = [0, 0])]),
                 dict(payload, objects = [wall, dict(window, wellDepth = -1)]),
                 dict(payload, objects = [wall, dict(window, windowWell = 1)]),
                 dict(payload, objects = [dict(wall, width = float("nan")), window])]
    for invalid in malformed:
        assert ValidateSelectionPayload(invalid, {}, {"Generic"}, {"Millimeters"}, {"Objects"}) is None, invalid
    label = dict(type = "Label", selected = True, first = [0, 0], second = [.2, 0], width = .2, text = "Tiny")
    assert ValidateSelectionPayload(dict(version = 1, center = [0, 0], objects = [label]), {}, (), (), ()) is not None
    furnishing = dict(type = "Furnishing", selected = True, first = [0, 0], second = [100, 0], width = 100, definition = "desk")
    data = dict(version = 1, center = [0, 0], objects = [furnishing])
    assert ValidateSelectionPayload(data, {}, (), (), ()) is None
    assert ValidateSelectionPayload(data, {"desk": {"key": "desk", "graphicData": b"<svg/>"}}, (), (), ()) is not None
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: primitive values, schema compatibility, selection groups, parents, defaults and missing assets without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
