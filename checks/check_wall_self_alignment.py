"""A wall's self-alignment guide must align its moving control endpoint."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import DrawingViewport, Wall


def Main():
    app = QtWidgets.QApplication([])
    viewport = DrawingViewport()
    viewport.resize(1200, 900)
    point = QtCore.QPointF
    source = Wall(point(), point(-60, -1800), 120)
    upper = Wall(point(-1600, 0), point(), 120)
    lower = Wall(point(-1400, -1950), point(240, -2400), 120)
    viewport.walls = [source, upper, lower]
    viewport.selectedWall, viewport.selectedVertex = source, 1
    viewport.dragStart = point(600, 400)
    viewport.midpointSnapEnabled = False
    raw = point(-60, -1800)
    target = viewport.SnapStairVertex(raw, source.firstVertex, source, QtCore.Qt.KeyboardModifier.NoModifier)
    assert abs(target.x() - source.firstVertex.x()) < .01
    assert (0, 0.0) in viewport.alignmentGuides
    # The same rule applies horizontally and with either endpoint being moved.
    viewport.walls = [source]
    for index in (0, 1):
        source.firstVertex, source.secondVertex = point(-1800, -60), point()
        viewport.selectedVertex = index
        opposite = point() if index == 0 else point(-1800, -60)
        raw = point(-1800, -60) if index == 0 else point(0, -120)
        target = viewport.SnapStairVertex(raw, opposite, source, QtCore.Qt.KeyboardModifier.NoModifier)
        assert abs(target.y() - opposite.y()) < .01
    # Exact endpoint snapping continues to outrank self alignment.
    source.firstVertex, source.secondVertex = point(), point(-60, -1800)
    viewport.walls = [source, upper, lower]
    viewport.selectedVertex = 1
    endpoint = Wall(point(-35, -1800), point(-900, -1800), 120)
    viewport.walls.append(endpoint)
    target = viewport.SnapStairVertex(point(-40, -1800), point(), source, QtCore.Qt.KeyboardModifier.NoModifier)
    assert target == endpoint.firstVertex and viewport.snapPriority == 0


if __name__ == "__main__":
    Main()
