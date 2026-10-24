"""Arrow extents and head angles across orientation, landing and scale changes."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import DrawOpeningSymbol, DrawStairSymbol, SlidingDoor


class RecordingPainter:
    def __init__(self):
        self.lines = []

    def setPen(self, pen):
        self.pen = pen

    def setBrush(self, brush):
        self.brush = brush

    def drawPolygon(self, polygon):
        self.polygon = polygon

    def drawLine(self, line):
        self.lines.append(line)


def CheckHead(lines):
    shaft = lines[-3]
    direction = (shaft.p2() - shaft.p1()) / shaft.length()
    for head in lines[-2:]:
        vector = head.p2() - head.p1()
        along = -QtCore.QPointF.dotProduct(vector, direction)
        across = abs(vector.x() * direction.y() - vector.y() * direction.x())
        assert along > 0 and math.isclose(across / along, 7 / 12, abs_tol = 1e-8)


app = QtWidgets.QApplication([])
point = QtCore.QPointF
for angle in (0, 45, 135):
    direction = point(math.cos(math.radians(angle)), math.sin(math.radians(angle)))
    for length, width in ((48, 36), (200, 40), (800, 150)):
        for trims in ((0, 0), (10, 15)):
            for reversedDirection in (False, True):
                painter = RecordingPainter()
                DrawStairSymbol(painter, point(), direction * length, width,
                                directionReversed = reversedDirection, firstTrim = trims[0], secondTrim = trims[1])
                shaft = painter.lines[-3]
                expected = (direction * trims[0], direction * (length - trims[1]))
                if reversedDirection:
                    expected = expected[::-1]
                assert QtCore.QLineF(shaft.p1(), expected[0]).length() < 1e-8
                assert QtCore.QLineF(shaft.p2(), expected[1]).length() < 1e-8
                CheckHead(painter.lines)
        for reversedDirection in (False, True):
            for panelsFlipped in (False, True):
                painter = RecordingPainter()
                DrawOpeningSymbol(painter, point(), direction * length, width, SlidingDoor,
                                  hingeAtSecond = reversedDirection, panelsFlipped = panelsFlipped)
                shaft = painter.lines[-3]
                normal = point(-direction.y(), direction.x())
                assert math.isclose(abs(QtCore.QPointF.dotProduct(shaft.p1(), normal)), width / 2 + 12)
                CheckHead(painter.lines)
print("PASS: full stair runs, landing trims, external sliding arrows and constant head angles")
