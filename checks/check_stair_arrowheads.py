"""Stair arrowheads have fixed geometry regardless of run, width or landings."""
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from planner_app.graphics.symbols import DrawStairSymbol


class LineRecorder:
    def __init__(self):
        self.lines = []

    def setPen(self, pen):
        pass

    def drawLine(self, line):
        self.lines.append(line)


def Main():
    point = QtCore.QPointF
    for length, width, firstTrim, secondTrim in ((20, 10, 0, 0), (80, 40, 0, 0),
                                                (200, 100, 0, 0), (1000, 300, 200, 300),
                                                (100, 50, 40, 40)):
        for degrees in (0, 37, 90, 213):
            angle = math.radians(degrees)
            axis = point(math.cos(angle), math.sin(angle))
            first = point(123, -47)
            second = first + axis * length
            for directionReversed in (False, True):
                painter = LineRecorder()
                DrawStairSymbol(painter, first, second, width, stepCount = 1,
                                directionReversed = directionReversed, outline = False,
                                firstTrim = firstTrim, secondTrim = secondTrim)
                direction = axis * (-1 if directionReversed else 1)
                normal = point(-direction.y(), direction.x())
                tip = first + axis * firstTrim if directionReversed else second - axis * secondTrim
                assert len(painter.lines) >= 4
                for side, line in zip((-1, 1), painter.lines[-2:]):
                    assert QtCore.QLineF(line.p1(), tip).length() < 1e-8
                    offset = line.p2() - tip
                    assert math.isclose(QtCore.QPointF.dotProduct(offset, direction), -12, abs_tol = 1e-8)
                    assert math.isclose(QtCore.QPointF.dotProduct(offset, normal), side * 7, abs_tol = 1e-8)
    print("Stair arrowheads: fixed 12 by 14 geometry across run lengths, widths, rotations, landings and reversed direction passed")


if __name__ == "__main__":
    Main()
