"""Wall control vertices win over footprint, midpoint, alignment and grid snaps."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    viewport = main.viewport
    viewport.ResetView()
    viewport.snapEnabled = viewport.vertexSnapEnabled = True
    viewport.gridSnapEnabled = viewport.alignmentSnapEnabled = viewport.midpointSnapEnabled = True
    viewport.connectedEnabled = viewport.connectedVerticesEnabled = True
    viewport.connectedObjectsEnabled = False
    point = QtCore.QPointF
    shared = point(37, 43)
    opposite = shared + point(90, -1250)
    near = shared + point(-8, -5)
    initial = shared + point(-40, -180)
    for sourceIndex in (0, 1):
        for targetIndex in (0, 1):
            sourcePoints = (initial, opposite) if sourceIndex == 0 else (opposite, initial)
            targetPoints = (shared, shared + point(0, 1400)) if targetIndex == 0 else (shared + point(0, 1400), shared)
            source, target = Wall(*sourcePoints, 240), Wall(*targetPoints, 240)
            viewport.walls = [source, target]
            viewport.windows, viewport.furnishings, viewport.labels = [], [], []
            viewport.SetSelection([(source, sourceIndex)])
            snapped = viewport.SnapStairVertex(near, opposite, source, QtCore.Qt.KeyboardModifier.NoModifier)
            assert snapped == shared, (sourceIndex, targetIndex, snapped)
            assert viewport.snapApplied and viewport.snapPriority == 0 and not viewport.alignmentGuides
            # The other wall's midpoint is even closer than its endpoint.
            distractor = Wall(near + point(-400, -600), near + point(400, 600), 80)
            viewport.walls.append(distractor)
            assert viewport.SnapStairVertex(near, opposite, source, QtCore.Qt.KeyboardModifier.NoModifier) == shared
            viewport.walls.remove(distractor)
            assert viewport.SnapStairVertex(near, opposite, source, QtCore.Qt.KeyboardModifier.AltModifier) == near
            assert not viewport.snapApplied
            history = len(viewport.undoHistory)
            Drag(viewport, viewport.WorldToViewport(initial).toPoint(), viewport.WorldToViewport(near).toPoint())
            endpoint = source.firstVertex if sourceIndex == 0 else source.secondVertex
            assert endpoint == shared, (sourceIndex, targetIndex, endpoint)
            assert len(viewport.undoHistory) == history + 1
            viewport.SetSelection([(source, sourceIndex)])
            assert any(obj is target and index == targetIndex for obj, index, position in viewport.AttachedVertices(source))
            viewport.Undo()
            assert (source.firstVertex if sourceIndex == 0 else source.secondVertex) == initial
            viewport.Redo()
            assert (source.firstVertex if sourceIndex == 0 else source.secondVertex) == shared
    main.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
