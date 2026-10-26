"""Shift on an opening control point resizes symmetrically without extrusion."""
import math
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow
from planner_app.models import (Wall, Window, Door, OpenDoorway, SilledWindow, CasementWindow,
    SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, SwingingDoor, DoubleDoor, AwningWindow, DoubleCasementWindow)
from planner_app.geometry.opening_placement import CenteredOpeningSpan
from planner_app.viewport import rendering


class TipRows(dict):
    def __getitem__(self, key):
        self.used.add(key)
        return super().__getitem__(key)


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.snapEnabled = False
    v.showTips = True
    assert rendering.toolTipRows["angle"][1] == "Snap to 15\u00b0 increments"
    assert rendering.toolTipRows["localAngle"][1] == "Snap to local 15\u00b0 increments"
    assert rendering.toolTipRows["center"] == ("Shift", "Expand from center")
    v.zoom = .75
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    plain = QtCore.Qt.KeyboardModifier.NoModifier
    point = QtCore.QPointF
    for openingType in (Window, Door, OpenDoorway, SilledWindow, CasementWindow, SlidingDoor, PocketDoor, BarnDoor,
                        BifoldDoor, SwingingDoor, DoubleDoor, AwningWindow, DoubleCasementWindow):
        for angle in (0, 37, 90):
            direction = point(math.cos(math.radians(angle)), math.sin(math.radians(angle)))
            for index in (0, 1):
                wall = Wall(direction * -2000, direction * 2000, 200)
                opening = openingType(wall, .4, .6)
                v.walls = [wall]
                v.windows = [opening]
                v.SetSelection([(opening, index)])
                endpoint = opening.firstVertex if index == 0 else opening.secondVertex
                # Advertise centered resizing while dragging normally, before
                # the user knows to hold Shift.
                QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, plain, v.WorldToViewport(endpoint).toPoint())
                target = v.dragStart + v.WorldToViewport(direction * (-100 if index == 0 else 100)) - v.WorldToViewport(point())
                v.UpdateInteraction(target, plain)
                rows = TipRows(rendering.toolTipRows)
                rows.used = set()
                with patch.object(rendering, "toolTipRows", rows):
                    v.grab()
                assert "center" in rows.used and "extrude" not in rows.used and "duplicate" not in rows.used
                v.CancelInteraction()
                QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, plain, target.toPoint())
                v.SetSelection([(opening, index)])
                QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, shift, v.WorldToViewport(endpoint).toPoint())
                assert v.dragSource is opening and v.dragSourceVertex == index
                assert v.boxStart is None, "Shift on a control point started box selection"
                delta = direction * (-300 if index == 0 else 300)
                target = v.dragStart + v.WorldToViewport(delta) - v.WorldToViewport(point())
                for unused in range(2):
                    v.UpdateInteraction(target, shift)
                    assert v.windows == [opening] and not v.dragCopies
                    assert abs(opening.length - 1400) < 1e-6, (openingType, angle, index, opening.length)
                    assert abs(opening.centerFraction - .5) < 1e-10
                rows = TipRows(rendering.toolTipRows)
                rows.used = set()
                with patch.object(rendering, "toolTipRows", rows):
                    v.grab()
                assert "center" in rows.used and "extrude" not in rows.used and "duplicate" not in rows.used
                assert "angle" not in rows.used and "localAngle" not in rows.used, "Opening point advertised angle snapping"
                v.UpdateInteraction(target, plain)
                assert abs(opening.length - 1100) < 1e-6
                fixed = opening.secondVertex if index == 0 else opening.firstVertex
                assert QtCore.QLineF(fixed, direction * (400 if index == 0 else -400)).length() < 1e-6
                v.UpdateInteraction(target, shift)
                assert abs(opening.centerFraction - .5) < 1e-10
                QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, shift, target.toPoint())
                assert len(v.windows) == 1 and abs(opening.centerFraction - .5) < 1e-10
                committed = opening.length
                v.Undo()
                assert abs(opening.length - 800) < 1e-6
                v.Redo()
                assert abs(opening.length - committed) < 1e-6

    # Limits apply symmetrically, including on the side opposite the cursor.
    wall = Wall(point(0, 0), point(4000, 0), 200)
    opening = Door(wall, .4, .6)
    sibling = Window(wall, .65, .8)
    v.walls, v.windows = [wall], [opening, sibling]
    v.SetOpeningVertex(opening, 0, point(0, 0), fromCenter = True)
    assert abs(opening.firstFraction - .35) < 1e-10 and abs(opening.secondFraction - .65) < 1e-10
    v.windows = [opening]
    v.SetOpeningVertex(opening, 0, point(-1000, 0), fromCenter = True)
    assert opening.firstFraction == 0 and opening.secondFraction == 1
    v.SetOpeningVertex(opening, 0, point(3000, 0), fromCenter = True)
    assert abs(opening.length - 1) < 1e-6 and opening.centerFraction == .5
    assert CenteredOpeningSpan((0, 0), (0, 0), (0, 0), 0, .5, 0, 1) is None
    assert CenteredOpeningSpan((0, 0), (4000, 0), (0, 0), 0, .5, .5, .5) is None
    # Snapping still resolves the grabbed point first; its partner mirrors the
    # snapped movement. Cancelling restores the original span and object count.
    opening.SetFractions(.4, .6)
    v.SetSelection([(opening, 0)])
    v.snapEnabled = True
    start = v.WorldToViewport(opening.firstVertex).toPoint()
    QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, plain, start)
    target = v.dragStart + point(-31, 0)
    worldTarget = v.dragVertices[0] + v.ViewportToWorld(target) - v.ViewportToWorld(v.dragStart)
    snapped = v.SnapPosition(worldTarget, shift, wall.firstVertex, point(1, 0))
    v.UpdateInteraction(target, shift)
    assert QtCore.QLineF(opening.firstVertex, snapped).length() < 1e-6
    assert abs(opening.centerFraction - .5) < 1e-10
    v.CancelInteraction()
    assert v.windows == [opening] and abs(opening.length - 800) < 1e-6
    QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, plain, target.toPoint())
    main.MarkProjectClean()
    main.close()


if __name__ == "__main__":
    Main()
