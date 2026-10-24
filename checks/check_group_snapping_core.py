"""Exact indexed constrained snapping versus the frozen full sweep."""
import math
import os
from pathlib import Path
import random
import subprocess
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))


def CheckWithoutQt():
    from check_geometry_core import CheckWithoutQt as CheckPrimitives
    CheckPrimitives()
    from planner_app.geometry.snapping import PrepareRayTargets, SnapPoint
    targets = [(1000, 92, False), (54, 1000, False), (1000, 88, False)]
    # Y entered the original alignment dictionary first, before its later
    # improvement tied X. Winning-target order alone must not select X.
    assert SnapPoint((60, 80), targets, 1, 14, True, None, (0, 0), (.6, .8),
                     rayTargets = PrepareRayTargets(targets)) == ((66, 88), True, 1, [(1, 88)])
    repeated = targets * 20
    assert SnapPoint((60, 80), repeated, 1, 14, True, None, (0, 0), (.6, .8),
                     rayTargets = PrepareRayTargets(repeated)) == ((66, 88), True, 1, [(1, 88)])
    assert PrepareRayTargets([(float("nan"), 0, True)]) is None
    print("PASS: prepared ray targets and tie-preserving snaps without Qt/site packages")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtWidgets
    from planner_app.geometry.snapping import PrepareRayTargets, SnapPoint
    from planner_app.viewport.widget import DrawingViewport
    from planner_app.models import Wall, Window, Door, Fireplace, SlidingDoor
    from fixtures.qt_group_snapping_reference_20261016 import SnapPoint as FrozenSnapPoint, ReferenceSnapping
    r = random.Random(211839)
    for case in range(2400):
        offset = (1e8, -1e8) if case % 5 == 0 else (0, 0)
        angle = case * .137
        directions = ((1, 0), (0, -1), (.6, .8), (math.cos(angle), math.sin(angle)),
                      (math.sqrt(1 - 4e-20), 2e-10), (1, 5e-11), (1, -1.1e-10), (2, 1))
        direction = directions[case % len(directions)]
        anchor = offset[0] + r.uniform(-100, 100), offset[1] + r.uniform(-100, 100)
        along = r.uniform(-100, 1000)
        offRay = 0 if case % 3 else r.uniform(-80, 80)
        position = (anchor[0] + direction[0] * along - direction[1] * offRay,
                    anchor[1] + direction[1] * along + direction[0] * offRay)
        targets = [(offset[0] + r.uniform(-1000, 1800), offset[1] + r.uniform(-1000, 1800), bool(i % 3)) for i in range(case % 127)]
        for index in range(8):
            t = along + (index - 4) * 10
            cross = (.009999, .01, .010001, 0)[index % 4]
            targets.append((anchor[0] + direction[0] * t - direction[1] * cross,
                            anchor[1] + direction[1] * t + direction[0] * cross, bool(case % 4)))
        if case % 2 == 0:
            targets += [(targets[0][0], y, False) for x, y, direct in targets[:12]]
            targets += targets[:10]
        scale = (.0001, .01, .03, .2, 1, 12, 1e4)[case % 7]
        arguments = (position, targets, scale, (0, 14, 20)[case % 3], bool(case % 4),
                     None if case % 2 else 25.4, anchor, direction)
        expected = FrozenSnapPoint(*arguments)
        actual = SnapPoint(*arguments, rayTargets = PrepareRayTargets(targets))
        assert actual == expected, ("ray", case, actual, expected)

    for scale in (1e-320, 1e-300, .03, 1, 1e300):
        for offset in (0, 1e12, 1e16, 1e300):
            for direction in ((1, 0), (.6, .8), (1, 1.1e-10), (2, 1)):
                targets = [(offset + value, -offset + other, bool(i % 2))
                           for i, (value, other) in enumerate(((0, 0), (10, 0), (0, 10), (100, 100), (-100, -100)))]
                for direct in (False, True):
                    data = [(x, y, direct) for x, y, flag in targets]
                    args = ((offset, -offset), data, scale, 14, True, None, (offset, -offset), direction)
                    assert SnapPoint(*args, rayTargets = PrepareRayTargets(data)) == FrozenSnapPoint(*args), ("extreme", scale, offset, direction)
    for bad in (float("nan"), float("inf"), -float("inf")):
        targets = [(1, 2, True), (bad, 3, False), (3, bad, True)]
        args = ((0, 0), targets, 1, 14, True, None, (0, 0), (1, 0))
        assert SnapPoint(*args, rayTargets = PrepareRayTargets(targets)) == FrozenSnapPoint(*args)

    class ReferenceViewport(DrawingViewport):
        SnapPosition = ReferenceSnapping.SnapPosition
        SnapObjectMovement = ReferenceSnapping.SnapObjectMovement

    app = QtWidgets.QApplication([])
    p = QtCore.QPointF
    actual, reference = DrawingViewport(), ReferenceViewport()
    modifier = QtCore.Qt.KeyboardModifier
    for case in range(160):
        targets = [p((i * 137) % 4000, (i * 73) % 3000) for i in range(120)]
        anchors = [p(i * 83, i * 29) for i in range(5 + case % 8)]
        axis = p(math.cos(case * .13), math.sin(case * .13))
        values = []
        for view in (actual, reference):
            view.snapEnabled, view.midpointSnapEnabled = bool(case % 4), bool(case % 2)
            view.vertexSnapEnabled, view.alignmentSnapEnabled, view.gridSnapEnabled = bool(case % 3), bool(case % 5), bool(case % 7)
            # The frozen collector retains disabled alignment targets; compare
            # enabled pools here and cover filtering in check_corner_snapping.
            view.vertexSnapEnabled = view.cornerSnapEnabled = True
            view.unitsMode = "Feet and Inches" if case % 3 else "Millimeters"
            view.zoom = (.03, .6, 2)[case % 3]
            value = view.SnapObjectMovement(anchors, p(47 + case, -31 + case),
                modifier.AltModifier if case % 7 == 0 else modifier.ControlModifier if case % 2 else modifier.NoModifier,
                snapTargets = targets, travelDirection = axis if case % 3 else None)
            values.append(((value.x(), value.y()), view.snapApplied, view.snapPriority, view.alignmentGuides))
        assert values[0] == values[1], ("movement", case, values)

    def Setup(view, case):
        view.CancelInteraction()
        axis = p(math.cos(case * .17), math.sin(case * .17))
        normal = p(-axis.y(), axis.x())
        offset = p(1e8, -1e8) if case % 6 == 0 else p()
        view.walls = [Wall(offset + normal * i * 2000, offset + normal * i * 2000 + axis * 8000, 240) for i in range(12)]
        types = (Window, Door, Fireplace, SlidingDoor)
        view.windows = [types[(i + case) % 4](wall, .3, .45) for i, wall in enumerate(view.walls)]
        view.windows += [Window(wall, .75, .85) for wall in view.walls]
        view.furnishings, view.labels = [], []
        view.hiddenObjectIds = {id(view.windows[-1])} if case % 2 else set()
        view.connectedEnabled = False
        view.snapEnabled, view.midpointSnapEnabled = True, bool(case % 3)
        view.vertexSnapEnabled, view.alignmentSnapEnabled, view.gridSnapEnabled = bool(case % 2), bool(case % 4), bool(case % 5)
        view.vertexSnapEnabled = view.cornerSnapEnabled = True
        view.unitsMode = "Feet and Inches" if case % 3 else "Millimeters"
        view.zoom = (.2, .6, 2)[case % 3]
        view.SetSelection([(opening, None) for opening in view.windows[:6]])
        view.interactionBefore = view.CaptureState()
        view.dragStart, view.isDragging = p(300, 300), True
        view.StartGroupDrag()

    def Snapshot(view):
        return ([(o.centerFraction, o.length, view.walls.index(o.parentWall)) for o in view.windows],
                [(o.firstVertex.x(), o.firstVertex.y(), o.secondVertex.x(), o.secondVertex.y()) for o in view.walls],
                list(view.alignmentGuides), view.snapApplied, view.snapPriority, len(view.dragCopies))

    for case in range(48):
        for view in (actual, reference):
            Setup(view, case)
        for frame in range(4):
            mods = modifier.ShiftModifier if frame == 1 and case % 3 == 0 else modifier.AltModifier if frame == 2 else modifier.NoModifier
            for view in (actual, reference):
                position = view.WorldToViewport(view.ViewportToWorld(view.dragStart) + p(350 + frame * 500, 110))
                view.UpdateGroupDrag(position, mods)
            assert Snapshot(actual) == Snapshot(reference), ("group", case, frame)
    print("PASS: 2400 exact ray snaps, 160 extreme numeric cases, nonfinite fallback, 160 movements and 192 group frames; Qt-free core")
    actual.close()
    reference.close()


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
