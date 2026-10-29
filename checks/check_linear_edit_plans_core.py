"""Linear command proposals preserve endpoints, miters and opening fractions without Qt."""
import copy
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.linear_edits import PlanSubdivision, PlanDissolution
    segments = [(1, (-1000, 0), (1000, 0), .2, .4, .25), (2, (0, 0), (0, 1000), .1, .3, .5)]
    openings = [(10, 1, .125), (11, 1, .5), (12, 1, .25), (13, 2, .75), (14, 99, .5)]
    before = copy.deepcopy((segments, openings))
    halves, moves = PlanSubdivision(iter(segments), iter(openings))
    assert halves[1] == (((-1000, 0), (-500, 0), .2, 0), ((-500, 0), (1000, 0), 0, .4), .25)
    assert halves[2] == (((0, 0), (0, 500), .1, 0), ((0, 500), (0, 1000), 0, .3), .5)
    assert moves == [(10, 1, 0, .5), (11, 1, 1, 1 / 3), (12, 1, 0, 1), (13, 2, 1, .5)]
    # Reattachment must preserve the original world position in either half.
    for key, parent, half, fraction in moves:
        original = next(record for record in segments if record[0] == parent)
        center = next(record[2] for record in openings if record[0] == key)
        first, second = original[1:3]
        newFirst, newSecond = halves[parent][half][:2]
        for index in (0, 1):
            oldPosition = first[index] + (second[index] - first[index]) * center
            newPosition = newFirst[index] + (newSecond[index] - newFirst[index]) * fraction
            assert math.isclose(oldPosition, newPosition, abs_tol = 1e-9)
    assert (segments, openings) == before
    assert PlanSubdivision([], openings) == ({}, [])
    for invalid in ((3, (0, 0), (0, 0), 0, 0, .5), (3, (0, 0), (1, 0), 0, 0, 0),
                    (3, (0, 0), (1, 0), 0, 0, 1), (3, (0, 0), (1, 0), 0, 0, float("nan"))):
        try:
            PlanSubdivision(segments + [invalid], openings)
        except ValueError:
            pass
        else:
            raise AssertionError(invalid)
        assert (segments, openings) == before

    for reverseSource in (False, True):
        for reverseOther in (False, True):
            source = ((0, 0), (-1000, 0), .2, .4) if reverseSource else ((-1000, 0), (0, 0), .2, .4)
            other = ((1000, 0), (0, 0), .7, .8) if reverseOther else ((0, 0), (1000, 0), .7, .8)
            first, second, firstMiter, secondMiter, direction, length = PlanDissolution((0, 0), source, other)
            outerMiter = .7 if reverseOther else .8
            if reverseSource:
                assert (first, second, firstMiter, secondMiter) == ((1000, 0), (-1000, 0), outerMiter, .4)
            else:
                assert (first, second, firstMiter, secondMiter) == ((-1000, 0), (1000, 0), .2, outerMiter)
            assert direction == (second[0] - first[0], second[1] - first[1]) and length == 2000
    try:
        PlanDissolution((0, 0), ((-1000, 0), (0, 0), 0, 0), ((0, 0), (-1000, 0), 0, 0))
    except ValueError as error:
        assert str(error) == "Cannot dissolve: the new object would have zero length."
    else:
        raise AssertionError("A zero-length dissolution must not produce a plan.")
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: linear split/dissolve plans, all endpoint orientations, miters and opening reattachments without Qt")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())
    import os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore
    from fixtures.parity_examples import ExampleWindow, InstallScene
    from planner_app.models import Wall, Door, Fireplace, MeasurementGuide
    with ExampleWindow() as (main, folder):
        v = main.viewport
        p = QtCore.QPointF
        v.groupModeEnabled = False
        wall = Wall(p(-3000, 0), p(3000, 0), 120, .2, .4)
        door = Door(wall, .1, .2)
        fireplace = Fireplace(wall, .7, .8)
        fireplace.depth, fireplace.depthOffset = 600, 150
        guide = MeasurementGuide(p(0, 3000), p(1000, 3000))
        InstallScene(main, [wall, door, fireplace, guide])
        v.objectGroups = [(wall, guide)]
        positions = [(obj, p(obj.firstVertex), p(obj.secondVertex)) for obj in (door, fireplace)]
        assert v.SubdivideWalls([wall])
        first, second = v.walls[:2]
        assert first.secondVertex == second.firstVertex == p()
        assert (first.firstMiter, first.secondMiter, second.firstMiter, second.secondMiter) == (.2, 0, 0, .4)
        assert door.parentWall is first and fireplace.parentWall is second
        assert v.objectGroups == [(first, second, guide)] and fireplace.depthOffset == 150
        for obj, a, b in positions:
            assert QtCore.QLineF(obj.firstVertex, a).length() < 1e-8
            assert QtCore.QLineF(obj.secondVertex, b).length() < 1e-8
        v.Undo()
        assert v.walls == [wall, guide] and door.parentWall is fireplace.parentWall is wall
        v.Redo()
        assert door.parentWall is first and fireplace.parentWall is second
        assert main.SaveProject(folder / "split.plan") and main.OpenProject(folder / "split.plan")
        assert len(v.walls) == 3 and len(v.windows) == 2
        main.MarkProjectClean()


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
