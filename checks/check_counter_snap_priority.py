"""Counter endpoint and body snapping prefer geometry over a closer grid point."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Counter, Wall
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    viewport = main.viewport
    point = QtCore.QPointF
    modifiers = QtCore.Qt.KeyboardModifier.NoModifier
    viewport.snapEnabled = viewport.gridSnapEnabled = True
    viewport.connectedEnabled = False
    viewport.alignmentSnapEnabled = viewport.midpointSnapEnabled = False
    viewport.zoom = 1
    source = Counter(point(), point(800, 0), 600)
    wall = Wall(point(1130, 300), point(1130, 1300), 240)
    viewport.walls = [source, wall]
    viewport.SetSelection([(source, 1)])
    # The other cap corner can reach grid x=1000 with a 30mm correction,
    # but the real wall corner at x=1010 needs 40mm and must still win.
    snapped = viewport.SnapStairVertex(point(970, 0), point(), source, modifiers)
    assert QtCore.QLineF(snapped, point(1010, 0)).length() < .01
    assert viewport.snapPriority == 0
    viewport.SetSelection([(source, None)])
    movement = viewport.SnapObjectMovement(viewport.ObjectCorners(source), point(170, 0), modifiers,
                                           snapTargets = viewport.StairSnapTargets(source))
    assert QtCore.QLineF(movement, point(210, 0)).length() < .01
    viewport.SetSelection([(source, 1)])
    Drag(viewport, viewport.WorldToViewport(source.secondVertex).toPoint(),
         viewport.WorldToViewport(point(970, 0)).toPoint())
    assert QtCore.QLineF(source.secondVertex, point(1010, 0)).length() < .01
    viewport.Undo()
    # Midpoints have the same priority as vertices, also above grid.
    target = Counter(point(1010, 100), point(1010, 500), 100)
    viewport.walls = [source, target]
    viewport.vertexSnapEnabled = False
    viewport.midpointSnapEnabled = True
    snapped = viewport.SnapStairVertex(point(970, 0), point(), source, modifiers)
    assert QtCore.QLineF(snapped, point(1010, 0)).length() < .01
    assert viewport.snapPriority == 0
    # Alignment must also beat grid when movement follows a constrained ray.
    viewport.midpointSnapEnabled = False
    viewport.alignmentSnapEnabled = True
    viewport.walls = [source, Wall(point(1170, 1000), point(1170, 2000), 240)]
    snapped = viewport.SnapStairVertex(point(970, 0), point(), source,
                                      QtCore.Qt.KeyboardModifier.ControlModifier)
    assert abs(snapped.x() - 1050) < .01 and abs(snapped.y()) < .01
    assert viewport.snapPriority == 1 and (0, 1050.0) in viewport.alignmentGuides
    viewport.alignmentSnapEnabled = False
    snapped = viewport.SnapStairVertex(point(970, 0), point(), source, modifiers)
    assert abs(snapped.x() - 1000) < .01 and viewport.snapPriority == 2
    main.close()


if __name__ == "__main__":
    Main()
