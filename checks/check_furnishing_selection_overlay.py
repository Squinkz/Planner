"""Selected furnishing bounds stay visible above overlapping scene objects and caches."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.models import Furnishing
from planner_app.graphics.palette import themeColors


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    back = Furnishing(v.furnishingDefinitions["null"])
    front = Furnishing(v.furnishingDefinitions["null"])
    back.width = 600
    back.firstVertex, back.secondVertex = QtCore.QPointF(0, -300), QtCore.QPointF(0, 300)
    front.width = 1600
    front.firstVertex, front.secondVertex = QtCore.QPointF(0, -800), QtCore.QPointF(0, 800)
    v.furnishings = [back, front]
    v.showGrid = v.showMeasurements = False
    v.hoverPosition = None
    v.SetSelection([(back, None)])
    expected = QtGui.QColor(themeColors["selectionOutline"])
    for angle in (0, 30):
        back.angle = angle
        corners = v.ObjectCorners(back)
        pixel = v.WorldToViewport(corners[0] * .4 + corners[1] * .6).toPoint()
        images = [v.grab().toImage(), v.grab().toImage()]
        assert v.viewportScene is not None, "The cached scene path was not exercised"
        v.dragStart = v.WorldToViewport(QtCore.QPointF())
        images.append(v.grab().toImage())
        v.dragStart = None
        for image in images:
            # Antialiasing blends the boundary; its strongest nearby pixel must carry the selection ink.
            colors = [image.pixelColor(pixel.x() + x, pixel.y() + y) for x in range(-2, 3) for y in range(-2, 3)]
            assert max(color.blue() - color.red() for color in colors) > (expected.blue() - expected.red()) * .5, "Higher priority furniture covered the selection outline"
        v.SetSelection([])
        unselected = v.grab().toImage()
        assert unselected != images[0]
        v.SetSelection([(back, None)])
    main.close()


if __name__ == "__main__":
    Main()
