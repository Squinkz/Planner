"""Display units and catalog search work without Qt or graphics dependencies."""
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.measurement_units import (MetricUnit, GridUnit, FormatLength, FormatArea, ParseImperialLength,
                                               unitModes, measurementPrecisions)
    from planner_app.catalog_metadata import FurnishingCategories
    from planner_app.furnishing_search import FindFurnishings, SortFurnishings, FurnishingDimensionText, SearchWords
    assert len(unitModes) == 6 and measurementPrecisions == dict(High = 1, Medium = 5, Low = 20)
    assert MetricUnit("Adaptive Metric", "cm") == (10, "cm")
    assert MetricUnit("Feet and Inches") == (304.8, "ft")
    assert GridUnit(100, "Adaptive Metric") == (1000, "m")
    assert GridUnit(10, "Adaptive Metric") == (10, "cm")
    assert GridUnit(1, "Adaptive Metric") == (1, "mm")
    assert FormatLength(1250, "Meters") == "1.25 m"
    assert FormatLength(1250, "Centimeters") == "125 cm"
    assert FormatLength(1250.4, "Millimeters") == "1250 mm"
    assert FormatLength(-.001, "Meters") == "0 m"
    assert FormatLength(15.31 * 25.4, "Inches", precision = "High") == '15 5/16"'
    assert FormatLength(11.99 * 25.4, "Feet and Inches", precision = "High") == '1\' 0"'
    assert FormatLength(-.01 * 25.4, "Inches", precision = "Low") == '0"'
    assert FormatArea(None, "Meters") == "—"
    assert FormatArea(14440000, "Meters") == "14.44 m²"
    assert FormatArea(14440000, "Centimeters") == "144,400 cm²"
    assert FormatArea(25.4 ** 2, "Inches") == "1 in²"
    for text, mode, expected in (("1′ 3.125″", "Feet and Inches", 384.175),
                                  ("-1 ft 3.125 in", "Feet and Inches", -384.175),
                                  ("1.5", "Feet and Inches", 457.2), ("1.5", "Inches", 38.1)):
        assert math.isclose(ParseImperialLength(text, mode), expected)
    for text in ("nan", "inf", "-inf", "not a length"):
        try:
            ParseImperialLength(text, "Feet and Inches")
        except ValueError:
            pass
        else:
            raise AssertionError(text)
    assert FurnishingCategories([" Kitchen ", "kitchen", "Dining", ""]) == ["Kitchen", "Dining"]
    assert FurnishingCategories(None) == ["Miscellaneous"]
    assert FurnishingCategories("Living") == ["Living"]
    for value in (True, ["Living", 3]):
        try:
            FurnishingCategories(value)
        except ValueError:
            pass
        else:
            raise AssertionError(value)
    definitions = [dict(key = "desk", name = "Desk", width = 1200, length = 600, category = "Office"),
                   dict(key = "chair", name = "Chair", width = 500, length = 500, category = "Seating"),
                   dict(key = "null", name = "Null", width = 100, length = 100)]
    assert [item["key"] for item in FindFurnishings(definitions, "desk", "Millimeters")] == ["desk"]
    assert [item["key"] for item in FindFurnishings(definitions, "w:1200mm l:600mm", "Millimeters")] == ["desk"]
    assert [item["key"] for item in SortFurnishings(definitions, "Area")] == ["chair", "desk"]
    assert FurnishingDimensionText(definitions[0], "Adaptive Metric") == "120 × 60"
    assert SearchWords("SHELVES") == ("shelf",)
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: metric/imperial conversion, precision, area, categories and catalog search without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())
    from planner_app import units, measurement_units
    from planner_app.catalog import FurnishingCategories
    from planner_app.catalog_metadata import FurnishingCategories as CoreCategories
    for name in ("MetricUnit", "GridUnit", "FormatLength", "FormatArea", "ParseImperialLength"):
        assert getattr(units, name) is getattr(measurement_units, name)
    assert FurnishingCategories is CoreCategories


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
