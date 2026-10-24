"""Measurements use the application font independently of canvas labels."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics import palette
from planner_app.graphics.fonts import fontFamily, LoadApplicationFonts
from planner_app.graphics.measurement_text import MeasurementTextPath, FractionTextPath
from planner_app.models import Label, Wall
from planner_app.viewport.widget import DrawingViewport


class RecordingPainter(QtGui.QPainter):
    def __init__(self, image):
        super().__init__(image)
        self.families = []

    def drawText(self, *arguments):
        self.families.append(self.font().family())
        super().drawText(*arguments)


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    v = DrawingViewport()
    v.resize(1400, 900)
    v.walls = [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), 240)]
    v.unitsMode = "Centimeters"
    original = palette.labelFont
    try:
        for family in ("D-DIN Condensed", "Noto Sans", "D-DIN Condensed"):
            palette.labelFont = family
            assert Label(text = "Label").Font().family() == family
            image = QtGui.QImage(v.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QtCore.Qt.GlobalColor.transparent)
            with RecordingPainter(image) as painter:
                initialFont = painter.font().toString()
                v.DrawScene(painter, v.DrawingRect(), v.WorldToViewport(QtCore.QPointF()), v.basePixelsPerMillimeter)
                assert painter.families and set(painter.families) == {fontFamily}, painter.families
                assert painter.font().toString() == initialFont
        for fraction in ("1/2", "3/8", "15/16"):
            condensed = MeasurementTextPath(fraction, QtGui.QFont("D-DIN Condensed", 10).toString(), 96)
            noto = MeasurementTextPath(fraction, QtGui.QFont("Noto Sans", 10).toString(), 96)
            assert not condensed.isEmpty()
            assert not noto.isEmpty()
            assert FractionTextPath(fraction, QtGui.QFont("D-DIN Condensed", 10).toString(), 96)[2] == ("native" if fraction == "1/2" else "built")
        v.unitsMode = "Feet and Inches"
        image = QtGui.QImage(v.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        with QtGui.QPainter(image) as painter:
            v.DrawScene(painter, v.DrawingRect(), v.WorldToViewport(QtCore.QPointF()), v.basePixelsPerMillimeter)
    finally:
        palette.labelFont = original
    print("PASS: fixed measurement font, independent canvas labels, painter restoration and imperial fraction rendering.")


if __name__ == "__main__":
    Main()
