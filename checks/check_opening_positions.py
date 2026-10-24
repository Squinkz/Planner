"""Check opening positions stay fixed unless connected stretch or endpoint pressure moves them."""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtWidgets

from check_history import Drag
from planner import MainWindow, Wall, Window, Door


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.unitsMode = "Meters"  # Property values below are explicitly in meters.
    viewport.zoom = 0.5
    viewport.panOffset = QtCore.QPointF(-200, 0)
    window.snapButton.setChecked(False)
    point = QtCore.QPointF
    parent = Wall(point(), point(5000, 0))
    opening = Window(parent, 800 / 5000, 2000 / 5000)
    door = Door(parent, 3200 / 5000, 4100 / 5000)
    viewport.walls = [parent]
    viewport.windows = [opening, door]
    original = viewport.CaptureState()
    positions = (point(opening.firstVertex), point(opening.secondVertex), point(door.firstVertex), point(door.secondVertex))

    # Extending or shortening the free wall tail cannot slide its openings.
    for length in (6.0, 4.5):
        viewport.selectedWall = parent
        viewport.selectedVertex = None
        window.EditProperty("length", length)
        assert (opening.firstVertex, opening.secondVertex, door.firstVertex, door.secondVertex) == positions
        viewport.Undo()

    # Moving either wall endpoint has the same rule during live dragging.
    first = viewport.WorldToViewport(parent.firstVertex).toPoint()
    end = viewport.WorldToViewport(parent.secondVertex).toPoint()
    viewport.selectedWall = parent
    Drag(viewport, first, first + QtCore.QPoint(50, 0))
    assert (opening.firstVertex, opening.secondVertex, door.firstVertex, door.secondVertex) == positions
    viewport.Undo()
    viewport.selectedWall = parent
    Drag(viewport, end, end + QtCore.QPoint(-50, 0))
    assert (opening.firstVertex, opening.secondVertex, door.firstVertex, door.secondVertex) == positions
    viewport.Undo()

    # The first endpoint pushes only the opening it reaches; later ones stay put.
    viewport.selectedWall = parent
    Drag(viewport, first, first + QtCore.QPoint(100, 0))
    assert opening.firstVertex == point(1000, 0) and opening.secondVertex == point(2200, 0)
    assert door.firstVertex == point(3200, 0) and door.secondVertex == point(4100, 0)
    viewport.Undo()

    # The opposite endpoint pushes a door back, propagating pressure only if needed.
    viewport.selectedWall = parent
    viewport.selectedVertex = None
    window.EditProperty("length", 3.8)
    assert opening.firstVertex == point(800, 0) and opening.secondVertex == point(2000, 0)
    assert door.firstVertex == point(2900, 0) and door.secondVertex == point(3800, 0)
    viewport.Undo()
    viewport.selectedWall = parent
    window.EditProperty("length", 2.5)
    assert opening.firstVertex == point(400, 0) and opening.secondVertex == point(1600, 0)
    assert door.firstVertex == point(1600, 0) and door.secondVertex == point(2500, 0)
    assert viewport.OpeningsValid()
    viewport.Undo()

    # Enabling Connected Objects allows center movement, preserving physical lengths.
    window.connectedOptions["objects"].setChecked(True)
    viewport.selectedWall = parent
    viewport.selectedVertex = None
    window.EditProperty("length", 6.0)
    assert abs(opening.firstVertex.x() - 1080) < 0.001
    assert abs(door.firstVertex.x() - 3930) < 0.001
    assert abs(opening.length - 1200) < 0.001 and abs(door.length - 900) < 0.001
    viewport.Undo()
    window.connectedOptions["vertices"].setChecked(False)
    window.connectedOptions["objects"].setChecked(False)
    viewport.selectedWall = parent
    window.EditProperty("length", 6.0)
    assert (opening.firstVertex, opening.secondVertex, door.firstVertex, door.secondVertex) == positions
    viewport.Undo()

    # Whole-wall translation still carries its openings regardless of the toggle.
    viewport.selectedWall = parent
    start = viewport.WorldToViewport(point(2600, 0)).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(30, -20))
    assert opening.firstVertex == positions[0] + point(300, 200)
    viewport.Undo()
    assert viewport.CaptureState()[0] == original[0] and viewport.CaptureState()[3] == original[3]
    window.close()
    print("PASS: fixed positions, connected stretch, endpoint pressure, packed openings, translation and undo.")


if __name__ == "__main__":
    Main()
