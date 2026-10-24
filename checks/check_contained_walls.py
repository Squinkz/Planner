"""Contained walls are visible, selectable warnings without blocking movement."""
import os
import sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, Stair
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    main = MainWindow()
    main.show()
    app.processEvents()
    viewport = main.viewport
    viewport.snapEnabled = False
    viewport.connectedEnabled = False
    point = QtCore.QPointF
    outer = Wall(point(-1500, 0), point(1500, 0), 600)
    inner = Wall(point(-500, 0), point(500, 0), 120)
    for walls in ([inner, outer], [outer, inner]):
        viewport.walls = walls
        assert viewport.ContainedWalls() == [inner]
        assert viewport.ContainedWalls() is viewport.containedWallCache
        viewport.SetSelection([])
        center = viewport.WorldToViewport(point())
        assert viewport.HitTest(center) == (inner, None)
        rendered = viewport.grab().toImage()
        edge = viewport.WorldToViewport(point(100, 60)).toPoint()
        color = rendered.pixelColor(edge)
        assert color.red() > color.green() * 1.5 and color.red() > color.blue() * 1.5, color.name()
    # Dragging into containment commits; dragging back out clears the warning.
    inner.firstVertex += point(0, 900)
    inner.secondVertex += point(0, 900)
    assert not viewport.ContainedWalls()
    before = viewport.WorldToViewport(point(0, 900)).toPoint()
    after = viewport.WorldToViewport(point()).toPoint()
    Drag(viewport, before, after)
    assert viewport.ContainedWalls() == [inner]
    Drag(viewport, after, before)
    assert not viewport.ContainedWalls()
    viewport.Undo()
    assert viewport.ContainedWalls() == [inner]
    viewport.SetSelection([(inner, None)])
    viewport.DeleteSelected()
    assert viewport.walls == [outer]
    viewport.Undo()
    assert inner in viewport.walls and viewport.ContainedWalls() == [inner]
    # Same tests in rotated local coordinates, plus an AABB-contained shape whose
    # actual corners cross the narrow diagonal wall faces.
    outer = Wall(point(-1000, -1000), point(1000, 1000), 400)
    inner = Wall(point(-300, -300), point(300, 300), 120)
    viewport.walls = [inner, outer]
    assert viewport.ContainedWalls() == [inner]
    crossing = Wall(point(-200, 200), point(200, -200), 120)
    viewport.walls = [crossing, outer]
    assert not viewport.ContainedWalls()
    # Partial overlaps and edge contact remain normal. Stairs never count as walls.
    outer = Wall(point(-1000, 0), point(1000, 0), 240)
    partial = Wall(point(500, 0), point(1500, 0), 120)
    adjacent = Wall(point(-500, 180), point(500, 180), 120)
    stair = Stair(point(-400, 0), point(400, 0), 120)
    viewport.walls = [outer, partial, adjacent, stair]
    assert not viewport.ContainedWalls()
    duplicate = Wall(point(1000, 0), point(-1000, 0), 240)
    viewport.walls = [outer, duplicate]
    assert viewport.ContainedWalls() == [duplicate]
    main.close()
    print("PASS: containment geometry, red draw priority, selection priority, nonblocking drag, undo/delete, cache refresh and duplicate walls.")


if __name__ == "__main__":
    Main()
