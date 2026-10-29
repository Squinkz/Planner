"""Exterior dimension room cuts and row compaction without Qt."""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.measurement_stack_layout import StackWall, StackSpan, PlanMeasurementStacks
    wall = StackWall((0, 0), (1000, 0), 100)
    partition = StackWall((500, 0), (500, 1000), 100)
    owners, openingOwners = [object()], [object()]
    total = StackSpan((0, -50), (1000, -50), owners, 100, (0, 0))
    openings = [((100, -50), (200, -50), openingOwners)]
    def RoomAtPoint(point):
        if 50 < point[1] < 950:
            return "left" if point[0] < 450 else "right" if point[0] > 550 else None
        return None
    inner, additional = PlanMeasurementStacks([total], openings, [wall, partition], RoomAtPoint)
    assert [(first[0], second[0]) for first, second, members in inner] == [(0, 100), (100, 200), (200, 450), (450, 550), (550, 1000)]
    assert inner[1][2] is openingOwners
    assert [tier for first, second, members, tier in additional] == [1, 1, 1, 2]
    inner, additional = PlanMeasurementStacks([total], openings, [wall, partition], RoomAtPoint, "Centerline")
    assert [(first[0], second[0]) for first, second, members in inner] == [(0, 100), (100, 200), (200, 500), (500, 1000)]
    assert [tier for first, second, members, tier in additional] == [1, 1, 2]
    # A free stub inside the same room cannot introduce a room division.
    inner, additional = PlanMeasurementStacks([total], [], [wall, partition], lambda point: "one room")
    assert inner == [((0, -50), (1000, -50), owners)] and additional == []
    # Reversed opening spans, repeated stops and first-match owner priority.
    otherOwners = [object()]
    spans = [((200, -50), (100, -50), openingOwners), ((100.005, -50), (200, -50), otherOwners)]
    inner, additional = PlanMeasurementStacks([total], spans, [wall], lambda point: None)
    assert len(inner) == 3 and inner[1][2] is openingOwners and len(additional) == 1
    assert PlanMeasurementStacks([], [], [], lambda point: None) == ([], [])
    assert PlanMeasurementStacks([total], openings, [wall, partition], None) == PlanMeasurementStacks(
        [total], openings, [wall, partition], lambda point: None)
    assert PlanMeasurementStacks([StackSpan((0, 0), (0, 0), owners, 100)], [], [], lambda point: None) == ([], [])
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: room/opening chains, face/centerline references, stub exclusion, stable stop/owner priority and tier compaction without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
