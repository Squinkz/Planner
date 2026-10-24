"""Verify default toggles and right-button drawing and Shift duplication."""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from check_history import Drag
from planner import MainWindow, Wall
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    if os.path.exists("C:/Windows/Fonts/segoeui.ttf"):
        QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    leftButton = QtCore.Qt.MouseButton.LeftButton
    assert viewport.snapEnabled and viewport.connectedEnabled
    assert window.snapButton.isChecked() and viewport.connectedEnabled
    assert viewport.mode == "Select"
    buttons = [button for button in window.sidebarTabs.widget(0).findChildren(QtWidgets.QPushButton)
               if button.objectName() == "openingIconButton"]
    assert [button.accessibleName() for button in buttons] == ["Door", "Sliding Door", "Pocket Door", "Barn Door", "Bifold Door", "Open Doorway", "Window", "Silled Window", "Casement Window", "Stair", "Counter", "Railing", "Pillar", "Column", "Fireplace", "Elevator", "Label", "Arrow", "Measurement Guide", "Boundary Line", "Angle Guide", "North Arrow"]
    assert all(not button.text() and not button.icon().isNull() for button in buttons)
    assert all(button.toolTip() == button.accessibleName().capitalize() for button in buttons if button is not window.angleGuideButton)
    assert "Angle Guide" in window.angleGuideButton.toolTip()
    assert not window.snapButton.text() and window.snapButton.accessibleName() == "Snap"
    assert not window.snapButton.icon().isNull()
    assert window.snapButton.menu() is None and window.snapOptionsButton.menu() is None

    # Shift leaves Select mode active, even when another widget has keyboard focus.
    QtTest.QTest.keyPress(window.snapButton, QtCore.Qt.Key.Key_Shift)
    assert viewport.mode == "Select" and viewport.cursor().shape() == QtCore.Qt.CursorShape.ArrowCursor
    QtTest.QTest.keyRelease(window.snapButton, QtCore.Qt.Key.Key_Shift)
    assert viewport.mode == "Select" and viewport.cursor().shape() == QtCore.Qt.CursorShape.ArrowCursor

    # Plain dragging empty canvas cannot create a wall; right-button drawing snaps.
    start = QtCore.QPoint(220, 300)
    end = QtCore.QPoint(520, 300)
    Drag(viewport, start, end)
    assert not viewport.walls
    Drag(viewport, start, end, button = QtCore.Qt.MouseButton.RightButton)
    assert len(viewport.walls) == 1
    wall = viewport.walls[0]
    assert wall.width == 200.0
    assert wall.firstVertex.x() % 100 == 0 and wall.firstVertex.y() % 100 == 0
    # Alignment to the starting endpoint beats rounding cap corners to the grid.
    assert wall.secondVertex.y() == wall.firstVertex.y()
    assert abs(wall.secondVertex.x() / 100 - round(wall.secondVertex.x() / 100)) < 1e-6
    viewport.Undo()
    assert not viewport.walls
    viewport.Redo()
    assert viewport.walls[0] is wall

    # The construction preset affects new walls only and is not a drawing edit.
    historyCount = len(viewport.undoHistory)
    window.wallWidthSelector.slider.setValue(1)
    assert viewport.newWallWidth == 150.0
    assert len(viewport.undoHistory) == historyCount and wall.width == 200.0
    Drag(viewport, QtCore.QPoint(220, 450), QtCore.QPoint(520, 450), button = QtCore.Qt.MouseButton.RightButton)
    interiorWall = viewport.walls[-1]
    assert interiorWall.width == 150.0 and wall.width == 200.0
    window.wallWidthSelector.slider.setValue(3)
    assert viewport.newWallWidth == 300.0 and interiorWall.width == 150.0
    viewport.Undo()
    assert len(viewport.walls) == 1 and viewport.newWallWidth == 300.0

    # Shift on a wall body duplicates it without moving the source.
    window.snapButton.setChecked(False)
    midpoint = viewport.WorldToViewport((wall.firstVertex + wall.secondVertex) / 2).toPoint()
    sourceState = (point(wall.firstVertex), point(wall.secondVertex))
    Drag(viewport, midpoint, midpoint + QtCore.QPoint(0, -100), shift)
    branch = viewport.walls[-1]
    assert branch.firstVertex == sourceState[0] + point(0, 500)
    assert QtCore.QLineF(branch.firstVertex, branch.secondVertex).length() == QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
    assert wall.firstVertex == sourceState[0] and wall.secondVertex == sourceState[1]
    viewport.Undo()

    # Vertex starts are exact even off-grid, with snapping disabled and a click
    # a few pixels away from the handle center. A click alone makes no tiny wall.
    wall.firstVertex = point(-777, 321)
    wall.width = 300
    window.wallWidthSelector.slider.setValue(1)
    endpoint = viewport.WorldToViewport(wall.firstVertex).toPoint() + QtCore.QPoint(2, 0)
    QtTest.QTest.mouseClick(viewport, QtCore.Qt.MouseButton.RightButton, pos = endpoint)
    assert len(viewport.walls) == 1
    Drag(viewport, endpoint, endpoint + QtCore.QPoint(-80, -60), button = QtCore.Qt.MouseButton.RightButton)
    branch = viewport.walls[-1]
    assert branch.firstVertex == point(-777, 321) and branch.width == 150
    assert wall.firstVertex == point(-777, 321)
    viewport.Undo()
    window.wallWidthSelector.slider.setValue(3)

    window.snapButton.setChecked(True)
    window.connectedOptions["vertices"].setChecked(True)
    window.connectedOptions["objects"].setChecked(True)
    app.processEvents()
    window.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "preview.png"))
    window.close()
    print("PASS: default toggles, right-button drawing, duplication, preset widths for new walls and vertex branches, unchanged existing walls and history.")


if __name__ == "__main__":
    Main()
