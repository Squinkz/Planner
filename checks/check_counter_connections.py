"""Either counter endpoint can join either endpoint, regardless of run direction."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Counter, Stair, Wall
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.ResetView()
    v.snapEnabled = v.vertexSnapEnabled = True
    v.gridSnapEnabled = v.alignmentSnapEnabled = v.midpointSnapEnabled = False
    v.connectedEnabled = v.connectedVerticesEnabled = True
    v.connectedObjectsEnabled = False
    point = QtCore.QPointF
    shared, near, opposite = point(), point(-25, 0), point(-1000, 0)
    for sourceIndex in (0, 1):
        for targetIndex in (0, 1):
            sourcePoints = (point(-200, 0), opposite) if sourceIndex == 0 else (opposite, point(-200, 0))
            targetPoints = (shared, point(0, 1000)) if targetIndex == 0 else (point(0, 1000), shared)
            source, target = Counter(*sourcePoints), Counter(*targetPoints, width = 400)
            v.walls, v.windows, v.furnishings, v.labels = [source, target], [], [], []
            v.SetSelection([(source, sourceIndex)])
            snapped = v.SnapStairVertex(near, opposite, source, QtCore.Qt.KeyboardModifier.NoModifier)
            assert QtCore.QLineF(snapped, shared).length() < .01, (sourceIndex, targetIndex, snapped)
            assert v.snapApplied and v.snapPriority == 0
            locked = v.SnapStairVertex(near, opposite, source, QtCore.Qt.KeyboardModifier.ControlModifier)
            assert QtCore.QLineF(locked, shared).length() < .01
            free = v.SnapStairVertex(near, opposite, source, QtCore.Qt.KeyboardModifier.AltModifier)
            assert free == near and not v.snapApplied
            history = len(v.undoHistory)
            endpoint = source.firstVertex if sourceIndex == 0 else source.secondVertex
            Drag(v, v.WorldToViewport(endpoint).toPoint(), v.WorldToViewport(near).toPoint())
            endpoint = source.firstVertex if sourceIndex == 0 else source.secondVertex
            assert QtCore.QLineF(endpoint, shared).length() < .01, (sourceIndex, targetIndex, endpoint)
            assert len(v.undoHistory) == history + 1
            v.SetSelection([(source, sourceIndex)])
            attachments = v.AttachedVertices(source)
            assert any(obj is target and index == targetIndex for obj, index, position in attachments)
            v.Undo()
            endpoint = source.firstVertex if sourceIndex == 0 else source.secondVertex
            assert endpoint == sourcePoints[sourceIndex]
            v.Redo()
            endpoint = source.firstVertex if sourceIndex == 0 else source.secondVertex
            assert endpoint == shared
    # Counter joins must not expose wall or stair control endpoints as counter targets.
    source = Counter(opposite, point(-200, 0))
    for other in (Wall(shared, point(0, 1000), 400), Stair(shared, point(0, 1000), 400)):
        v.walls = [source, other]
        v.SetSelection([(source, 1)])
        assert v.SnapStairVertex(near, opposite, source, QtCore.Qt.KeyboardModifier.NoModifier) == near
    main.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
