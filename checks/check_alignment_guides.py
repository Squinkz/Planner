"""Verify alignment guide coordinates, chosen roots and drag cleanup."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow, Wall


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    noModifiers = QtCore.Qt.KeyboardModifier.NoModifier
    window.connectedOptions["vertices"].setChecked(False)
    window.snapOptions["vertices"].setChecked(False)
    source = Wall(point(), point(1000, 0))
    target = Wall(point(1037, 900), point(1037, 1500))
    viewport.walls = [source, target]
    viewport.selectedWall = source
    start = viewport.WorldToViewport(source.firstVertex).toPoint()
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    position = viewport.WorldToViewport(point(1020, 200))
    viewport.UpdateInteraction(position, noModifiers)
    firstPreview = point(source.firstVertex)
    viewport.UpdateInteraction(position, noModifiers)
    assert source.firstVertex == firstPreview
    # A cap corner can snap without advertising alignment of the dragged vertex.
    assert viewport.alignmentGuides == []
    assert any(abs(corner.x() - 1157) < .01 for corner in viewport.ObjectCorners(source))
    viewport.UpdateInteraction(position, QtCore.Qt.KeyboardModifier.AltModifier)
    assert viewport.alignmentGuides == []
    viewport.UpdateInteraction(position, noModifiers)
    assert viewport.alignmentGuides == []
    QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.LeftButton, pos = position.toPoint())
    assert viewport.alignmentGuides == []
    viewport.Undo()

    # The first endpoint wins even though the second endpoint is evaluated last.
    start = viewport.WorldToViewport(point(500, 0)).toPoint()
    viewport.selectedWall = source
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    viewport.UpdateInteraction(point(start) + point(204, -40), noModifiers)
    assert viewport.alignmentGuides == [(0, 1037)]
    assert abs(source.firstVertex.x() - 1037) < .01
    viewport.CancelInteraction()
    assert viewport.alignmentGuides == []

    # Horizontal alignment and disabled options cannot leave stale guides.
    window.snapOptions["vertices"].setChecked(True)
    viewport.SnapPosition(point(600, 880), noModifiers)
    assert viewport.alignmentGuides == [(1, 900)]
    window.snapOptions["alignment"].setChecked(False)
    viewport.SnapPosition(point(600, 880), noModifiers)
    assert viewport.alignmentGuides == []
    # X and Y can come from two distinct vertices, with both guides rendered.
    window.snapOptions["vertices"].setChecked(False)
    window.snapOptions["alignment"].setChecked(True)
    other = Wall(point(1800, 263), point(1800, 1500))
    viewport.walls = [source, target, other]
    viewport.selectedWall = source
    start = viewport.WorldToViewport(source.firstVertex).toPoint()
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    position = viewport.WorldToViewport(point(1020, 250))
    viewport.UpdateInteraction(position, noModifiers)
    assert any(QtCore.QLineF(corner, point(917, 263)).length() < .01 for corner in viewport.ObjectCorners(source))
    assert viewport.alignmentGuides == []
    QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.LeftButton, pos = position.toPoint())
    assert viewport.alignmentGuides == []
    # A grid winner clears previous hints and reports its actual snap class.
    source = Wall(point(), point(1000, 0), 120)
    viewport.walls, viewport.windows = [source], []
    viewport.selectedWall, viewport.selectedVertex = source, 1
    viewport.dragStart = point()
    viewport.midpointSnapEnabled = False
    viewport.alignmentGuides = [(0, 0)]
    viewport.SnapStairVertex(point(647, 347), point(), source, noModifiers)
    assert viewport.snapPriority == 2 and viewport.alignmentGuides == []
    viewport.alignmentGuides = [(0, 0)]
    viewport.SnapObjectMovement([point()], point(647, 347), noModifiers, snapTargets = [])
    assert viewport.snapPriority == 2 and viewport.alignmentGuides == []
    # Genuine control-vertex alignment still displays its guide.
    # This helper-only fixture supplies dragStart but no complete mouse gesture;
    # avoid a checkbox callback that would replay an incomplete drag.
    viewport.vertexSnapEnabled = True
    target = viewport.SnapStairVertex(point(20, -600), point(), source, noModifiers)
    assert abs(target.x()) < .01 and viewport.alignmentGuides == [(0, 0)]
    viewport.CancelInteraction()
    window.close()
    print("PASS: guide rendering, chosen wall endpoint, projected X/Y intersections, Alt, release and cancellation.")


if __name__ == "__main__":
    Main()
