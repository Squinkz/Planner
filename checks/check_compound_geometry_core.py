"""Compound layout, decomposition and collision geometry without Qt."""
import copy
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.compound_furnishings import (CompoundAuthoredBounds, CompoundTransform, ComponentFrame,
        PlanCompoundFootprints, PlanFurnishingParts)
    leaf = dict(key = "leaf", width = 100., length = 200.)
    first = dict(definition = leaf, definitionKey = "portable-leaf", x = -200., y = 0., width = 100., length = 200.,
                 angle = 0., zIndex = 2, flipHorizontal = True)
    second = dict(first, x = 200., zIndex = 1, fixedSize = True, flipHorizontal = False)
    definition = dict(key = "compound", width = 500., length = 200., compoundCenter = (0., 0.), components = [first, second])
    before = copy.deepcopy(definition)
    assert CompoundAuthoredBounds(definition["components"]) == (-250, -100, 250, 100)
    identity = CompoundTransform((0, 0), 0, 500, 200, definition, False, False)
    assert identity == (1, 0, 0, 1, 0, 0)
    footprints = list(PlanCompoundFootprints(definition, identity))
    assert footprints[0][0] == (-250, -100, 100, 200)
    assert footprints[1][0] == (150, -100, 100, 200)
    plans = list(PlanFurnishingParts(definition, identity, False))
    assert [plan[2] for plan in plans] == [(200, 0), (-200, 0)]
    assert plans[0][0] is leaf and plans[0][1] == "portable-leaf"
    assert plans[0][3:6] == (100, 100, 0)
    assert [plan[6] for plan in plans] == [False, True]
    # Fixed-size children shrink uniformly along the most compressed parent
    # axis and never grow. Their positions still follow the full parent frame.
    frame = CompoundTransform((0, 0), 0, 1000, 100, definition, False, False)
    fixed = ComponentFrame(second, frame)
    assert fixed == (.5, 0, 0, .5, 400, 0)
    free = ComponentFrame(second, frame, False)
    assert free == (2, 0, 0, .5, 400, 0)
    mirrored = CompoundTransform((0, 0), 90, 500, 200, definition, True, False)
    for bounds, corners, axes in PlanCompoundFootprints(definition, mirrored):
        assert sum(corners[index][0] * corners[(index + 1) % 4][1] - corners[(index + 1) % 4][0] * corners[index][1]
                   for index in range(4)) > 0
        assert len(axes) == 4 and all(math.isclose(math.hypot(*axis), 1) for axis in axes)
    # A fixed-size ancestor suppresses independent fixed sizing further down.
    nested = dict(key = "nested", width = 500., length = 200., compoundCenter = (0., 0.), components = [second])
    branch = dict(first, definition = nested, width = 250., length = 100., fixedSize = True)
    root = dict(definition, components = [branch])
    assert len(list(PlanCompoundFootprints(root, identity))) == 1
    assert list(PlanFurnishingParts(root, identity, True))[0][0] is nested
    assert definition == before
    try:
        CompoundAuthoredBounds([])
    except ValueError:
        pass
    else:
        raise AssertionError("empty authored layouts must be rejected")
    cyclic = dict(definition)
    cyclic["components"] = [dict(first, definition = cyclic)]
    for function, arguments in ((PlanCompoundFootprints, (cyclic, identity)), (PlanFurnishingParts, (cyclic, identity, False))):
        try:
            list(function(*arguments))
        except ValueError:
            pass
        else:
            raise AssertionError("cyclic compounds must be rejected")
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: affine layouts, stable paint order, mirrored winding, fixed-size ancestry, identity and graph limits without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
