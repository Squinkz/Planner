"""Ruler corners use canvas colors and stay visible on the first pan frame."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall
from planner_app.graphics.palette import themeColors
from planner_app.graphics.theme import ApplyApplicationTheme


def Main():
    with tempfile.TemporaryDirectory(dir = Path(__file__).parent) as folder:
        os.environ["PLANNER_SESSION_PATH"] = str(Path(folder) / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(Path(folder) / "startup.plan")
        app = QtWidgets.QApplication([])
        ApplyApplicationTheme(app)
        main = MainWindow()
        main.show()
        v = main.viewport
        v.walls = [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), 240)]
        v.sceneRevision += 1
        v.EnsureObjectIds()
        app.processEvents()
        before = v.grab().toImage()
        assert before.pixelColor(3, 3) == QtGui.QColor(themeColors["rulerBackground"])
        rect = QtCore.QRect(v.rulerSize + 10, 1, v.width() - v.rulerSize - 20, v.rulerSize - 2)
        position = v.DrawingRect().center().toPoint()
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.MiddleButton, pos = position)
        held = v.grab().toImage()
        assert held.copy(rect) == before.copy(rect), "Ruler disappears when pressing without moving"
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.MiddleButton, pos = position)
        image = QtGui.QImage(v.size(), QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        v.DrawRulerFrame(painter, "mm", allEdges = True)
        painter.end()
        for x, y in ((3, 3), (v.width() - 4, 3), (3, v.height() - 4), (v.width() - 4, v.height() - 4)):
            assert image.pixelColor(x, y) == QtGui.QColor(themeColors["rulerBackground"])
        edgeColor = QtGui.QColor(themeColors["rulerMinorTick"])
        for x in (v.rulerSize, v.width() - v.rulerSize):
            for y in (3, v.rulerSize // 2, v.height() - v.rulerSize // 2, v.height() - 4):
                assert image.pixelColor(x, y) == edgeColor, (x, y, image.pixelColor(x, y).name())
        for y in (v.rulerSize, v.height() - v.rulerSize):
            for x in (3, v.rulerSize // 2, v.width() - v.rulerSize // 2, v.width() - 4):
                assert image.pixelColor(x, y) == edgeColor, (x, y, image.pixelColor(x, y).name())
        # Wider borders retain the same text/tick band beside all four canvas
        # edges. Compare actual rasterized labels, including the rotated sides.
        referenceBands = None
        for size in (28, 56, 100):
            v.rulerSize = size
            v.setFixedSize(400 + 2 * size, 300 + 2 * size)
            image = QtGui.QImage(v.size(), QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtCore.Qt.GlobalColor.transparent)
            with QtGui.QPainter(image) as painter:
                rect = QtCore.QRectF(size, size, 400, 300)
                unit = v.DrawGridBackground(painter, rect, QtCore.QPointF(size + 137, size + 143),
                                            v.zoom * v.basePixelsPerMillimeter, drawGrid = False, allEdges = True)
                v.DrawRulerFrame(painter, unit, allEdges = True)
            bands = [image.copy(size + 45, size - 27, 310, 26),
                     image.copy(size + 45, size + 301, 310, 26),
                     image.copy(size - 27, size + 45, 26, 210),
                     image.copy(size + 401, size + 45, 26, 210)]
            if referenceBands is None:
                referenceBands = bands
            else:
                assert bands == referenceBands, ("Ruler labels moved away from ticks", size)
        main.MarkProjectClean()
        main.close()
        print("PASS: canvas ruler corners and stationary first pan frame")


if __name__ == "__main__":
    Main()
