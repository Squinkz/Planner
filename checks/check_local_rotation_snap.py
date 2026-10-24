"""Rotation snap origins use the captured angle in local transform mode."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Furnishing


def Main():
    point = QtCore.QPointF
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    with ExampleWindow() as (main, folder):
        v = main.viewport
        for local in (False, True):
            for initial, turn in ((17, 23), (17, 4), (37, -23), (350, 23)):
                for duplicate in (False, True):
                    desk = Furnishing(v.furnishingDefinitions["desk"])
                    desk.angle = initial
                    InstallScene(main, [desk])
                    v.localTransforms = local
                    v.snapEnabled = True
                    v.SetSelection([(desk, None)])
                    v.rotationPivot = point(-500, 300)
                    handle = next(handle for handle in v.FurnishingHandles(desk) if handle[0] == "rotate")
                    v.BeginFurnishingHandleDrag(desk, handle, handle[3])
                    state = v.furnishingHandleDrag
                    offset = v.ViewportToWorld(handle[3]) - state["pivot"]
                    radians = math.radians(turn)
                    target = v.WorldToViewport(state["pivot"] + point(
                        offset.x() * math.cos(radians) - offset.y() * math.sin(radians),
                        offset.x() * math.sin(radians) + offset.y() * math.cos(radians)))
                    modifiers = ctrl | QtCore.Qt.KeyboardModifier.ShiftModifier if duplicate else ctrl
                    v.UpdateFurnishingHandleDrag(target, modifiers)
                    result = state["object"]
                    origin = initial if local else 0
                    expected = origin + round((initial + turn - origin) / 15) * 15
                    assert abs((result.angle - expected + 180) % 360 - 180) < 1e-7, (local, initial, turn, result.angle, expected)
                    # Repeated frames must keep the drag-start origin, not move it
                    # to the previous frame's angle. Free rotation still uses Alt.
                    v.UpdateFurnishingHandleDrag(target, modifiers)
                    assert abs((result.angle - expected + 180) % 360 - 180) < 1e-7
                    v.UpdateFurnishingHandleDrag(target, modifiers | QtCore.Qt.KeyboardModifier.AltModifier)
                    assert abs((result.angle - initial - turn + 180) % 360 - 180) < 1e-7
                    if duplicate:
                        assert abs((desk.angle - initial + 180) % 360 - 180) < 1e-7
                    v.CancelInteraction()
                    assert len(v.furnishings) == 1
                    assert abs((desk.angle - initial + 180) % 360 - 180) < 1e-7
    print("Local/global rotation snap origins, repeated frames, wraparound, pivots and copies passed")


if __name__ == "__main__":
    Main()
