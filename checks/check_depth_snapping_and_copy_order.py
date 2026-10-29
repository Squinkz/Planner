"""Depth tips snap during translation; Shift copies preserve furnishing stacking."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore
from planner_app.models import MeasurementGuide, Wall, Arrow, Furnishing
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_history import Drag


def Main():
    point = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.connectedEnabled = False
        v.snapEnabled = v.vertexSnapEnabled = True
        v.cornerSnapEnabled = v.gridSnapEnabled = v.alignmentSnapEnabled = v.midpointSnapEnabled = False
        for depth in (500, -500):
            for grouped in (False, True):
                guide = MeasurementGuide(point(-1000, 0), point(1000, 0), depth = depth)
                target = Wall(point(2000, -depth), point(3500, -depth), 200)
                other = Arrow(point(-2000, -1500), point(-1000, -1500))
                InstallScene(main, [guide, target] + ([other] if grouped else []))
                tips = v.GuideDepthEndpoints(guide)
                assert tips == (point(-1000, -depth), point(1000, -depth))
                assert all(tip in list(v.SnapVertices()) for tip in tips)
                v.hiddenObjectIds = {id(guide)}
                assert all(tip not in list(v.SnapVertices()) for tip in tips)
                v.hiddenObjectIds = set()
                v.SetSelection([(guide, None)] + ([(other, None)] if grouped else []))
                grab = point(-500, 0)
                Drag(v, v.WorldToViewport(grab).toPoint(), v.WorldToViewport(grab + point(980, 20)).toPoint())
                assert v.GuideDepthEndpoints(guide)[1] == target.firstVertex, (depth, grouped, guide.firstVertex)
                v.Undo()
                assert guide.firstVertex == point(-1000, 0)
        # A stationary tip is also a target when another guide endpoint moves.
        guide = MeasurementGuide(point(-1000, 0), point(1000, 0), depth = 500)
        moving = MeasurementGuide(point(-2000, -1000), point(-2000, -2000))
        InstallScene(main, [guide, moving])
        tip = v.GuideDepthEndpoints(guide)[0]
        v.SetSelection([(moving, 0)])
        Drag(v, v.WorldToViewport(moving.firstVertex).toPoint(), v.WorldToViewport(tip + point(20, 20)).toPoint())
        assert moving.firstVertex == tip
        guide.depth = 0
        assert v.GuideDepthEndpoints(guide) == ()
        # Reverse the selection relative to scene order to reproduce the bug.
        for behind in (False, True):
            rear = Furnishing(v.furnishingDefinitions["desk"])
            rear.firstVertex, rear.secondVertex = point(-400, -400), point(-400, 400)
            rear.width, rear.behindCounters = 800, behind
            front = rear.Clone()
            front.firstVertex += point(300, 0)
            front.secondVertex += point(300, 0)
            front.behindCounters = False
            InstallScene(main, [rear, front])
            v.snapEnabled = False
            v.SetSelection([(front, None), (rear, None)])
            grab = (front.firstVertex + front.secondVertex) / 2
            Drag(v, v.WorldToViewport(grab).toPoint(), v.WorldToViewport(grab + point(1500, 500)).toPoint(),
                 QtCore.Qt.KeyboardModifier.ShiftModifier)
            assert len(v.furnishings) == 4
            rearCopy, frontCopy = v.furnishings[2:]
            assert rearCopy.firstVertex - rear.firstVertex == frontCopy.firstVertex - front.firstVertex
            assert rearCopy.firstVertex.x() < frontCopy.firstVertex.x(), "Copy order followed selection instead of paint order"
            assert rearCopy.behindCounters == behind and not frontCopy.behindCounters
            v.Undo()
            assert v.furnishings == [rear, front]
            v.Redo()
            assert v.furnishings == [rear, front, rearCopy, frontCopy]
    print("PASS: signed depth-tip snap anchors/targets, hidden tips, group movement, endpoint drag, copy stacking/layers and undo/redo.")


if __name__ == "__main__":
    Main()
