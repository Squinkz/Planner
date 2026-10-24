"""Verify view-independent geometry reuse and automatic cache invalidation."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from unittest.mock import patch
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall, Door


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    viewport = window.viewport
    window.show()
    app.processEvents()
    point = QtCore.QPointF
    source = Wall(point(-1500, 0), point(1500, 0))
    branch = Wall(point(), point(0, 1000), 120)
    door = Door(source, .1, .3)
    viewport.walls = [source, branch]
    viewport.windows = [door]
    with patch.object(viewport, "TraceWallComponent", wraps = viewport.TraceWallComponent) as tracer:
        path = viewport.ConnectedWallPath(viewport.walls)
        dimensions = viewport.WallDimensions(viewport.walls, path)
        initialTraces = tracer.call_count
        assert initialTraces > 0
        for zoom, pan in ((.02, point()), (.5, point(81, -37)), (1, point(-103, 200)), (10, point(1000, -700))):
            viewport.zoom = zoom
            viewport.panOffset = pan
            path = viewport.ConnectedWallPath(viewport.walls)
            assert viewport.WallDimensions(viewport.walls, path) is dimensions
            viewport.grab()
        assert tracer.call_count == initialTraces
        door.swingsOutwards = True
        changed = viewport.WallDimensions(viewport.walls, path)
        assert changed is not dimensions and tracer.call_count == initialTraces
        for field in ("firstVertex", "width", "firstMiter"):
            before = viewport.CaptureState()
            original = getattr(source, field)
            setattr(source, field, point(-1800, 0) if field == "firstVertex" else .5 if field == "firstMiter" else original / 2)
            viewport.RecordEdit(before)
            path = viewport.ConnectedWallPath(viewport.walls)
            assert viewport.WallDimensions(viewport.walls, path) is not changed
            viewport.Undo()
            viewport.ConnectedWallPath(viewport.walls)
            viewport.Redo()
            viewport.ConnectedWallPath(viewport.walls)
            assert getattr(source, field) != original
            viewport.Undo()
        before = tracer.call_count
        viewport.walls.append(Wall(point(1500, 0), point(1500, 1000)))
        viewport.ConnectedWallPath(viewport.walls)
        addedTraces = tracer.call_count
        assert addedTraces > before
        viewport.walls.pop()
        viewport.ConnectedWallPath(viewport.walls)
        # Removing the added wall restores geometry already held in the cache.
        assert tracer.call_count == addedTraces
    # Cached and fresh rendering must produce identical pixels at each view.
    for zoom in (.5, 1, 2):
        viewport.zoom = zoom
        viewport.panOffset = point(30, 80)
        image = viewport.grab().toImage()
        viewport.wallGeometryKey = None
        viewport.dimensionCacheKey = None
        assert viewport.grab().toImage() == image
    window.close()
    print("PASS: pan/zoom reuse, door dimensions, geometry edits, history, membership and identical cached rendering.")


if __name__ == "__main__":
    Main()
