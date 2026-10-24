"""Numeric wall moves must fit openings on stretched neighbors just like a canvas drag."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow
from planner_app.models import Wall, Window
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    right = Wall(point(3000, 0), point(3000, 2000), 120)
    bottom = Wall(point(), point(3000, 0), 120)
    obstruction = Wall(point(6400, -500), point(6400, 500), 120)
    opening = Window(bottom, .65, .95)
    v.walls, v.windows = [bottom, right, obstruction], [opening]
    v.connectedEnabled = v.connectedVerticesEnabled = True
    v.connectedObjectsEnabled = False
    v.snapEnabled = False
    v.zoom = .2
    v.SetSelection([(right, None)])
    assert v.OpeningsValid()
    before = v.CaptureState()
    start = v.WorldToViewport(point(3000, 1000)).toPoint()
    end = v.WorldToViewport(point(8000, 1000)).toPoint()
    Drag(v, start, end)
    assert QtCore.QLineF(right.firstVertex, point(8000, 0)).length() < .01
    assert abs(opening.centerFraction * QtCore.QLineF(bottom.firstVertex, bottom.secondVertex).length() - 2400) < .01
    assert v.OpeningsValid()
    manualVertices = [(point(wall.firstVertex), point(wall.secondVertex)) for wall in v.walls]
    manualOpening = opening.centerFraction
    v.RestoreState(before)
    assert v.MoveSpecial(5000, 0, 0) is None
    for wall, (first, second) in zip(v.walls, manualVertices):
        assert QtCore.QLineF(wall.firstVertex, first).length() < .01
        assert QtCore.QLineF(wall.secondVertex, second).length() < .01
    assert abs(opening.centerFraction - manualOpening) < 1e-8
    assert v.OpeningsValid()
    v.RestoreState(before)
    assert v.MoveSpecial(-2600, 0, 0), "A wall too short for its window must still reject the move"
    assert v.CaptureState() == before
    main.close()


if __name__ == "__main__":
    Main()
