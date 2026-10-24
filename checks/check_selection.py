"""Regression check for angled-wall highlight spilling into connected walls."""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
import itertools

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
    window.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas")  # Fixed palette for pixel assertions.
    window.resize(2000, 1400)
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    for endpoint in (point(631.874553742708, 1342.576902768044), point(1200, 1200),
                     point(1400, 600), point(600, 1400)):
        diagonal = Wall(point(), endpoint, firstMiter = 0.0, secondMiter = 0.0)
        horizontal = Wall(point(), point(endpoint.x(), 0), firstMiter = 0.0, secondMiter = 0.0)
        vertical = Wall(point(), point(0, endpoint.y()), firstMiter = 0.0, secondMiter = 0.0)
        viewport.walls = [diagonal, horizontal, vertical]
        for zoom in (0.5, 1.0, 2.0):
            viewport.zoom = zoom
            viewport.panOffset = point(30, 100)
            midpoint = viewport.WorldToViewport(endpoint / 2).toPoint()
            QtTest.QTest.mouseClick(viewport, QtCore.Qt.MouseButton.LeftButton, pos = midpoint)
            assert viewport.selectedWall is diagonal and viewport.selectedVertex is None
            rendered = viewport.grab().toImage()
            selectedSample = viewport.WorldToViewport(endpoint * 0.8).toPoint()
            assert rendered.pixelColor(selectedSample).name() in ("#243947", "#72b8ff"), (endpoint, zoom, selectedSample)
            for otherPoint in (point(endpoint.x() * 0.8, 0), point(0, endpoint.y() * 0.8)):
                sample = viewport.WorldToViewport(otherPoint).toPoint()
                assert rendered.pixelColor(sample).name() in ("#20262b", "#697680"), (endpoint, zoom, sample)

    # Shared/overlapping endpoint hits favor the selected wall, independent of
    # drawing order and whether the shared endpoint is its first or second.
    viewport.ResetView()
    for reverseEndpoints in (False, True):
        selected = Wall(point(0, 1000), point(), 300, firstMiter = 0.0, secondMiter = 0.0) if reverseEndpoints else Wall(point(), point(0, 1000), 300, firstMiter = 0.0, secondMiter = 0.0)
        other = Wall(point(), point(1000, 0), 200, firstMiter = 0.0, secondMiter = 0.0)
        viewport.walls = [selected, other]
        viewport.selectedWall = selected
        expectedIndex = 1 if reverseEndpoints else 0
        sharedPoint = viewport.WorldToViewport(point())
        for offset in (point(), point(4, 2)):
            hitWall, vertexIndex = viewport.HitTest(sharedPoint + offset)
            assert hitWall is selected and vertexIndex == expectedIndex
        QtTest.QTest.mouseClick(viewport, QtCore.Qt.MouseButton.LeftButton, pos = sharedPoint.toPoint())
        assert viewport.selectedWall is selected and viewport.selectedVertex == expectedIndex
        # A different endpoint outside the selected handle retains normal hits.
        hitWall, vertexIndex = viewport.HitTest(viewport.WorldToViewport(other.secondVertex))
        assert hitWall is other and vertexIndex == 1
        viewport.selectedWall = None
        hitWall, vertexIndex = viewport.HitTest(sharedPoint)
        assert hitWall is other and vertexIndex == 0
        # right-button drawing uses the selected vertex's position and the active default width.
        viewport.selectedWall = selected
        shift = QtCore.Qt.KeyboardModifier.ShiftModifier
        QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.RightButton, shift, sharedPoint.toPoint())
        assert viewport.pendingWall is None
        QtTest.QTest.mouseMove(viewport, sharedPoint.toPoint() + QtCore.QPoint(40, -40))
        assert viewport.pendingWall.width == 200
        assert viewport.pendingWall.firstVertex == point()
        viewport.CancelInteraction()
        QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.LeftButton, pos = sharedPoint.toPoint())

    # Shared handles retain their blue outline/fill for every selected wall
    # and insertion order, with either endpoint participating in the joint.
    viewport.ResetView()
    for reverseEndpoints in (False, True):
        walls = [Wall(point(), point(0, 1000)), Wall(point(), point(1000, 0)),
                 Wall(point(), point(1000, 1000))]
        if reverseEndpoints:
            walls = [Wall(wall.secondVertex, wall.firstVertex) for wall in walls]
        sharedIndex = 1 if reverseEndpoints else 0
        sharedPoint = viewport.WorldToViewport(point()).toPoint()
        for orderedWalls in itertools.permutations(walls):
            viewport.walls = list(orderedWalls)
            for selectedWall in walls:
                viewport.selectedWall = selectedWall
                for selectedVertex in (None, sharedIndex):
                    viewport.selectedVertex = selectedVertex
                    rendered = viewport.grab().toImage()
                    bluePixels = 0
                    for x in range(sharedPoint.x() - 8, sharedPoint.x() + 9):
                        for y in range(sharedPoint.y() - 8, sharedPoint.y() + 9):
                            color = rendered.pixelColor(x, y)
                            if color.blue() > 180 and color.blue() > color.red() + 50:
                                bluePixels += 1
                    assert bluePixels >= (45 if selectedVertex is not None else 20), (reverseEndpoints, selectedVertex, bluePixels)

    # Recreate the failing dimensions for a final visual check.
    endpoint = point(631.874553742708, 1342.576902768044)
    diagonal = Wall(point(), endpoint, firstMiter = 0.0, secondMiter = 0.0)
    viewport.walls = [diagonal, Wall(point(), point(endpoint.x(), 0), firstMiter = 0.0, secondMiter = 0.0),
                      Wall(point(), point(0, endpoint.y()), firstMiter = 0.0, secondMiter = 0.0)]
    viewport.ResetView()
    viewport.selectedWall = diagonal
    window.RefreshProperties()
    app.processEvents()
    window.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "selection-preview.png"))
    window.close()
    print("PASS: isolated angled-wall highlight and selected-wall endpoint priority for shared vertices, clicks and right-button drawing.")


if __name__ == "__main__":
    Main()
