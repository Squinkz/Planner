"""Material ownership follows the miter from shared vertices to joined edges."""
import os
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    window = MainWindow()
    window.resize(1200, 900)
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    upright = Wall(point(), point(0, 2000), material = "Brick")
    horizontal = Wall(point(), point(3000, 0), material = "Wood")
    angled = Wall(point(3000, 0), point(4200, 2000), material = "Concrete Block")
    viewport.walls = [upright, horizontal, angled]
    viewport.grab()
    verticalPath = viewport.wallMaterialPaths[id(upright)]
    horizontalPath = viewport.wallMaterialPaths[id(horizontal)]
    # At the right-angle joint, the dividing diagonal is x + y = 0
    # in stable screen-oriented geometry, not either rectangle's cap.
    for sample in (point(10, -15), point(-15, 10), point(-20, -10)):
        assert verticalPath.contains(sample) and not horizontalPath.contains(sample)
    for sample in (point(15, -10), point(-10, 15), point(20, 10)):
        assert horizontalPath.contains(sample) and not verticalPath.contains(sample)
    # Reversing scene order preserves ownership at both the square and angled joints.
    samples = [point(x, y) for x in range(-22, 850, 13) for y in range(-45, 25, 11)]
    owners = {id(wall): [viewport.wallMaterialPaths[id(wall)].contains(sample) for sample in samples]
              for wall in viewport.walls}
    viewport.walls.reverse()
    viewport.grab()
    for wall in viewport.walls:
        assert owners[id(wall)] == [viewport.wallMaterialPaths[id(wall)].contains(sample) for sample in samples]
    viewport.zoom = .6
    viewport.panOffset = point(-220, 0)
    viewport.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "material-junctions.png"))
    # Junction shading still covers the union at a three-way connection.
    viewport.walls.append(Wall(point(), point(-1500, 1000), material = "Ceramic"))
    viewport.grab()
    for x in range(-40, 41, 7):
        for y in range(-40, 41, 7):
            sample = point(x, y)
            if viewport.wallGeometryPath.contains(sample):
                assert any(path.contains(sample) for path in viewport.wallMaterialPaths.values())
    # Unequal collinear widths at a T must retain the entire transition patch.
    for rotation in (0, 37, 90, 180, 270):
        angle = math.radians(rotation)
        along = point(math.cos(angle), math.sin(angle))
        across = point(-along.y(), along.x())
        thin = Wall(point(), -along * 2000, 120, material = "Brick")
        wide = Wall(point(), along * 2000, 360, material = "Wood")
        branch = Wall(point(), -across * 2000, 360, material = "Concrete Block")
        viewport.walls = [thin, wide, branch]
        viewport.grab()
        samples = [point(x + .17, y + .31) for x in range(-48, 49, 2) for y in range(-48, 49, 2)]
        for sample in samples:
            if viewport.wallGeometryPath.contains(sample):
                assert any(path.contains(sample) for path in viewport.wallMaterialPaths.values()), (rotation, sample)
        ownership = {id(wall): [viewport.wallMaterialPaths[id(wall)].contains(sample) for sample in samples]
                     for wall in viewport.walls}
        viewport.walls.reverse()
        viewport.grab()
        for wall in viewport.walls:
            assert ownership[id(wall)] == [viewport.wallMaterialPaths[id(wall)].contains(sample) for sample in samples]
    window.close()
    print("PASS: diagonal miter material boundaries, angled joins, order independence and three-way fill coverage.")


if __name__ == "__main__":
    Main()
