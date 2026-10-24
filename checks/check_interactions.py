"""Run offscreen interaction checks with: python check_interactions.py."""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from planner import MainWindow, Wall
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    fontPath = "C:/Windows/Fonts/segoeui.ttf"
    if os.path.exists(fontPath):
        QtGui.QFontDatabase.addApplicationFont(fontPath)
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.unitsMode = "Adaptive Metric"
    leftButton = QtCore.Qt.MouseButton.LeftButton
    assert window.snapButton.isChecked() and viewport.connectedEnabled
    window.snapButton.setChecked(False)
    window.connectedOptions["vertices"].setChecked(False)
    window.connectedOptions["objects"].setChecked(False)
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    start = QtCore.QPoint(220, 300)
    end = QtCore.QPoint(520, 300)
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.RightButton, shift, start)
    QtTest.QTest.mouseMove(viewport, end)
    assert len(viewport.walls) == 0 and viewport.pendingWall is not None
    QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.RightButton, shift, end)
    assert len(viewport.walls) == 1
    wall = viewport.walls[0]
    assert wall.width == 200.0
    assert QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() == 1500.0
    QtTest.QTest.mouseClick(viewport, leftButton, pos = start)
    assert len(viewport.walls) == 1  # A click cannot create a zero-length wall.

    midpoint = QtCore.QPoint(370, 300)
    QtTest.QTest.mouseClick(viewport, leftButton, pos = midpoint)
    assert viewport.selectedWall is wall and viewport.selectedVertex is None
    assert window.wallProperties.isVisible() and not window.vertexProperties.isVisible()
    assert window.propertyFields["length"].value() == 1.5
    originalFirst = QtCore.QPointF(wall.firstVertex)
    originalSecond = QtCore.QPointF(wall.secondVertex)
    QtTest.QTest.mousePress(viewport, leftButton, pos = midpoint)
    QtTest.QTest.mouseMove(viewport, midpoint + QtCore.QPoint(40, -20))
    QtTest.QTest.mouseRelease(viewport, leftButton, pos = midpoint + QtCore.QPoint(40, -20))
    assert wall.firstVertex == originalFirst + QtCore.QPointF(200, 100)
    assert wall.secondVertex == originalSecond + QtCore.QPointF(200, 100)

    fixedFirst = QtCore.QPointF(wall.firstVertex)
    window.propertyFields["length"].setValue(2.0)
    assert window.propertyFields["width"].value() == 20.0
    assert window.propertyFields["width"].suffix() == " cm"
    window.propertyFields["width"].setValue(30.0)
    assert wall.firstVertex == fixedFirst
    assert wall.secondVertex == fixedFirst + QtCore.QPointF(2000, 0)
    assert wall.width == 300.0

    endpoint = viewport.WorldToViewport(wall.secondVertex).toPoint()
    QtTest.QTest.mouseClick(viewport, leftButton, pos = endpoint)
    assert viewport.selectedVertex == 1 and window.vertexProperties.isVisible()
    QtTest.QTest.mousePress(viewport, leftButton, pos = endpoint)
    QtTest.QTest.mouseMove(viewport, endpoint + QtCore.QPoint(0, -80))
    QtTest.QTest.mouseRelease(viewport, leftButton, pos = endpoint + QtCore.QPoint(0, -80))
    assert wall.firstVertex == fixedFirst
    assert wall.secondVertex.y() == fixedFirst.y() + 400
    window.propertyFields["x"].setValue(1.2)
    window.propertyFields["y"].setValue(0.8)
    assert wall.secondVertex == QtCore.QPointF(1200, 800)

    # A diagonal length edit keeps direction and anchors the first vertex.
    viewport.selectedVertex = None
    window.RefreshProperties()
    oldDirection = wall.secondVertex - wall.firstVertex
    window.propertyFields["length"].setValue(3.0)
    newDirection = wall.secondVertex - wall.firstVertex
    assert abs(QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() - 3000) < 1e-8
    assert abs(oldDirection.x() * newDirection.y() - oldDirection.y() * newDirection.x()) < 1e-6
    assert wall.firstVertex == fixedFirst

    # Escape rolls back a vertex drag and discards an unfinished wall.
    endpoint = viewport.WorldToViewport(wall.firstVertex).toPoint()
    QtTest.QTest.mousePress(viewport, leftButton, pos = endpoint)
    QtTest.QTest.mouseMove(viewport, endpoint + QtCore.QPoint(30, 30))
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Escape)
    QtTest.QTest.mouseRelease(viewport, leftButton, pos = endpoint + QtCore.QPoint(30, 30))
    assert wall.firstVertex == fixedFirst
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.RightButton, shift, start)
    QtTest.QTest.mouseMove(viewport, end)
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Escape)
    QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.RightButton, shift, end)
    assert viewport.pendingWall is None and len(viewport.walls) == 1

    # Snapping tracks minor visible grid lines at each scale, with Alt inversion.
    window.snapOptions["alignment"].setChecked(False)
    noModifiers = QtCore.Qt.KeyboardModifier.NoModifier
    altModifier = QtCore.Qt.KeyboardModifier.AltModifier
    for zoom, expectedStep in ((0.02, 10000.0), (1.0, 100.0), (10.0, 10.0), (100.0, 1.0)):
        viewport.zoom = zoom
        assert viewport.GridSteps()[1] == expectedStep
        position = QtCore.QPointF(0.37 * expectedStep, -0.72 * expectedStep)
        snapped = QtCore.QPointF(0, -expectedStep)
        for enabled in (False, True):
            window.snapButton.setChecked(enabled)
            assert viewport.SnapPosition(position, noModifiers) == (snapped if enabled else position)
            assert viewport.SnapPosition(position, altModifier) == (position if enabled else snapped)
    viewport.ResetView()
    window.snapButton.setChecked(True)
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.RightButton, shift, start)
    QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.RightButton, shift, end)
    assert len(viewport.walls) == 2
    vertex = viewport.walls[-1].secondVertex
    assert abs(vertex.x() / 100 - round(vertex.x() / 100)) < 1e-6
    assert abs(vertex.y() / 100 - round(vertex.y() / 100)) < 1e-6

    # Pressing/releasing Alt during an active drag updates without mouse motion.
    endpoint = viewport.WorldToViewport(wall.firstVertex).toPoint()
    QtTest.QTest.mousePress(viewport, leftButton, pos = endpoint)
    target = QtCore.QPointF(endpoint + QtCore.QPoint(33, -27))
    viewport.UpdateInteraction(target, noModifiers)
    assert abs(wall.firstVertex.x() / 100 - round(wall.firstVertex.x() / 100)) < 1e-6
    assert abs(wall.firstVertex.y() / 100 - round(wall.firstVertex.y() / 100)) < 1e-6
    rawTarget = fixedFirst + (viewport.ViewportToWorld(target) - viewport.ViewportToWorld(QtCore.QPointF(endpoint)))
    QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_Alt)
    assert window.snapButton.isChecked() != viewport.snapEnabled
    assert (wall.firstVertex - rawTarget).manhattanLength() < 1e-8
    QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_Alt)
    assert window.snapButton.isChecked() == viewport.snapEnabled
    assert abs(wall.firstVertex.x() / 100 - round(wall.firstVertex.x() / 100)) < 1e-6
    assert abs(wall.firstVertex.y() / 100 - round(wall.firstVertex.y() / 100)) < 1e-6
    viewport.CancelInteraction()
    window.snapButton.setChecked(False)
    QtTest.QTest.mousePress(viewport, leftButton, pos = endpoint)
    viewport.UpdateInteraction(target, noModifiers)
    assert (wall.firstVertex - rawTarget).manhattanLength() < 1e-8
    QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_Alt)
    assert window.snapButton.isChecked() != viewport.snapEnabled
    assert abs(wall.firstVertex.x() / 100 - round(wall.firstVertex.x() / 100)) < 1e-6
    assert abs(wall.firstVertex.y() / 100 - round(wall.firstVertex.y() / 100)) < 1e-6
    QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_Alt)
    assert window.snapButton.isChecked() == viewport.snapEnabled
    assert (wall.firstVertex - rawTarget).manhattanLength() < 1e-8
    viewport.CancelInteraction()

    # Snapping a wall body preserves both its direction and length.
    window.snapButton.setChecked(True)
    viewport.selectedWall = wall
    viewport.selectedVertex = None
    viewport.dragStart = viewport.WorldToViewport((wall.firstVertex + wall.secondVertex) / 2)
    viewport.dragVertices = (QtCore.QPointF(wall.firstVertex), QtCore.QPointF(wall.secondVertex))
    direction = wall.secondVertex - wall.firstVertex
    viewport.UpdateInteraction(viewport.dragStart + QtCore.QPointF(33, -27), noModifiers)
    assert (wall.secondVertex - wall.firstVertex - direction).manhattanLength() < 1e-8
    assert any(abs(corner.x() / 100 - round(corner.x() / 100)) < 1e-6
               and abs(corner.y() / 100 - round(corner.y() / 100)) < 1e-6
               for corner in viewport.ObjectCorners(wall) + [wall.firstVertex, wall.secondVertex])
    viewport.CancelInteraction()

    for zoom in (0.02, 1.0, 100.0):
        viewport.zoom = zoom
        assert not viewport.grab().isNull()
    viewport.ResetView()
    # Existing off-grid vertices take priority over nearby grid intersections.
    snapWall = Wall(QtCore.QPointF(37, 23), QtCore.QPointF(837, 23), firstMiter = 0.0, secondMiter = 0.0)
    viewport.walls = [snapWall]
    viewport.selectedWall = None
    viewport.snapEnabled = True
    assert viewport.SnapPosition(QtCore.QPointF(47, 33), noModifiers) == snapWall.firstVertex
    assert viewport.SnapPosition(QtCore.QPointF(47, 33), altModifier) == QtCore.QPointF(47, 33)
    # Exclude the dragged vertex itself, preventing it from sticking to its old position.
    viewport.selectedWall = snapWall
    viewport.selectedVertex = 0
    viewport.dragStart = viewport.WorldToViewport(snapWall.firstVertex)
    assert viewport.SnapPosition(QtCore.QPointF(47, 33), noModifiers) == QtCore.QPointF(0, 0)
    viewport.dragStart = None

    cornerWalls = [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(), firstMiter = 0.0, secondMiter = 0.0),
                   Wall(QtCore.QPointF(), QtCore.QPointF(0, 1000), firstMiter = 0.0, secondMiter = 0.0)]
    cornerPoint = viewport.WorldToViewport(QtCore.QPointF(80, -80))
    assert not any(viewport.WallPolygon(item).containsPoint(cornerPoint, QtCore.Qt.FillRule.OddEvenFill) for item in cornerWalls)
    assert viewport.ConnectedWallPath(cornerWalls).contains(cornerPoint)
    viewport.walls = cornerWalls
    assert viewport.HitTest(cornerPoint)[0] is not None
    reversedWalls = [Wall(item.secondVertex, item.firstVertex, item.width, firstMiter = 0.0, secondMiter = 0.0) for item in cornerWalls]
    assert viewport.ConnectedWallPath(reversedWalls).contains(cornerPoint)
    cornerWalls[0].width = 300
    assert viewport.ConnectedWallPath(cornerWalls).contains(viewport.WorldToViewport(QtCore.QPointF(80, -140)))
    crossingWalls = [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), firstMiter = 0.0, secondMiter = 0.0),
                     Wall(QtCore.QPointF(0, -1000), QtCore.QPointF(0, 1000), firstMiter = 0.0, secondMiter = 0.0)]
    crossingPath = viewport.ConnectedWallPath(crossingWalls)
    # Former wall edges at the crossing are now inside the combined fill.
    assert crossingPath.contains(viewport.WorldToViewport(QtCore.QPointF(0, 100)))
    assert crossingPath.contains(viewport.WorldToViewport(QtCore.QPointF(100, 0)))
    assert len(crossingPath.toSubpathPolygons()) == 1

    # Render a room corner and a separate crossing for visual inspection.
    viewport.walls = [Wall(QtCore.QPointF(-1600, -800), QtCore.QPointF(-1600, 1200), firstMiter = 0.0, secondMiter = 0.0),
                      Wall(QtCore.QPointF(-1600, 1200), QtCore.QPointF(-400, 1200), firstMiter = 0.0, secondMiter = 0.0),
                      Wall(QtCore.QPointF(-400, 1200), QtCore.QPointF(-400, -800), firstMiter = 0.0, secondMiter = 0.0),
                      Wall(QtCore.QPointF(300, 0), QtCore.QPointF(1800, 0), firstMiter = 0.0, secondMiter = 0.0),
                      Wall(QtCore.QPointF(1000, -1000), QtCore.QPointF(1000, 1000), firstMiter = 0.0, secondMiter = 0.0)]
    wall = viewport.walls[0]
    viewport.selectedWall = wall
    viewport.selectedVertex = None
    window.RefreshProperties()
    app.processEvents()
    window.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "preview.png"))
    window.close()
    print("PASS: wall interactions, snapping and Alt inversion, off-grid vertex priority, corner miters, unequal widths, crossing union and rendering.")


if __name__ == "__main__":
    Main()
