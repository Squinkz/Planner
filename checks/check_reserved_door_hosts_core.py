"""Reserved pocket/barn-door support without Qt, windows or rendering."""
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from planner_app.geometry.reserved_doors import (ReservedDoorSupportBounds, ReservedDoorWallContact,
    ReservedDoorWithinHost, ReservedDoorPlacementBounds, ReservedDoorEditCenter)
from planner_app.geometry.group_movement import GroupOpeningLimits
from planner_app.model_construction import PlanProjectOpening


def Main():
    for angle in (0, .63):
        cosine, sine = math.cos(angle), math.sin(angle)
        for reverse in (False, True):
            points = [(-2000, 0), (0, 0), (2000, 0), (0, 2000), (0, -2000)]
            first, joint, end, branch, crossing = [(x * cosine - y * sine, x * sine + y * cosine) for x, y in points]
            start, finish = (joint, first) if reverse else (first, joint)
            bounds = ReservedDoorSupportBounds(start, finish, [(first, joint), (joint, end)])
            expected = (-1, 1) if reverse else (0, 2)
            assert all(abs(actual - wanted) < 1e-9 for actual, wanted in zip(bounds, expected))
            assert ReservedDoorWallContact(start, finish, 200, joint, branch, bounds) == "branch"
            assert ReservedDoorWallContact(start, finish, 200, crossing, branch, bounds) is None
            assert ReservedDoorWallContact(start, finish, 200, joint, end, bounds) == "collinear"
    assert ReservedDoorSupportBounds((0, 0), (1000, 0), [((1030, 0), (2000, 0))]) == (0, 1)
    assert ReservedDoorWithinHost(2000, 1800, .95, False, (0, 2))
    assert not ReservedDoorWithinHost(2000, 1800, .95, False, (0, 1))
    assert not ReservedDoorWithinHost(2000, 1800, 1.05, False, (0, 2))  # Actual aperture outside parent.
    assert ReservedDoorWithinHost(2000, 1800, .05, True, (-1, 1))
    assert not ReservedDoorWithinHost(2000, 1800, -.05, True, (-1, 1))
    for kind in ("BarnDoor", "PocketDoor"):
        record = dict(type = kind, center = .95, length = 1800, hingeAtSecond = False, swingsOutwards = False)
        plan = PlanProjectOpening(record, 2000, 200, "Generic", {"Generic"}, parkingBounds = (0, 2))
        assert plan.fields["length"] == 1800
        try:
            PlanProjectOpening(record, 2000, 200, "Generic", {"Generic"})
        except ValueError:
            pass
        else:
            raise AssertionError("Unsupported reserved span accepted")
    bounds = ReservedDoorPlacementBounds(2000, 1800, False, (0, 2))
    minimum, maximum = GroupOpeningLimits((1, 0), [(1, (2000, 0), 2000, .95, 1800, None, bounds)], {})
    assert abs(maximum - 100) < 1e-9  # Actual aperture stops at parent's end.
    assert abs(minimum + 1000) < 1e-9
    # Large subdivided supports retain only two scalar results, no membership matrix.
    bounds = ReservedDoorSupportBounds((0, 0), (100, 0), [((index * 100, 0), ((index + 1) * 100, 0)) for index in range(2000)])
    assert bounds == (0, 2000)
    for follow in (False, True):
        center = ReservedDoorEditCenter((-2000, 0), (0, 0), (-2000, 0), (200, 0), .95, follow)
        assert abs(-2000 + 2200 * center + 100) < 1e-8
    assert ReservedDoorEditCenter((-2000, 0), (0, 0), (-1800, 100), (200, 100), .95, True) == .95
    assert ReservedDoorEditCenter((-2000, 0), (0, 0), (-1800, 100), (200, 100), .95, False) is None
    center = ReservedDoorEditCenter((-2000, 0), (0, 0), (-1800, 0), (200, 0), .95, False)
    assert abs(-1800 + 2000 * center + 100) < 1e-8
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: reserved vs actual bounds, branches/crossings, rotations/reversal, gaps, persistence validation and group limits; no Qt")


if __name__ == "__main__":
    Main()
