"""Export normalization, inheritance and physical sizing without Qt."""
import copy
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.export_settings import (NormalizeExportSettings, ResolveExportView, ExportScalePerMeter,
                                             ExportPixelSize, BorderSize)
    base = dict(unitsMode = "Millimeters", showMeasurements = False,
                measurementVisibility = dict(walls = True, doors = True, railings = False),
                visibility = {"World": False, "Walls": True, "Doors": False},
                viewportSettings = dict(overall = 1, major = .5),
                lineworkSettings = dict(baseWidth = 2, walls = 1), measurementSettings = dict(walls = 1))
    context = (base, ("Millimeters", "Feet and Inches"), {"High": 1}, {"walls": 1, "stairs": 2, "counters": 2})
    legacy = dict(floors = False, solidFurnishings = False)
    assert NormalizeExportSettings(legacy, *context) == dict(roomStyle = "Canvas", solidObjects = False)
    assert legacy == dict(floors = False, solidFurnishings = False)
    assert NormalizeExportSettings(dict(legacy, roomStyle = "Tinted", solidObjects = True), *context) == dict(roomStyle = "Tinted", solidObjects = True)
    assert NormalizeExportSettings(dict(measurementVisibility = dict(elevators = True)), *context) == {}
    options = dict(bounds = [-1000, -1000, 2000, 1000], viewportSettings = dict(overall = 1.5),
                   lineworkSettings = dict(baseWidth = 3), measurementVisibility = dict(doors = True),
                   measurementSettings = dict(stairs = 2), fileType = "SVG", scaleMode = "Architectural",
                   architecturalScale = 100, dpi = 300, solidRooms = True)
    original = copy.deepcopy(options)
    normalized = NormalizeExportSettings(options, *context)
    assert normalized == options and options == original
    normalized["bounds"][0] = 99
    normalized["lineworkSettings"]["baseWidth"] = 4
    assert options == original
    for invalid in (None, [], {"unknown": True}, {"floors": 1}, {"dpi": True}, {"dpi": 0},
                    {"scale": float("nan")}, {"scale": 0}, {"bounds": [0, 0, -1, 10]},
                    {"unitsMode": "Unknown"}, {"solidRooms": 1}, {"roomStyle": "Unknown"},
                    {"measurementSettings": {"stairs": 1}}, {"lineworkSettings": {"baseWidth": .5}},
                    {"viewportSettings": {"unknown": 1}}, {"texture": "../texture.png"}, {"canvasColor": 5}):
        try:
            NormalizeExportSettings(invalid, *context)
        except ValueError:
            pass
        else:
            raise AssertionError(invalid)
    # Color names remain strings here; the desktop adapter owns QColor parsing.
    assert NormalizeExportSettings(dict(canvasColor = "red"), *context) == dict(canvasColor = "red")

    overrides = dict(unitsMode = "Feet and Inches", measurementVisibility = dict(doors = True),
                     visibility = dict(Doors = True), lineworkSettings = dict(walls = .5))
    before = copy.deepcopy((base, overrides))
    view = ResolveExportView(base, overrides)
    assert view["autoSizingUnitsMode"] == "Millimeters" and view["unitsMode"] == "Feet and Inches"
    assert view["showMeasurements"] and view["measurementVisibility"] == dict(walls = False, doors = True, railings = False)
    assert view["visibility"] == {"World": True, "Walls": True, "Doors": True}
    assert view["lineworkSettings"] == dict(baseWidth = 2, walls = .5)
    assert (base, overrides) == before
    inherited = ResolveExportView(base, {})
    assert inherited["visibility"]["World"] is False and inherited["showMeasurements"] is False
    view["lineworkSettings"]["baseWidth"] = 4
    assert (base, overrides) == before

    assert ExportScalePerMeter({}, "PNG") == 100
    assert ExportScalePerMeter(dict(scale = 123.45), "SVG") == 123.45
    arch = dict(scale = 777, scaleMode = "Architectural", dpi = 300, architecturalScale = 100)
    assert math.isclose(ExportScalePerMeter(arch, "PNG"), 300 * 1000 / (25.4 * 100))
    assert ExportScalePerMeter(arch, "PNG_OPTIMIZED") == ExportScalePerMeter(arch, "PNG")
    assert math.isclose(ExportScalePerMeter(arch, "SVG"), 96 * 1000 / (25.4 * 100))
    assert BorderSize("None", 100) == 0 and BorderSize("Frame", 1) == 4
    assert BorderSize("Ruler + Reference Zones", 28) == 56
    assert ExportPixelSize((0, 0, 10000, 5000), 100) == (1000, 500)
    assert ExportPixelSize((0, 0, 10000, 5000), 100, BorderSize("Plain")) == (1056, 556)
    assert ExportPixelSize((0, 0, 10000.00000001, 5000), 100) == (1000, 500)
    assert ExportPixelSize((0, 0, 10000.1, 5000), 100) == (1001, 500)
    assert ExportPixelSize((0, 0, .001, .001), .001) == (1, 1)
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: export normalization, legacy defaults, view inheritance, units, scale and resolution without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
