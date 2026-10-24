"""Verify independent Connected Points and Connected Objects controls."""

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
    point = QtCore.QPointF
    noModifiers = QtCore.Qt.KeyboardModifier.NoModifier
    window.snapButton.setChecked(False)
    assert window.connectedOptions["vertices"].isChecked() and viewport.connectedVerticesEnabled
    assert window.connectedOptions["vertices"].accessibleName() == "Connected Points"
    assert window.connectedOptions["vertices"].toolTip() == "Move connected points together"
    assert not window.connectedOptions["objects"].isChecked() and not viewport.connectedObjectsEnabled
    source = Wall(point(), point(1500, 0))
    shared = Wall(point(1500, 0), point(1500, 800))
    interior = Wall(point(500, 50), point(500, 800))
    descendant = Wall(point(1500, 400), point(2200, 400))
    contained = Wall(point(200, 30), point(400, 30), 80)
    crossing = Wall(point(1000, -800), point(1000, 800), 80)
    viewport.walls = [source, shared, interior, descendant, contained, crossing]
    body = viewport.WorldToViewport(point(900, 0)).toPoint()
    vertex = viewport.WorldToViewport(source.secondVertex).toPoint()
    delta = point(200, 100)
    for vertices, objects in ((True, True), (True, False), (False, True), (False, False)):
        window.connectedOptions["vertices"].setChecked(vertices)
        window.connectedOptions["objects"].setChecked(objects)
        Drag(viewport, body, body + QtCore.QPoint(40, -20))
        assert source.firstVertex == delta
        assert shared.firstVertex == point(1500, 0) + (delta if vertices or objects else point())
        assert interior.firstVertex == point(500, 50) + (delta if vertices or objects else point())
        assert contained.firstVertex == point(200, 30) + (delta if vertices or objects else point())
        assert contained.secondVertex == point(400, 30) + (delta if vertices or objects else point())
        assert crossing.firstVertex == point(1000, -800) + (delta if objects else point())
        assert crossing.secondVertex == point(1000, 800) + (delta if objects else point())
        assert shared.secondVertex == point(1500, 800) + (delta if objects else point())
        assert interior.secondVertex == point(500, 800) + (delta if objects else point())
        assert (descendant.firstVertex != point(1500, 400)) == objects
        viewport.Undo()
        viewport.selectedWall = source
        Drag(viewport, vertex, vertex + QtCore.QPoint(40, -20))
        assert shared.firstVertex == point(1500, 0) + (delta if vertices else point())
        assert interior.firstVertex == point(500, 50) and descendant.firstVertex == point(1500, 400)
        viewport.Undo()

    # Empty choices disable connections; checking either restores only that behavior.
    assert not viewport.connectedEnabled and not hasattr(window, "connectedButton")
    window.connectedOptions["vertices"].setChecked(True)
    assert viewport.connectedEnabled and not viewport.connectedObjectsEnabled
    window.connectedOptions["objects"].setChecked(True)

    # Changing an option mid-drag restores or reapplies the original group.
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = body)
    viewport.UpdateInteraction(point(body + QtCore.QPoint(40, -20)), noModifiers)
    window.connectedOptions["objects"].setChecked(False)
    assert shared.firstVertex == point(1500, 0) + delta
    assert interior.firstVertex == point(500, 50) + delta and descendant.firstVertex == point(1500, 400)
    assert contained.firstVertex == point(200, 30) + delta and crossing.firstVertex == point(1000, -800)
    window.connectedOptions["vertices"].setChecked(False)
    assert shared.firstVertex == point(1500, 0)
    window.connectedOptions["vertices"].setChecked(True)
    window.connectedOptions["objects"].setChecked(True)
    assert interior.firstVertex == point(500, 50) + delta
    viewport.CancelInteraction()
    assert source.firstVertex == point() and shared.firstVertex == point(1500, 0)

    # Coincident vertices being carried by a wall cannot snap it back to itself.
    window.connectedOptions["objects"].setChecked(False)
    window.snapOptions["grid"].setChecked(False)
    window.snapOptions["alignment"].setChecked(False)
    window.snapButton.setChecked(True)
    Drag(viewport, body, body + QtCore.QPoint(6, -6))
    assert source.firstVertex == point(30, 30)
    assert shared.firstVertex == source.secondVertex
    viewport.Undo()
    window.close()
    print("PASS: independent Connected modes, checkbox rules, mid-drag toggles, carried-vertex snapping and history.")


if __name__ == "__main__":
    Main()
