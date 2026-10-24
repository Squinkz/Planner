"""Nearly straight 12/24 cm joins must not create remote miter/material wedges."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    v = window.viewport
    point = QtCore.QPointF
    for rotation in (0, 45, 90, 180, 270):
        radians = math.radians(rotation)
        def Rotate(value):
            return point(value.x() * math.cos(radians) - value.y() * math.sin(radians),
                         value.x() * math.sin(radians) + value.y() * math.cos(radians))
        for reverse in (False, True):
            thin = Wall(point(), Rotate(point(102, 2107)), 120, material = "Concrete Block")
            wide = Wall(point(), Rotate(point(49, -1581)), 240)
            if reverse:
                for wall in (thin, wide):
                    wall.firstVertex, wall.secondVertex = wall.secondVertex, wall.firstVertex
            v.walls = [thin, wide]
            v.grab()
            for distance in (250, 500, 1000):
                direction = Rotate(point(102, 2107))
                direction /= math.hypot(direction.x(), direction.y())
                normal = point(-direction.y(), direction.x())
                for offset in (-50, 0, 50):
                    world = direction * distance + normal * offset
                    sample = point(world.x(), -world.y()) * v.basePixelsPerMillimeter
                    assert v.wallMaterialPaths[id(thin)].contains(sample), (rotation, reverse, distance, offset)
                    assert not v.wallMaterialPaths[id(wide)].contains(sample)
            samples = [point(x + .17, y + .31) for x in range(-45, 46, 3) for y in range(-45, 46, 3)]
            owners = {id(wall): [v.wallMaterialPaths[id(wall)].contains(sample) for sample in samples] for wall in v.walls}
            for sample in samples:
                if v.wallGeometryPath.contains(sample):
                    assert any(path.contains(sample) for path in v.wallMaterialPaths.values()), (rotation, reverse, sample)
            v.walls.reverse()
            v.grab()
            for wall in v.walls:
                assert owners[id(wall)] == [v.wallMaterialPaths[id(wall)].contains(sample) for sample in samples]
    window.close()
    print("PASS: local 12/24 cm joins, complete material coverage, rotations, reversed endpoints and paint-order independence.")


if __name__ == "__main__":
    Main()
