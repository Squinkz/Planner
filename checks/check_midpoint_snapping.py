"""Verify midpoint targets, projected alignment and moving-object exclusions."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow, Wall, Window, Door
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    none = QtCore.Qt.KeyboardModifier.NoModifier
    alt = QtCore.Qt.KeyboardModifier.AltModifier
    for option in window.snapOptions:
        window.snapOptions[option].setChecked(False)
    assert not viewport.snapEnabled
    window.snapOptions["midpoints"].setChecked(True)
    window.snapButton.setChecked(True)
    parent = Wall(point(), point(4000, 0))
    opening = Window(parent, .2, .4)
    door = Door(parent, .6, .8)
    viewport.walls = [parent]
    viewport.windows = [opening, door]
    for obj in (parent, opening, door):
        center = (obj.firstVertex + obj.secondVertex) / 2
        assert viewport.SnapPosition(center + point(35, 20), none) == center
        assert viewport.SnapPosition(center + point(35, 20), alt) == center + point(35, 20)
    # Combined X/Y projection uses midpoint coordinates from different walls.
    other = Wall(point(6000, 600), point(8000, 600))
    viewport.walls.append(other)
    window.snapOptions["alignment"].setChecked(True)
    assert viewport.SnapPosition(point(2035, 620), none) == point(2000, 600)
    assert viewport.alignmentGuides == [(0, 2000), (1, 600)]
    window.snapOptions["midpoints"].setChecked(False)
    assert viewport.SnapPosition(point(2035, 620), none) == point(2035, 620)
    assert not viewport.alignmentGuides
    window.snapOptions["alignment"].setChecked(False)
    window.snapOptions["midpoints"].setChecked(True)
    window.snapButton.setChecked(True)
    window.connectedOptions["vertices"].setChecked(False)
    viewport.windows = []
    # Translating a wall snaps a bounding corner to a midpoint without resizing it.
    moving = Wall(point(-1500, -1000), point(-500, -1000))
    viewport.walls.append(moving)
    viewport.selectedWall = moving
    start = viewport.WorldToViewport(point(-1000, -1000)).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(707, -180))
    assert moving.firstVertex == point(2000, -120)
    assert point(2000, 0) in viewport.ObjectCorners(moving)
    assert moving.secondVertex - moving.firstVertex == point(1000, 0)
    viewport.Undo()
    # Midpoints affected by a drag cannot snap the moving geometry back to itself.
    viewport.selectedWall = moving
    viewport.dragStart = point(start)
    assert all(midpoint != point(-1000, -1000) for midpoint in viewport.SnapMidpoints())
    viewport.CancelInteraction()
    # An opening uses its own center as the root and another wall's center as target.
    crossing = Wall(point(1800, -1000), point(1800, 1000))
    viewport.walls = [parent, crossing]
    viewport.windows = [opening]
    viewport.selectedWall = opening
    start = viewport.WorldToViewport(point(1200, 0)).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(123, 0))
    assert abs((opening.firstVertex.x() + opening.secondVertex.x()) / 2 - 1200) < .01
    # The crossing wall obstructs the desired placement; translation is rejected.
    assert abs(opening.length - 800) < .01
    # Turning off the last option disables Snap; enabling Snap restores grid.
    window.snapOptions["midpoints"].setChecked(False)
    assert not viewport.snapEnabled
    window.snapButton.setChecked(True)
    assert viewport.gridSnapEnabled and window.snapOptions["grid"].isChecked()
    window.close()
    print("PASS: wall/window/door midpoints, projected alignment, Alt, wall/opening movement, exclusions and toggle rules.")


if __name__ == "__main__":
    Main()
