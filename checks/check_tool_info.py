"""Live two-column tool information for vertices and furnishing/text handles."""
import os
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner_app.viewport.widget import DrawingViewport
from planner_app.models import Wall, Furnishing, Label
from planner_app.units import FormatLength
from planner_app.graphics.text import PathTextPainter


def Main():
    app = QtWidgets.QApplication([])
    v = DrawingViewport()
    v.unitsMode = "Adaptive Metric"
    v.resize(1000, 700)
    v.snapEnabled = False
    texts = []

    class InfoPainter(PathTextPainter):
        def drawText(self, *args):
            if isinstance(args[-1], str):
                texts.append(args[-1])
            return super().drawText(*args)

    p = QtCore.QPointF
    wall = Wall(p(-1500, 0), p(1500, 0), 240)
    v.walls = [wall]
    v.SetSelection([(wall, 0)])
    v.dragStart = p(400, 300)
    with patch("planner_app.viewport.rendering.PathTextPainter", InfoPainter):
        v.grab()
        assert "Length" in texts and "Width" in texts and "3 m" in texts and "24 cm" in texts
        wall.firstVertex = p(-2000, 0)
        texts.clear()
        v.grab()
        assert "3.5 m" in texts
        v.dragStart = None
        v.walls = []
        for item in (Furnishing(v.furnishingDefinitions["desk"], p()), Label(p(), "Room")):
            v.furnishings, v.labels = ([item], []) if not isinstance(item, Label) else ([], [item])
            v.SetSelection([(item, None)])
            handle = next(handle for handle in v.FurnishingHandles(item) if handle[0] == "resize"
                          and (handle[1] == "corner" if isinstance(item, Label) else handle[1] == "width" and handle[2] == 1))
            v.BeginFurnishingHandleDrag(item, handle, handle[3])
            v.UpdateFurnishingHandleDrag(handle[3] + p(40, 0), QtCore.Qt.KeyboardModifier.NoModifier)
            for mode in ("Adaptive Metric", "Meters", "Centimeters", "Millimeters"):
                v.unitsMode = mode
                texts.clear()
                v.grab()
                assert "Width" in texts and "Length" in texts
                assert "Right mouse" in texts and "Cancel" in texts
                assert FormatLength(item.width, mode, adaptive = "cm") in texts
                assert FormatLength(item.length, mode, adaptive = "cm") in texts
            before = v.interactionBefore
            QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.RightButton, pos = handle[3].toPoint())
            QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.RightButton, pos = handle[3].toPoint())
            assert v.furnishingHandleDrag is None and v.dragStart is None
            assert v.CaptureState()[5] == before[5] and v.CaptureState()[8] == before[8]
            handle = next(handle for handle in v.FurnishingHandles(item) if handle[0] == "rotate")
            v.BeginFurnishingHandleDrag(item, handle, handle[3])
            item.angle = 47.25
            texts.clear()
            v.grab()
            assert "Angle" in texts and "47.2" + chr(176) in texts
            assert "Right mouse" in texts and "Cancel" in texts
            assert "Length" not in texts and "Width" not in texts
            before = v.interactionBefore
            QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.RightButton, pos = handle[3].toPoint())
            QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.RightButton, pos = handle[3].toPoint())
            assert v.furnishingHandleDrag is None and v.dragStart is None
            assert v.CaptureState()[5] == before[5] and v.CaptureState()[8] == before[8]
        v.labels = []
        a = Furnishing(v.furnishingDefinitions["desk"], p(-800, 0))
        b = Furnishing(v.furnishingDefinitions["desk"], p(800, 0))
        v.furnishings = [a, b]
        v.SetSelection([(a, None), (b, None)])
        box = v.FurnishingSelectionBox()
        handle = next(handle for handle in v.FurnishingHandles(box) if handle[0] == "rotate")
        v.BeginFurnishingHandleDrag(box, handle, handle[3])
        v.furnishingHandleDrag["object"].angle = 30
        texts.clear()
        v.grab()
        assert "Angle" in texts and "30" + chr(176) in texts
        assert "Right mouse" in texts and "Cancel" in texts
        v.CancelInteraction()
        texts.clear()
        v.grab()
        assert not any(key in texts for key in ("Length", "Width", "Angle"))
    v.close()
    print("PASS: vertex dimensions, furnishing/label resize units, single/group rotation and idle cleanup")


if __name__ == "__main__":
    Main()
