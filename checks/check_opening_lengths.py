"""Verify fixed opening lengths, wall minimums, connected dragging and cancellation."""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtTest, QtWidgets

from check_history import Drag
from planner import MainWindow, Wall, Window, Door


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.unitsMode = "Meters"  # Property values below are explicitly in meters.
    viewport.zoom = 0.5
    window.snapButton.setChecked(False)
    window.connectedOptions["objects"].setChecked(True)
    point = QtCore.QPointF
    root = Wall(point(-1500, -1500), point(-1500, 1500))
    child = Wall(point(-1500, 0), point(2500, 0))
    opening = Window(child, 0.2, 0.5)
    door = Door(child, 0.65, 0.875)
    viewport.walls = [root, child]
    viewport.windows = [opening, door]
    before = viewport.CaptureState()
    start = viewport.WorldToViewport(point(-1500, -800)).toPoint()
    end = start + QtCore.QPoint(75, 0)
    Drag(viewport, start, end)
    assert child.firstVertex == point(-750, 0)
    for item, length in ((opening, 1200), (door, 900)):
        assert abs(item.length - length) < 0.001
        assert abs(QtCore.QLineF(item.firstVertex, item.secondVertex).length() - length) < 0.001
        assert 0 <= item.firstFraction < item.secondFraction <= 1
    assert viewport.OpeningsValid()
    after = viewport.CaptureState()
    viewport.Undo()
    assert viewport.CaptureState()[0] == before[0] and viewport.CaptureState()[3] == before[3]
    viewport.Redo()
    assert viewport.CaptureState()[0] == after[0] and viewport.CaptureState()[3] == after[3]
    viewport.Undo()

    # Switching Connected Objects restores/reapplies openings without scale or drift.
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    viewport.UpdateInteraction(point(end), QtCore.Qt.KeyboardModifier.NoModifier)
    expected = (point(opening.firstVertex), point(door.firstVertex))
    window.connectedOptions["objects"].setChecked(False)
    window.connectedOptions["vertices"].setChecked(False)
    assert child.firstVertex == point(-1500, 0)
    assert opening.centerFraction == before[3][0][2]
    window.connectedOptions["objects"].setChecked(True)
    assert opening.firstVertex == expected[0] and door.firstVertex == expected[1]
    viewport.CancelInteraction()
    assert viewport.CaptureState()[0] == before[0] and viewport.CaptureState()[3] == before[3]

    # Vertex following cannot shrink its child below the total opening lengths.
    window.connectedOptions["objects"].setChecked(False)
    window.connectedOptions["vertices"].setChecked(True)
    Drag(viewport, start, start + QtCore.QPoint(270, 0))
    assert viewport.CaptureState()[0] == before[0]
    assert viewport.CaptureState()[3] == before[3]

    viewport.walls = [child]
    # Length edits clamp at the combined minimum and pack both openings intact.
    viewport.selectedWall = child
    viewport.selectedVertex = None
    window.RefreshProperties()
    assert abs(window.propertyFields["length"].minimum() - 2.1) < 0.001
    window.EditProperty("length", 1.0)
    assert abs(QtCore.QLineF(child.firstVertex, child.secondVertex).length() - 2100) < 0.001
    assert abs(QtCore.QLineF(opening.firstVertex, opening.secondVertex).length() - 1200) < 0.001
    assert abs(QtCore.QLineF(door.firstVertex, door.secondVertex).length() - 900) < 0.001
    assert QtCore.QLineF(opening.secondVertex, door.firstVertex).length() < 0.001
    viewport.Undo()
    assert viewport.CaptureState()[3] == before[3]

    # Endpoint dragging stops at the same physical minimum.
    viewport.selectedWall = child
    endpoint = viewport.WorldToViewport(child.secondVertex).toPoint()
    target = viewport.WorldToViewport(point(-1000, 0)).toPoint()
    Drag(viewport, endpoint, target)
    assert abs(QtCore.QLineF(child.firstVertex, child.secondVertex).length() - 2100) < 0.001
    assert viewport.OpeningsValid()
    viewport.Undo()

    # Icon controls remain ordinary history edits.
    viewport.selectedWall = door
    viewport.selectedVertex = None
    window.RefreshProperties()
    for fieldName, attribute in (("swing", "swingsOutwards"), ("hinge", "hingeAtSecond")):
        button = window.doorFields[fieldName]
        assert isinstance(button, QtWidgets.QPushButton) and not button.isCheckable()
        QtTest.QTest.mouseClick(button, QtCore.Qt.MouseButton.LeftButton)
        assert getattr(door, attribute) and not button.text() and not button.icon().isNull()
        viewport.Undo()
        assert not getattr(door, attribute) and not button.isChecked()
    window.close()
    print("PASS: fixed lengths, connected wall deformation, minimum bounds, packing, cancellation, undo/redo and binary controls.")


if __name__ == "__main__":
    Main()
