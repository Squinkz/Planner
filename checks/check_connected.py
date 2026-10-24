"""Run connected-wall movement checks offscreen."""

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
    window.connectedOptions["objects"].setChecked(True)
    window.snapButton.setChecked(False)
    window.connectedOptions["vertices"].setChecked(False)
    window.connectedOptions["objects"].setChecked(False)
    point = QtCore.QPointF
    source = Wall(point(0, 0), point(1500, 0))
    shared = Wall(point(1500, 0), point(1500, 800))
    interior = Wall(point(500, 50), point(500, 800))
    boundary = Wall(point(700, 100), point(700, 800))
    bothInside = Wall(point(200, -50), point(400, 50), 50)
    crossing = Wall(point(1100, -800), point(1100, 800))
    laterCollision = Wall(point(1600, 50), point(2000, 800))
    viewport.walls = [source, shared, interior, boundary, bothInside, crossing, laterCollision]
    before = viewport.CaptureState()[0]
    start = viewport.WorldToViewport(point(900, 0)).toPoint()
    end = start + QtCore.QPoint(40, -20)
    delta = point(200, 100)

    # Disabled mode moves only the selected wall.
    Drag(viewport, start, end)
    assert source.firstVertex == delta
    assert shared.firstVertex == point(1500, 0)
    viewport.Undo()
    assert viewport.CaptureState()[0] == before

    # Capture inclusive collisions at drag start and traverse attached walls.
    window.connectedOptions["vertices"].setChecked(True)
    window.connectedOptions["objects"].setChecked(True)
    assert viewport.connectedEnabled
    Drag(viewport, start, end)
    assert source.firstVertex == delta and source.secondVertex == point(1500, 0) + delta
    assert shared.firstVertex == point(1500, 0) + delta and shared.secondVertex == point(1500, 800) + delta
    assert interior.firstVertex == point(500, 50) + delta and interior.secondVertex == point(500, 800) + delta
    assert boundary.firstVertex == point(700, 100) + delta
    assert bothInside.firstVertex == point(200, -50) + delta
    assert bothInside.secondVertex == point(400, 50) + delta
    assert crossing.firstVertex == point(1100, -800) + delta and crossing.secondVertex == point(1100, 800) + delta
    assert laterCollision.firstVertex == point(1600, 50) + delta
    assert laterCollision.secondVertex == point(2000, 800) + delta
    after = viewport.CaptureState()[0]
    assert len(viewport.undoHistory) == 1
    viewport.Undo()
    assert viewport.CaptureState()[0] == before
    viewport.Redo()
    assert viewport.CaptureState()[0] == after
    viewport.Undo()

    # Escape restores every attached endpoint. Toggling Connected during a
    # drag restores or reapplies the captured group without accumulating deltas.
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    viewport.UpdateInteraction(QtCore.QPointF(end), QtCore.Qt.KeyboardModifier.NoModifier)
    assert shared.firstVertex == point(1500, 0) + delta
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Escape)
    QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.LeftButton, pos = end)
    assert viewport.CaptureState()[0] == before
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    viewport.UpdateInteraction(QtCore.QPointF(end), QtCore.Qt.KeyboardModifier.NoModifier)
    window.connectedOptions["vertices"].setChecked(False)
    window.connectedOptions["objects"].setChecked(False)
    assert shared.firstVertex == point(1500, 0)
    window.connectedOptions["vertices"].setChecked(True)
    window.connectedOptions["objects"].setChecked(True)
    assert shared.firstVertex == point(1500, 0) + delta
    viewport.CancelInteraction()
    assert viewport.CaptureState()[0] == before

    # Snap moves the whole captured group by the same delta; attached endpoints
    # cannot hold the dragged wall in place by snapping it back to itself.
    # Isolate endpoint alignment and grid behavior from midpoint targets.
    window.snapOptions["midpoints"].setChecked(False)
    window.snapButton.setChecked(True)
    Drag(viewport, start, start + QtCore.QPoint(13, -13))
    # Moving control vertices are excluded from targets. The upper cap corners
    # snap to the grid and carry attached endpoints by the same delta.
    assert source.firstVertex == point(100, 80)
    assert shared.firstVertex == point(1600, 80)
    viewport.Undo()
    window.snapButton.setChecked(False)
    endpoint = viewport.WorldToViewport(source.firstVertex).toPoint()
    Drag(viewport, endpoint, endpoint + QtCore.QPoint(-40, 20))
    assert source.firstVertex == point(-200, -100)
    assert bothInside.firstVertex == point(200, -50)
    viewport.Undo()
    assert viewport.CaptureState()[0] == before

    # A chain with a closed cycle is traversed once, including remote junctions.
    source = Wall(point(0, 0), point(1000, 0))
    child = Wall(point(1000, 0), point(1000, 1000))
    grandchild = Wall(point(1000, 1000), point(0, 1000))
    closing = Wall(point(0, 1000), point(0, 0))
    viewport.walls = [source, child, grandchild, closing]
    before = viewport.CaptureState()[0]
    start = viewport.WorldToViewport(point(500, 0)).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(40, -20))
    assert source.firstVertex == delta and source.secondVertex == point(1000, 0) + delta
    assert child.firstVertex == source.secondVertex and closing.secondVertex == source.firstVertex
    assert child.secondVertex == grandchild.firstVertex
    assert grandchild.secondVertex == closing.firstVertex
    assert grandchild.firstVertex == point(1000, 1000) + delta
    viewport.Undo()
    assert viewport.CaptureState()[0] == before

    # Coincident vertex drags move the whole junction, but not the opposite ends.
    viewport.selectedWall = source
    endpoint = viewport.WorldToViewport(source.secondVertex).toPoint()
    Drag(viewport, endpoint, endpoint + QtCore.QPoint(40, -20))
    assert source.secondVertex == point(1000, 0) + delta
    assert child.firstVertex == source.secondVertex
    assert source.firstVertex == point(0, 0) and child.secondVertex == point(1000, 1000)
    viewport.Undo()
    window.connectedOptions["vertices"].setChecked(False)
    window.connectedOptions["objects"].setChecked(False)
    viewport.selectedWall = source
    Drag(viewport, endpoint, endpoint + QtCore.QPoint(40, -20))
    assert child.firstVertex == point(1000, 0)
    viewport.Undo()

    # Control vertices can snap during whole-wall movement, ahead of face/grid alignment.
    source = Wall(point(37, 81), point(1037, 81))
    target = Wall(point(1190, 276), point(2000, 1000))
    viewport.walls = [source, target]
    viewport.selectedWall = source
    window.snapButton.setChecked(True)
    start = viewport.WorldToViewport((source.firstVertex + source.secondVertex) / 2).toPoint()
    originalLength = source.secondVertex - source.firstVertex
    Drag(viewport, start, start + QtCore.QPoint(30, -40))
    assert source.secondVertex == target.firstVertex
    assert source.secondVertex - source.firstVertex == originalLength
    viewport.Undo()
    window.snapOptions["vertices"].setChecked(False)
    window.snapOptions["alignment"].setChecked(False)
    Drag(viewport, start, start + QtCore.QPoint(30, -40))
    assert source.secondVertex != target.firstVertex
    assert source.firstVertex.x() % 100 == 0 or source.secondVertex.x() % 100 == 0

    # A moving exterior wall carries both children and their interior wall rigidly.
    window.snapButton.setChecked(False)
    window.connectedOptions["vertices"].setChecked(True)
    window.connectedOptions["objects"].setChecked(True)
    root = Wall(point(6500, 0), point(6500, -3700))
    top = Wall(point(0, 0), point(6500, 0))
    bottom = Wall(point(1200, -1800), point(6500, -1800))
    inner = Wall(point(4300, 0), point(4300, -1800))
    viewport.walls = [root, top, bottom, inner]
    viewport.selectedWall = root
    # Zoom out so the complete layout fits the offscreen viewport.
    viewport.zoom = 0.3
    viewport.panOffset = point(-200, 0)
    start = viewport.WorldToViewport(point(6500, -2700)).toPoint()
    before = viewport.CaptureState()[0]
    end = start + QtCore.QPoint(0, 60)
    Drag(viewport, start, end)
    assert top.firstVertex == point(0, -1000) and bottom.firstVertex == point(1200, -2800)
    expectedTop = top.firstVertex + (top.secondVertex - top.firstVertex) * (4300 / 6500)
    expectedBottom = bottom.firstVertex + (bottom.secondVertex - bottom.firstVertex) * (3100 / 5300)
    assert QtCore.QLineF(inner.firstVertex, expectedTop).length() < 0.001
    assert QtCore.QLineF(inner.secondVertex, expectedBottom).length() < 0.001
    assert inner.firstVertex.y() == -1000
    assert inner.secondVertex.y() == -2800
    after = viewport.CaptureState()[0]
    viewport.Undo()
    assert viewport.CaptureState()[0] == before
    viewport.Redo()
    assert viewport.CaptureState()[0] == after
    viewport.Undo()
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    viewport.UpdateInteraction(point(end), QtCore.Qt.KeyboardModifier.NoModifier)
    window.connectedOptions["vertices"].setChecked(False)
    window.connectedOptions["objects"].setChecked(False)
    assert inner.firstVertex == point(4300, 0) and inner.secondVertex == point(4300, -1800)
    window.connectedOptions["vertices"].setChecked(True)
    window.connectedOptions["objects"].setChecked(True)
    assert QtCore.QLineF(inner.firstVertex, expectedTop).length() < 0.001
    viewport.CancelInteraction()
    assert viewport.CaptureState()[0] == before
    window.close()
    print("PASS: recursive attachments and cycles, coincident vertex drags, endpoint snapping, toggles, history and cancellation.")


if __name__ == "__main__":
    Main()
