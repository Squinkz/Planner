"""Shift resize preserves object/group centers and can toggle during a drag."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets, QtTest
from planner import MainWindow, Pillar, Column, Wall, Fireplace, Label, NorthArrow
from planner_app.models import Furnishing


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v, point = main.viewport, QtCore.QPointF
    v.snapEnabled = False
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    none = QtCore.Qt.KeyboardModifier.NoModifier
    parent = Wall(point(-2500, 0), point(2500, 0), 240)
    objects = [Furnishing(v.furnishingDefinitions["desk"], point()), Pillar(point(0, -400), point(0, 400), 400),
               Column(point(0, -400), point(0, 400), 400), Fireplace(parent, .38, .62), Label(point()), NorthArrow(point())]
    for obj in objects:
        v.walls = [parent] if isinstance(obj, Fireplace) else [obj] if isinstance(obj, Pillar) else []
        v.windows = [obj] if isinstance(obj, Fireplace) else []
        v.labels = [obj] if isinstance(obj, Label) else []
        v.furnishings = [obj] if isinstance(obj, Furnishing) and not isinstance(obj, Label) else []
        if not isinstance(obj, Fireplace):
            obj.angle = 30
        v.SetSelection([(obj, None)])
        for field in (["corner"] if isinstance(obj, Label) else ["width", "length", "corner"]):
            handle = next(handle for handle in v.FurnishingHandles(obj) if handle[0] == "resize" and handle[1] == field)
            v.BeginFurnishingHandleDrag(obj, handle, handle[3])
            state = v.furnishingHandleDrag
            center = point(state["center"])
            north = state["north"]
            east = point(north.y(), -north.x())
            if field == "corner":
                delta = (east * (handle[2][0] * state["width"]) + north * (handle[2][1] * state["length"])) * .1
            else:
                delta = (east if field == "width" else north) * (handle[2] * state[field] * .1)
            end = handle[3] + v.WorldToViewport(center + delta) - v.WorldToViewport(center)
            for modifiers, centered in ((shift, True), (none, False), (shift, True)):
                v.UpdateFurnishingHandleDrag(end, modifiers)
                actualCenter = (obj.HandleBox().firstVertex + obj.HandleBox().secondVertex) / 2 if isinstance(obj, Fireplace) else (obj.firstVertex + obj.secondVertex) / 2
                assert ((actualCenter - center).manhattanLength() < .001) == centered, (type(obj).__name__, field)
                expectedFactor = 1.2 if centered else 1.1
                actualSize = (obj.depth if field in ("width", "corner") else obj.length) if isinstance(obj, Fireplace) else obj.width if field in ("width", "corner") else obj.length
                originalSize = state["width"] if field in ("width", "corner") else state["length"]
                assert math.isclose(actualSize, originalSize * expectedFactor, abs_tol = .001)
            v.CancelInteraction()
    v.walls, v.windows, v.labels = [], [], []
    first = Furnishing(v.furnishingDefinitions["desk"], point(-800, 0))
    second = Furnishing(v.furnishingDefinitions["desk"], point(800, 300))
    first.angle, second.angle = 25, -40
    v.furnishings = [first, second]
    v.SetSelection([(first, None), (second, None)])
    box = v.FurnishingSelectionBox()
    handle = next(handle for handle in v.FurnishingHandles(box) if handle[:3] == ("resize", "width", 1))
    v.BeginFurnishingHandleDrag(box, handle, handle[3])
    center = point(v.furnishingHandleDrag["center"])
    v.UpdateFurnishingHandleDrag(handle[3] + point(60, 0), shift)
    bounds = v.ObjectFootprint(first)[0].united(v.ObjectFootprint(second)[0])
    assert (bounds.center() - center).manhattanLength() < .001
    v.CancelInteraction()
    # Grid snapping targets the moving half-span while preserving the center.
    v.furnishings = [first]
    first.angle = 0
    first.firstVertex, first.secondVertex, first.width = point(0, -400), point(0, 400), 400
    v.SetSelection([(first, None)])
    v.snapEnabled = v.gridSnapEnabled = True
    v.vertexSnapEnabled = v.midpointSnapEnabled = v.alignmentSnapEnabled = False
    handle = next(handle for handle in v.FurnishingHandles(first) if handle[:3] == ("resize", "width", 1))
    v.BeginFurnishingHandleDrag(first, handle, handle[3])
    v.UpdateFurnishingHandleDrag(handle[3] + point(27, 0), shift)
    step = v.GridSteps()[1]
    assert (first.firstVertex + first.secondVertex).manhattanLength() < .001
    assert abs(first.width / (2 * step) - round(first.width / (2 * step))) < .001
    v.CancelInteraction()
    # Holding Shift before pressing a handle must bypass box selection.
    v.snapEnabled = False
    handle = next(handle for handle in v.FurnishingHandles(first) if handle[:3] == ("resize", "width", 1))
    QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, shift, handle[3].toPoint())
    assert v.furnishingHandleDrag is not None and v.boxStart is None
    end = v.dragStart + point(60, 0)
    v.UpdateInteraction(end, shift)
    assert (first.firstVertex + first.secondVertex).manhattanLength() < .001 and first.width > 400
    QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, shift, end.toPoint())
    assert v.furnishingHandleDrag is None and v.boxStart is None
    main.close()
    print("PASS: Shift side/corner resize, live toggling, rotated objects and group centers")


if __name__ == "__main__":
    Main()
