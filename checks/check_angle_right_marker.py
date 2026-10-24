"""Right-angle markers use exact geometry and remain consistent across rotations and zoom."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.angle_guide import AngleGuideLayout


def Main():
    app = QtWidgets.QApplication([])
    metrics = QtGui.QFontMetricsF(app.font())
    point = QtCore.QPointF
    middle = point(35, 70)
    for rotation in (0, 27, 90, 163, 270):
        radians = math.radians(rotation)
        firstDirection = point(math.cos(radians), math.sin(radians))
        for side in (-1, 1):
            lastDirection = point(-firstDirection.y(), firstDirection.x()) * side
            for length in (50, 200, 900):
                first = middle + firstDirection * length
                last = middle + lastDirection * length * 2
                path, rect, label, anchor = AngleGuideLayout(first, middle, last, metrics)
                corner = middle + (firstDirection + lastDirection) * 12
                assert label == "90°" and QtCore.QLineF(anchor, corner).length() < 1e-8
                assert not any(path.elementAt(index).isCurveTo() for index in range(path.elementCount()))
                for selected in (False, True):
                    offset = point(80, -45)
                    shiftedPath, shiftedRect, _, shiftedAnchor = AngleGuideLayout(
                        first, middle, last, metrics, textOffset = offset, drawArms = selected)
                    assert QtCore.QLineF(shiftedRect.center(), rect.center() + offset).length() < 1e-8
                    assert shiftedAnchor == anchor
                    assert not any(shiftedPath.elementAt(index).isCurveTo() for index in range(shiftedPath.elementCount()))
    # Display rounding must not turn a non-right angle into a square.
    for degrees in (89.96, 90.04, 89.999999, 90.000001, 45, 135):
        radians = math.radians(degrees)
        path, _, label, _ = AngleGuideLayout(middle + point(200, 0), middle,
                                            middle + point(math.cos(radians), math.sin(radians)) * 200, metrics)
        assert any(path.elementAt(index).isCurveTo() for index in range(path.elementCount())), degrees
        if abs(degrees - 90) < .05:
            assert label == "90°"
    # Short arms cap the marker; collapsed arms still have no marker or label.
    _, _, _, anchor = AngleGuideLayout(middle + point(15, 0), middle, middle + point(0, 15), metrics)
    assert anchor == middle + point(7, 7)
    path, _, label, anchor = AngleGuideLayout(middle, middle, middle + point(0, 100), metrics)
    assert path.isEmpty() and label == "" and anchor is None
    print("PASS: exact right-angle square, rotated/reversed arms, fixed screen size, short arms, label offset and near-right arcs")


if __name__ == "__main__":
    Main()
