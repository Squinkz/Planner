"""Grid/ruler cache reuse, invalidation and equivalence to a fresh redraw."""
import math
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import DrawingViewport
from planner_app.graphics.palette import themeColors
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    app.setStyleSheet(BuildStyle())
    v = DrawingViewport()
    v.performanceTimer.stop()
    v.resize(900, 650)
    v.show()
    app.processEvents()
    with patch.object(v, "DrawGridBackground", wraps = v.DrawGridBackground) as builder:
        for index in range(4):
            v.hoverPosition = QtCore.QPointF(200 + index, 150)
            v.grab()
        assert builder.call_count == 0, "Cursor movement must reuse the background."
        for setting in ("pan", "zoom", "grid", "intensity", "units", "size", "font", "palette"):
            previous = v.viewportBackgroundKey
            if setting == "pan":
                v.panOffset += QtCore.QPointF(.37, 12.5)
            elif setting == "zoom":
                v.zoom = .7
            elif setting == "grid":
                v.showGrid = False
            elif setting == "intensity":
                v.gridIntensities["major"] = .25
            elif setting == "units":
                v.unitsMode = "Inches"
            elif setting == "size":
                v.resize(1200, 750)
            elif setting == "font":
                font = QtGui.QFont(v.font())
                font.setPointSizeF(max(1, font.pointSizeF()) + 3)
                v.setFont(font)
            else:
                original = themeColors["canvas"]
                themeColors["canvas"] = themeColors["controlBackground"]
            cached = v.grab().toImage()
            assert v.viewportBackgroundKey != previous, setting
            ratio = v.devicePixelRatioF()
            assert v.viewportBackground.width() == math.ceil(v.width() * ratio)
            v.viewportBackgroundKey = None
            assert v.grab().toImage() == cached, setting
            if setting == "palette":
                themeColors["canvas"] = original
    v.close()
    print("PASS: reused grid/rulers, complete invalidation and identical cached/fresh pixels.")


if __name__ == "__main__":
    Main()
