"""Precise potential issues distinguish real geometry from clustered-endpoint drift."""
import copy
import math
from pathlib import Path
import subprocess
import sys


def CheckWithoutQt():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
    from planner_app.geometry.wall_diagnostics import WallDiagnosticRecord, PlanPotentialWallRepairs
    from planner_app.measurement_units import FormatLength
    def Check(walls, step = 100):
        before = copy.deepcopy(walls)
        result = PlanPotentialWallRepairs(walls, step, (0, 0), "Millimeters")
        assert walls == before
        return result
    # An accepted near-coincident junction must not tilt the shorter reference
    # ray and amplify that artificial angle along its much longer neighbour.
    walls = [WallDiagnosticRecord(1, 1, (0, 0), (100000, 0), 120),
             WallDiagnosticRecord(2, 2, (.005, .005), (.005, 1000.005), 120),
             WallDiagnosticRecord(3, 3, (.005, 1000.005), (1000.005, 1000.005), 120)]
    for angle in (0, 30, 90, 173):
        cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        def Rotate(point):
            return (point[0] * cosine - point[1] * sine + 1000000,
                    point[0] * sine + point[1] * cosine - 2000000)
        rotated = [WallDiagnosticRecord(wall.key, wall.objectId, Rotate(wall.first), Rotate(wall.second), wall.width) for wall in walls]
        assert not any(issue["code"].startswith("potential:right-angle") for issue in Check(rotated)), angle
        assert not any(issue["code"].startswith("potential:right-angle") for issue in Check(list(reversed(rotated)))), angle
    # A real correction is perpendicular through the moving wall's own near end.
    almost = [WallDiagnosticRecord(1, 1, (0, 0), (1000, 0), 120),
              WallDiagnosticRecord(2, 2, (.005, .005), (5.005, 1000.005), 120)]
    right = next(issue for issue in Check(almost) if issue["code"].startswith("potential:right-angle"))
    assert right["repair"] == ((2, 1, (.005, 1000.005)),)
    # Actual flat.plan drift crossed the old .01 cutoff solely through rounding.
    for offset in (.010000000000062, .1):
        assert not any(issue["code"] == "potential:axis" for issue in Check([
            WallDiagnosticRecord(5, 5, (0, -5), (-3360, -5 - offset), 120)]))
    assert any(issue["code"] == "potential:axis" for issue in Check([
        WallDiagnosticRecord(5, 5, (0, -5), (-3360, -5.100001), 120)]))
    for gap, expected in ((.09, False), (.1, False), (.11, True)):
        issues = Check([WallDiagnosticRecord(1, 1, (0, 0), (1000, 0), 120),
                        WallDiagnosticRecord(2, 2, (1000 + gap, 0), (2000, 0), 120)])
        gaps = [issue for issue in issues if issue["code"].startswith("potential:gap")]
        assert bool(gaps) == expected, gap
        if gaps:
            assert "0.11 mm apart" in gaps[0]["description"]
    assert FormatLength(.01, "Millimeters", decimals = 4) == "0 mm"
    assert FormatLength(.01, "Millimeters", decimals = 4, preserveDecimals = True) == "0.01 mm"
    assert FormatLength(.01, "Inches", decimals = 4, preserveDecimals = True) == '0.0004"'
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: true wall directions, anchored repairs, rotated/translated junctions, sub-tenth-mm noise and precise diagnostic text")


if __name__ == "__main__":
    if "--without-qt" in sys.argv:
        CheckWithoutQt()
    else:
        result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"], capture_output = True, text = True, timeout = 10)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout.strip())
