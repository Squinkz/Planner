"""A stair endpoint aligns to its stationary endpoint beside enclosing walls."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Stair, Wall
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    viewport.zoom = .6
    viewport.panOffset = point(100, 220)
    source = Stair(point(0, -1700), point(-180, 1700))
    child = Stair(point(-2300, 1700), point(-180, 1700))
    right = Wall(point(620, -2200), point(620, 2320), 240)
    top = Wall(point(-2800, 2320), point(620, 2320), 240)
    viewport.walls = [source, child, right, top]
    viewport.snapEnabled = True
    viewport.vertexSnapEnabled = True
    viewport.gridSnapEnabled = True
    viewport.alignmentSnapEnabled = True
    viewport.midpointSnapEnabled = False
    viewport.selectedWall = source
    viewport.selectedVertex = 1
    window.RefreshProperties()
    app.processEvents()
    raw = point(-5, 1700)
    Drag(viewport, viewport.WorldToViewport(source.secondVertex).toPoint(), viewport.WorldToViewport(raw).toPoint())
    assert source.secondVertex.x() == source.firstVertex.x()
    assert child.secondVertex == source.secondVertex
    assert viewport.OpeningsValid()
    viewport.Undo()
    assert source.secondVertex == point(-180, 1700) and child.secondVertex == point(-180, 1700)
    viewport.Redo()
    assert source.secondVertex.x() == 0
    # Horizontal alignment must not round the connected endpoint into the wall
    # on the unaligned X axis (180 mm would otherwise become 200 mm).
    source = Stair(point(-2200, 620), point(180, 780))
    child = Stair(point(180, 780), point(180, 3000))
    right = Wall(point(800, 0), point(800, 3600), 240)
    bottom = Wall(point(-3200, 0), point(800, 0), 240)
    viewport.walls = [source, child, right, bottom]
    viewport.selectedWall, viewport.selectedVertex = source, 1
    window.RefreshProperties()
    app.processEvents()
    assert viewport.OpeningsValid()
    Drag(viewport, viewport.WorldToViewport(source.secondVertex).toPoint(),
         viewport.WorldToViewport(point(180, 625)).toPoint())
    assert source.secondVertex.y() == source.firstVertex.y()
    assert abs(source.secondVertex.x() - 180) < 1e-8
    assert child.firstVertex == source.secondVertex and viewport.OpeningsValid()
    viewport.Undo()
    assert source.secondVertex == point(180, 780)
    viewport.Redo()
    assert source.secondVertex == point(180, 620)
    # A nearby opposite endpoint must not monopolize alignment when dragging
    # one bounding corner toward a wall face from a small initial gap.
    source = Stair(point(-2000, 700), point(1000, 700))
    bottom = Wall(point(-3200, 0), point(1800, 0), 240)
    viewport.walls = [source, bottom]
    viewport.selectedWall, viewport.selectedVertex = source, 0
    window.RefreshProperties()
    app.processEvents()
    Drag(viewport, viewport.WorldToViewport(source.firstVertex).toPoint(),
         viewport.WorldToViewport(point(-2000, 620)).toPoint())
    corners = viewport.ObjectCorners(source)
    assert min(abs(corner.y() - 120) for corner in corners) < .01, corners
    assert viewport.StairFits(source)
    viewport.Undo()
    assert source.firstVertex == point(-2000, 700)
    # The opposite endpoint is alignment-only, not a target that collapses the run.
    viewport.gridSnapEnabled = False
    viewport.alignmentSnapEnabled = False
    viewport.walls = [source]
    raw = source.firstVertex + point(10, 10)
    assert viewport.SnapStairVertex(raw, source.firstVertex, source, QtCore.Qt.KeyboardModifier.NoModifier) == raw
    window.close()
    print("PASS: self alignment, adjacent wall clearance, connected endpoint, history and no endpoint collapse.")


if __name__ == "__main__":
    Main()
