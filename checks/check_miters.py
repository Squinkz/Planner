"""Check per-vertex chamfer rendering, inheritance and edit history."""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtTest, QtWidgets

from check_history import Drag
from planner import MainWindow, Wall


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    window.snapButton.setChecked(False)
    window.connectedOptions["vertices"].setChecked(False)
    window.connectedOptions["objects"].setChecked(False)
    source = Wall(point(), point(-1000, 0))
    neighbor = Wall(point(), point(-1000, -300))
    viewport.walls = [source, neighbor]
    assert source.firstMiter == source.secondMiter == 0
    viewport.selectedWall = source
    viewport.selectedVertex = 0
    window.RefreshProperties()
    editor = window.propertyFields["miter"]
    assert editor.minimum() == 0 and editor.maximum() == 1 and editor.value() == 0

    # Changing a shared joint updates all coincident endpoints, independently
    # of Connected. Opposite endpoints retain their individual settings.
    bounds = []
    for value in (0, 0.5, 1):
        window.EditProperty("miter", value)
        assert source.firstMiter == neighbor.firstMiter == value
        assert source.secondMiter == neighbor.secondMiter == 0
        bounds.append(viewport.ConnectedWallPath(viewport.walls).boundingRect().right())
    assert bounds[0] > bounds[1] > bounds[2]
    viewport.Undo()
    assert source.firstMiter == neighbor.firstMiter == 0.5
    viewport.Redo()
    assert source.firstMiter == neighbor.firstMiter == 1

    # New construction copies its start vertex's value, even with Snap off.
    window.EditProperty("miter", 0.75)
    start = viewport.WorldToViewport(source.firstVertex).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(80, -60), shift, button = QtCore.Qt.MouseButton.RightButton)
    branch = viewport.walls[-1]
    assert branch.firstMiter == 0.75 and branch.secondMiter == 0
    viewport.Undo()
    assert branch not in viewport.walls
    viewport.Redo()
    assert branch.firstMiter == 0.75

    # Dropping A onto B transfers A's value to B, and undo restores both.
    source = Wall(point(-800, 0), point(-1600, 0), firstMiter = 0.3)
    target = Wall(point(600, 500), point(1200, 500), firstMiter = 0.9)
    viewport.walls = [source, target]
    viewport.selectedWall = source
    viewport.selectedVertex = 0
    start = viewport.WorldToViewport(source.firstVertex).toPoint()
    end = viewport.WorldToViewport(target.firstVertex).toPoint()
    Drag(viewport, start, end)
    assert source.firstVertex == target.firstVertex
    assert source.firstMiter == target.firstMiter == 0.3
    viewport.Undo()
    assert source.firstMiter == 0.3 and target.firstMiter == 0.9
    viewport.Redo()
    assert target.firstMiter == 0.3

    # Finishing a new wall at an existing vertex transfers the new endpoint's
    # default value. Cancelled previews never change that existing vertex.
    viewport.Undo()
    empty = end + QtCore.QPoint(-40, -80)
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.RightButton, shift, empty)
    viewport.UpdateInteraction(point(end), shift)
    viewport.CancelInteraction()
    assert target.firstMiter == 0.9
    Drag(viewport, empty, end, shift, button = QtCore.Qt.MouseButton.RightButton)
    assert target.firstMiter == viewport.walls[-1].secondMiter == 0
    viewport.Undo()
    assert target.firstMiter == 0.9
    window.close()
    print("PASS: chamfer range/default, decreasing corner reach, shared edits, branch/drop inheritance, cancellation and undo/redo.")


if __name__ == "__main__":
    Main()
