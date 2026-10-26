"""Stacked labels add up from the inner row in every display unit and precision."""
import math
import os
from fractions import Fraction
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtSvg
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from planner_app.geometry.measurement_stacks import StackedDimensionLengths
from planner_app.models import Wall, Window
from planner_app.units import FormatLength, unitModes, imperialModes
from planner_app.viewport.rendering import RenderingMixin
from planner_app.export_plan import RenderPlan


def DisplayedValue(length, mode, precision):
    text = FormatLength(length, mode, adaptive = "m", includeUnit = False, precision = precision)
    if mode in imperialModes:
        feet, text = text.split("'") if "'" in text else ("0", text)
        return Fraction(feet) * 12 + sum(Fraction(part) for part in text.replace('"', '').split())
    return Fraction(text)


def Main():
    p = QtCore.QPointF
    # Deliberately accumulate rounding error, including fractional-inch carry.
    lengths = [3690.3, 710.3, 2150.3, 380.3, 900.3, 520.3, 520.3, 900.3, 380.3, 2150.3, 710.3, 3690.3]
    for angle in (0, 37, 180):
        direction = p(math.cos(math.radians(angle)), math.sin(math.radians(angle)))
        origin = p(-1234.5, -987.6)
        stops = [0]
        for length in lengths:
            stops.append(stops[-1] + length)
        points = [origin + direction * distance for distance in stops]
        wall = Wall(points[0], points[-1])
        inner = [(first, second, [wall]) for first, second in zip(points, points[1:])]
        rows = [(points[0], points[6], [wall], 1), (points[6], points[-1], [wall], 1),
                (points[0], points[-1], [wall], 2)]
        geometry = [(p(first), p(second)) for first, second, owners in inner]
        for mode in unitModes:
            for precision in ("High", "Medium", "Low"):
                base = [DisplayedValue(QtCore.QLineF(first, second).length(), mode, precision) for first, second, owners in inner]
                rounded = StackedDimensionLengths(inner, rows, mode, precision)
                displayed = [DisplayedValue(length, mode, precision) for length in rounded]
                assert displayed == [sum(base[:6]), sum(base[6:]), sum(base)], (angle, mode, precision, displayed)
                assert displayed[0] + displayed[1] == displayed[2]
                # Reversed input order/direction cannot alter the labels.
                reversedInner = [(second, first, owners) for first, second, owners in reversed(inner)]
                assert StackedDimensionLengths(reversedInner, rows, mode, precision) == rounded
        assert [(first, second) for first, second, owners in inner] == geometry
        # Missing spans are not replaced by a misleading partial sum.
        assert StackedDimensionLengths(inner[1:], rows[-1:], "Millimeters", "High") == [QtCore.QLineF(points[0], points[-1]).length()]
    with ExampleWindow() as (main, folder):
        v = main.viewport
        walls = Rectangle(-3000.3, -2000, 6000.6, 4000)
        walls.extend([Wall(p(-1000.1, -2000), p(-1000.1, 2000), 120),
                      Wall(p(1000.1, -2000), p(1000.1, 2000), 120)])
        windows = [Window(walls[0], .08, .19), Window(walls[0], .4, .56), Window(walls[0], .78, .9)]
        InstallScene(main, walls + windows)
        v.wallMeasurementMode = "Exterior stacked"
        v.showMeasurements = v.measurementVisibility["walls"] = True
        v.SetSelection([])
        observed = []

        def CaptureLength(length, mode, **kwargs):
            text = FormatLength(length, mode, **kwargs)
            observed.append((length, text))
            return text

        for reference in ("Centerline", "Wall faces"):
            v.wallMeasurementReference = reference
            for mode in unitModes:
                v.unitsMode = mode
                for precision in ("High", "Medium", "Low"):
                    v.measurementPrecision = precision
                    observed.clear()
                    with patch("planner_app.viewport.rendering.FormatLength", CaptureLength):
                        v.grab()
                    inner, rows = v.sceneMeasurements[1:]
                    assert any(tier == 2 for first, second, owners, tier in rows)
                    rounded = StackedDimensionLengths(inner, rows, mode, precision)
                    assert all(any(abs(length - value) < 1e-7 for value, text in observed) for length in rounded)
        # PNG and SVG use the same corrected labels, with export's active units.
        data = main.BuildProjectData()
        draw = RenderingMixin.DrawSceneMeasurements
        exported = []

        def CaptureExport(viewport, *args, **kwargs):
            observed.clear()
            with patch("planner_app.viewport.rendering.FormatLength", CaptureLength):
                result = draw(viewport, *args, **kwargs)
            inner, rows = viewport.sceneMeasurements[1:]
            rounded = StackedDimensionLengths(inner, rows, viewport.unitsMode, viewport.measurementPrecision)
            assert rows and all(any(abs(length - value) < 1e-7 for value, text in observed) for length in rounded)
            exported.append(viewport.unitsMode)
            return result

        with patch.object(RenderingMixin, "DrawSceneMeasurements", CaptureExport):
            for outputFormat in ("png", "svg"):
                output = RenderPlan(folder / "rounding.plan", 250, [-4000, -3000, 8000, 6000],
                                    projectData = data, outputFormat = outputFormat, applyTheme = False)
                assert output if outputFormat == "png" else QtSvg.QSvgRenderer(output).isValid()
        assert exported == [v.unitsMode, v.unitsMode]
    print("PASS: stacked sums, all units/precisions, rotated chains, wall references, unchanged geometry and PNG/SVG labels")


if __name__ == "__main__":
    Main()
