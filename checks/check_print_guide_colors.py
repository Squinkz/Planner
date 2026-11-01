"""Print page guides stay visible across canvas themes and mismatched custom inks."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics import palette
from planner_app.viewport.export_bounds import ExportBoundsOverlay


class GuideViewport(QtWidgets.QWidget):
    def WorldToViewport(self, point):
        return point * .01 + QtCore.QPointF(180.3, 120.7)

    def ViewportToWorld(self, point):
        return (point - QtCore.QPointF(180.3, 120.7)) / .01


class GuidePainter(QtGui.QPainter):
    def drawLine(self, *args):
        self.colors.append(self.pen().color())
        self.widths.append(self.pen().widthF())
        super().drawLine(*args)


def Luminance(color):
    return sum(weight * (value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4)
               for value, weight in zip((color.redF(), color.greenF(), color.blueF()), (.2126, .7152, .0722)))


def Main():
    app = QtWidgets.QApplication([])
    viewport = GuideViewport()
    overlay = ExportBoundsOverlay(viewport)
    overlay.printMode = True
    themes = [name for name, definition in palette.themeDefinitions.items() if definition["type"] == "canvas"]
    cases = [(name, {}) for name in themes] + [(themes[0], dict(canvas = color, objectOutline = color)) for color in ("#ffffff", "#000000", "#808080")]
    for name, overrides in cases:
        palette.SetThemes(canvasTheme = name)
        with patch.dict(palette.themeColors, overrides):
            image = QtGui.QImage(400, 300, QtGui.QImage.Format.Format_RGB32)
            image.fill(QtGui.QColor(palette.themeColors["canvas"]))
            painter = GuidePainter(image)
            painter.colors = []
            painter.widths = []
            overlay.DrawPrintGuides(painter, QtCore.QRectF(0, 0, 400, 300))
            painter.end()
            assert painter.colors, name
            assert all(width >= 2 for width in painter.widths), name
            background = Luminance(QtGui.QColor(palette.themeColors["canvas"]))
            for color in painter.colors:
                ink = Luminance(color)
                assert color.alpha() == 255
                if not overrides:
                    assert color.name() in [QtGui.QColor(palette.themeColors[role]).name() for role in
                        ("groupSelectionOutline", "warningOutline", "errorText", "missing", "objectOutline", "rulerText")], (name, color.name())
                    assert color.name() != QtGui.QColor(palette.themeColors["selectionOutline"]).name(), name
                assert (max(ink, background) + .05) / (min(ink, background) + .05) >= 4.49, (name, overrides, color.name())
    print(f"Print guide visibility verified for {len(themes)} canvas themes and custom colour mismatches")


if __name__ == "__main__":
    Main()
