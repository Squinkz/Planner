"""Wall heuristics and invalid-dimension repair proposals without Qt."""
import copy
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.wall_diagnostics import WallDiagnosticRecord, PlanPotentialWallRepairs
    from planner_app.record_repairs import ProposeOpeningGeometry, ProposeObjectGeometry, GeometryRepairText
    from planner_app.record_validation import Finite
    from planner_app.coincident_records import GroupCoincidentRecords, PlanCoincidentRemoval
    walls = [WallDiagnosticRecord(101, 1, (0, 0), (2000, 4), 120),
             WallDiagnosticRecord(102, 2, (2000, 4), (2004, 2000), 120),
             WallDiagnosticRecord(103, 3, (2006, 2000), (4000, 2000), 120)]
    before = copy.deepcopy(walls)
    issues = PlanPotentialWallRepairs(iter(walls), 100, (0, 0), "Millimeters")
    assert {issue["code"].split(":")[1] for issue in issues} == {"axis", "grid", "right-angle", "gap"}
    first = next(issue for issue in issues if issue["code"] == "potential:axis" and issue["object"] == 101)
    assert first["repair"] == ((101, 0, (0, 4)),)
    # Golden fingerprints from the original Qt implementation preserve saved ignores.
    assert first["fingerprint"] == "fb27ad0abc403e551ee61312d4046dd89ad0a7550f6655de9177a3d815dc322f"
    right = next(issue for issue in issues if issue["code"].startswith("potential:right-angle"))
    assert right["fingerprint"] == "dca900ebca58fd53d919d7878f8ebc7891e927705a028de9dae4a07209127d19"
    gap = next(issue for issue in issues if issue["code"].startswith("potential:gap"))
    assert gap["repair"] == ((103, 0, (2004, 2000)),)
    remapped = [WallDiagnosticRecord(wall.key + 1000, wall.objectId, wall.first, wall.second, wall.width) for wall in walls]
    again = PlanPotentialWallRepairs(remapped, 100, (0, 0), "Millimeters")
    assert [issue["fingerprint"] for issue in issues] == [issue["fingerprint"] for issue in again]
    assert walls == before
    assert PlanPotentialWallRepairs([WallDiagnosticRecord(1, 1, (0, 0), (2000, 0), 120)], 100, (0, 0), "Millimeters") == []
    assert PlanPotentialWallRepairs([WallDiagnosticRecord(1, 1, (0, 0), (.5, 0), 120),
                                     WallDiagnosticRecord(2, 2, (float("nan"), 0), (1000, 0), 120)], 100, (0, 0), "Millimeters") == []
    assert not Finite(True) and not Finite(float("inf")) and Finite(120)

    definitions = {"null": {"width": 200}}
    wall = dict(type = "Wall", first = [0, 0], second = [1000, 0], width = 120, firstMiter = 0, secondMiter = 0)
    assert ProposeObjectGeometry(wall, 240, definitions) is None
    invalid = dict(wall, first = ["bad", float("inf")], second = None, width = -1, firstMiter = 2)
    original = copy.deepcopy(invalid)
    repaired = ProposeObjectGeometry(invalid, 240, definitions)
    assert (repaired["first"], repaired["second"], repaired["width"], repaired["firstMiter"]) == ([0, 0], [1000, 0], 240, 0)
    assert invalid == original
    edge = dict(wall, first = [1e12, 50], second = [1e12, 50])
    assert ProposeObjectGeometry(edge, 240, definitions)["second"] == [1e12 - 1000, 50]
    label = dict(type = "Label", first = [0, 0], second = [.01, 0], width = .001)
    assert ProposeObjectGeometry(label, 240, definitions) is None
    opening = dict(type = "Window", center = "bad", length = -1, wellDepth = None)
    proposal = ProposeOpeningGeometry(opening, 120, 500)
    assert proposal["code"] == "dimensions" and proposal["repair"]["center"] == .5
    assert proposal["repair"]["length"] == 500 and proposal["repair"]["wellDepth"] == 600
    assert ProposeOpeningGeometry(opening, 120, .5)["repair"] is None
    fireplace = dict(type = "Fireplace", center = .5, length = 500, depth = 60, depthOffset = 50)
    proposal = ProposeOpeningGeometry(fireplace, 120, 2000)
    assert proposal["code"] == "fireplace_bounds" and proposal["highlight"]
    assert proposal["repair"]["depth"] == 120 and proposal["repair"]["depthOffset"] == 0
    assert ProposeOpeningGeometry(dict(fireplace, geometryIssues = ["fireplace_bounds"]), 120, 2000) is None
    assert GeometryRepairText(wall, dict(wall, width = 240)) == "Repair will set:\nWidth: 240 mm"
    a, b, c = object(), object(), object()
    firstRecord = dict(wall, id = 1, measurementHidden = True)
    secondRecord = dict(wall, id = 2, measurementHidden = False, measurementFlipped = True)
    unchanged = copy.deepcopy((firstRecord, secondRecord))
    groups = GroupCoincidentRecords([(a, firstRecord), (b, secondRecord), (c, dict(wall, width = 240))])
    assert groups == [(a, b)] and (firstRecord, secondRecord) == unchanged
    assert GroupCoincidentRecords([(a, ("Furnishing", "desk", 1)), (b, ("Furnishing", "desk", 1))]) == [(a, b)]
    owned = dict(wall, id = 1)
    GroupCoincidentRecords([(a, owned)], consumeRecords = True)
    assert "id" not in owned
    calls = []
    def Visible(obj):
        calls.append(obj)
        return obj is b
    assert PlanCoincidentRemoval([(a, b, c)], Visible, selectedIds = {id(b)}) == {id(a): b, id(c): b}
    assert calls == [a, b]  # Keep the original lazy visibility query behavior.
    calls.clear()
    assert PlanCoincidentRemoval([(a, b, c)], Visible, selectedIds = {id(a)}) == {} and calls == []
    assert PlanCoincidentRemoval([(a, b)], lambda obj: False) == {id(b): a}
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: wall proposals, stable ignore fingerprints and dimension recovery plans without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
