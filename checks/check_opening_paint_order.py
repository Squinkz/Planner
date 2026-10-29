"""Opening paint order keeps panels in front of jambs and jambs in front of arcs."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.symbols import DrawOpeningSymbol
from planner_app.graphics.palette import themeColors
from planner_app.models import BarnDoor, Door, SwingingDoor, DoubleDoor


def Main():
    app = QtWidgets.QApplication([])
    point = QtCore.QPointF
    for hinge in (False, True):
        for outward in (False, True):
            image = QtGui.QImage(500, 500, QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtGui.QColor(themeColors["canvas"]))
            first, second = point(250, 400), point(250, 100)
            with QtGui.QPainter(image) as painter:
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                DrawOpeningSymbol(painter, first, second, 40, BarnDoor, hinge, outward,
                                  color = "#ff0000", wallColor = "#000000", lineWidth = 1, wallLineWidth = 10)
            # The jamb at the opening midpoint passes behind the leaf. Sample
            # inside its body, beyond the thin panel outline's antialias band.
            x = 250 + (23 if outward else -23)
            assert image.pixelColor(x, 250) == QtGui.QColor(themeColors["canvas"]), (hinge, outward, image.pixelColor(x, 250).name())
    for kind in (Door, SwingingDoor, DoubleDoor):
        for hinge in (False, True):
            for outward in (False, True):
                image = QtGui.QImage(500, 500, QtGui.QImage.Format.Format_ARGB32)
                image.fill(QtCore.Qt.GlobalColor.white)
                with QtGui.QPainter(image) as painter:
                    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                    DrawOpeningSymbol(painter, point(100, 250), point(400, 250), 40, kind, hinge, outward,
                                      color = "#ff0000", wallColor = "#000000", lineWidth = 4, wallLineWidth = 10)
                for x in (100, 400):
                    for y in (230, 270):
                        assert image.pixelColor(x, y) == QtGui.QColor("black"), (kind, hinge, outward, x, y)
    print("PASS: barn-panel/jamb and swing-arc/jamb overlap for both hinges and directions")


if __name__ == "__main__":
    Main()
