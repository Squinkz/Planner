"""Detached construction rules and project binding plans without Qt."""
import copy
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.model_construction import (PlanObjectConstruction, PlanProjectMemberships,
        PlanProjectOpening, PlanCompoundFallback, PlanSelectionOpeningFields)
    wall = dict(type = "Wall", first = [0, 0], second = [100, 0], width = 240,
                firstMiter = .2, secondMiter = .4, material = "Generic", id = 7)
    materials, units, weights = {"Generic"}, {"Millimeters"}, {"Objects"}
    before = copy.deepcopy(wall)
    plan = PlanObjectConstruction(wall, materials, units, weights)
    assert plan.kind == "Wall" and plan.category == "walls" and plan.width == 240.
    assert plan.first == (0., 0.) and plan.fields["measurementHidden"] is False and wall == before
    label = dict(type = "RoomLabel", first = [0, 0], second = [1e-8, 0], width = 1e-8,
                 text = "Room", unitsOverride = "Millimeters")
    plan = PlanObjectConstruction(label, materials, units, weights)
    assert plan.category == "labels" and plan.fields["unitsOverride"] == "Millimeters"
    furnishing = dict(wall, type = "Furnishing", definition = "portable", flipHorizontal = True)
    assert PlanObjectConstruction(furnishing, materials, units, weights).fields["flipHorizontal"] is True
    arrow = dict(wall, type = "Arrow", solidTip = True, tipSize = 2, intensity = 1)
    assert PlanObjectConstruction(arrow, materials, units, weights).fields["tipSize"] == 480
    angle = dict(wall, type = "AngleGuide", width = 0, second = [0, 0], middle = [10, 20], textOffset = [3, 4])
    assert PlanObjectConstruction(angle, materials, units, weights).points["middleVertex"] == (10., 20.)
    pasted = PlanObjectConstruction(angle, materials, units, weights, placement = ((5, 6), (5, 6), 0), delta = (5, 6))
    assert pasted.points == dict(textOffset = (3, 4), middleVertex = (15, 26))
    for invalid in (dict(wall, width = True), dict(wall, width = 0), dict(wall, firstMiter = 2),
            dict(wall, second = [0, 0]), dict(label, unitsOverride = "unknown"), dict(label, intensity = 2),
            dict(furnishing, flipHorizontal = 1), dict(wall, type = "Stair", directionReversed = False, manualStepCount = 100001),
            dict(wall, type = "Railing", manualPostCount = 1), dict(angle, middle = [float("nan"), 0])):
        try:
            PlanObjectConstruction(invalid, materials, units, weights)
        except ValueError:
            pass
        else:
            raise AssertionError(invalid)
    records = [wall, dict(label, id = 9)]
    membership = dict(groups = [[1, 0]], hidden = [1])
    assert PlanProjectMemberships(records, [0, 1], membership) == ([(0, 7), (1, 9)], [(1, 0)], [1], {7, 9})
    for badRecords, badScene in (([wall, dict(label, id = 7)], membership), (records, dict(groups = [[0, 0]], hidden = [])),
            (records, dict(groups = [[0, 1], [1, 0]], hidden = [])), (records, dict(groups = [], hidden = [True])),
            (records, dict(groups = [], hidden = [1, 1]))):
        try:
            PlanProjectMemberships(badRecords, [0, 1], badScene)
        except ValueError:
            pass
        else:
            raise AssertionError((badRecords, badScene))
    opening = dict(type = "Fireplace", center = .5, length = 600, depth = 100, depthOffset = 300,
                   swingsOutwards = False, geometryIssues = ["fireplace_bounds"])
    recovered = PlanProjectOpening(opening, 2000, 240, "Generic", materials)
    assert recovered.firstFraction == .35 and recovered.secondFraction == .65
    assert recovered.fields["manualDepth"] == 100 and recovered.fields["manualDepthOffset"] == 300
    assert recovered.fields["material"] == "Generic"
    relaxed = PlanProjectOpening(dict(opening, geometryIssues = []), 2000, 240, "Generic", materials, validatePlacement = False)
    assert relaxed.fields["manualDepth"] == 100 and relaxed.fields["manualDepthOffset"] == 300
    casement = PlanProjectOpening(dict(type = "CasementWindow", center = .5, length = 600, swingsOutwards = True),
                                 2000, 240, "Generic", materials)
    assert "hingeAtSecond" not in casement.fields and casement.fields["wellDepth"] == 600
    selection = dict(swingsOutwards = 1, depth = 400, depthOffset = 80 + 1e-8,
                     material = "Generic", measurementFlipped = 0)
    selectedFields = PlanSelectionOpeningFields(selection, "Fireplace", 240)
    assert selectedFields["swingsOutwards"] is True and selectedFields["measurementFlipped"] is False
    assert selectedFields["depthOffset"] == 80 + 1e-8
    for badSelection in (dict(selection, depth = 239), dict(selection, depthOffset = 80 + 2e-8),
                         dict(selection, depth = float("inf"))):
        try:
            PlanSelectionOpeningFields(badSelection, "Fireplace", 240)
        except ValueError:
            pass
        else:
            raise AssertionError(badSelection)
    child = dict(type = "Furnishing", definition = "leaf", first = [0, 0], second = [100, 0], width = 100)
    nested = dict(child, definition = "missing", children = [child, dict(child, definition = "unknown", flipVertical = True)])
    plans, count, nextId = PlanCompoundFallback(nested, {"leaf"}, 2, 10)
    assert count == 4 and nextId == 12 and [plan.fields["objectId"] for plan in plans] == [10, 11]
    assert plans[1].fields["definitionKey"] == "unknown" and plans[1].fields["flipVertical"]
    # Known definitions terminate recursion, so malformed serialized children are ignored.
    assert len(PlanCompoundFallback(dict(child, children = None), {"leaf"}, 1, 1)[0]) == 1
    deep = child
    for index in range(64):
        deep = dict(nested, children = [deep])
    for badRoot, count in ((dict(nested, children = []), 0), (dict(child, second = [0, 0]), 0),
                           (dict(child, flipHorizontal = 1), 0), (child, 100000), (deep, 0)):
        try:
            PlanCompoundFallback(badRoot, {"leaf"}, count, 1)
        except ValueError:
            pass
        else:
            raise AssertionError((badRoot, count))
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: portable construction inputs, validation modes, defaults, translated angle fields and ID/group/hidden binding without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
