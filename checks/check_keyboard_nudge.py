"""Visible-grid keyboard nudging, duplication, paste in place and focus guards."""
import os
import sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow, Wall, Window
from furnishings import Furnishing
from planner_app.units import imperialModes


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    ctrlShift = QtCore.Qt.KeyboardModifier.ControlModifier | shift
    try:
        v.walls, v.windows, v.labels = [], [], []
        obj = Furnishing(v.furnishingDefinitions["desk"], point(37.25, 42.125))
        v.furnishings = [obj]
        v.SetSelection([(obj, None)])
        v.setFocus()
        v.snapEnabled = True
        for units in ("Meters", imperialModes[0]):
            v.unitsMode = units
            for zoom in (.2, 1, 3):
                v.zoom = zoom
                for key, direction in ((QtCore.Qt.Key.Key_Right, point(1, 0)), (QtCore.Qt.Key.Key_Left, point(-1, 0)),
                                       (QtCore.Qt.Key.Key_Up, point(0, 1)), (QtCore.Qt.Key.Key_Down, point(0, -1))):
                    before = v.CaptureState()
                    first = point(obj.firstVertex)
                    expected = first + direction * v.GridSteps()[1]
                    QtTest.QTest.keyClick(v, key)
                    assert QtCore.QLineF(obj.firstVertex, expected).length() < 1e-7, (units, zoom, key, obj.firstVertex, expected)
                    assert v.snapEnabled and v.dragStart is None and not v.groupDrag
                    v.Undo()
                    assert v.CaptureState() == before
        v.unitsMode = "Meters"
        v.zoom = .5
        first = point(obj.firstVertex)
        step = v.GridSteps()[1]
        v.rotationPivot = point(-1000, 0)
        v.furnishingRotationObject = obj
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Right, shift)
        assert len(v.furnishings) == 2 and obj.firstVertex == first
        duplicate = v.selectedWall
        assert QtCore.QLineF(duplicate.firstVertex, first + point(step, 0)).length() < 1e-7
        assert v.rotationPivot == point(-1000, 0) and v.furnishingRotationObject is duplicate
        v.Undo()
        assert v.furnishings == [obj]
        v.Redo()
        assert v.furnishings[-1] is duplicate
        # Connected furnishings move recursively, while duplication copies only selection.
        v.furnishings = [obj]
        other = obj.Clone()
        other.firstVertex += point(obj.width, 0)
        other.secondVertex += point(obj.width, 0)
        v.furnishings.append(other)
        v.SetSelection([(obj, None)])
        v.connectedEnabled = v.connectedObjectsEnabled = True
        otherFirst = point(other.firstVertex)
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Up)
        assert QtCore.QLineF(other.firstVertex, otherFirst + point(0, step)).length() < 1e-7
        v.Undo()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Up, shift)
        assert len(v.furnishings) == 3 and other.firstVertex == otherFirst and obj.firstVertex == first
        v.Undo()
        v.connectedEnabled = False
        v.objectGroups = [(obj, other)]
        v.SetSelection([(obj, None)])
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Down, shift)
        assert len(v.furnishings) == 4 and len(v.objectGroups) == 2 and len(v.SelectionEntries()) == 2
        v.Undo()
        v.objectGroups = []
        v.furnishings = [obj]
        # Paste in place ignores viewport position and snapping, keeping fractional coordinates.
        v.SetSelection([(obj, None)])
        assert v.CopySelection()
        v.panOffset = point(100000, 100000)
        v.hoverPosition = point(-500, -500)
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_V, ctrlShift)
        pasted = v.selectedWall
        assert pasted is not obj and pasted.firstVertex == obj.firstVertex and pasted.secondVertex == obj.secondVertex
        v.Undo()
        assert pasted not in v.furnishings
        # Architectural overlap rejects the entire paste in place.
        v.furnishings = []
        wall = Wall(point(-1500, 0), point(1500, 0), 240)
        opening = Window(wall, .3, .5)
        v.walls, v.windows = [wall], [opening]
        v.SetSelection([(wall, None)])
        # Shift nudging cannot commit a wall copy that still intersects its source.
        before = v.CaptureState()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Up, shift)
        assert v.CaptureState() == before
        assert v.CopySelection()
        before = v.CaptureState()
        assert not v.PasteSelection(inPlace = True)
        assert v.CaptureState() == before
        # Cutting then pasting retains parent and child coordinates, even offscreen.
        assert v.CutSelection()
        assert v.PasteSelection(inPlace = True)
        assert v.walls[0].firstVertex == wall.firstVertex and v.walls[0].secondVertex == wall.secondVertex
        assert v.windows[0].centerFraction == opening.centerFraction
        # Arrow keys in an input remain input keys; export rejects building shortcuts.
        v.SetSelection([(v.walls[0], None)])
        field = QtWidgets.QLineEdit(main)
        field.setText("123")
        field.show()
        field.setFocus()
        before = v.CaptureState()
        QtTest.QTest.keyClick(field, QtCore.Qt.Key.Key_Right)
        assert v.CaptureState() == before
        field.hide()
        v.exportOverlay.active = True
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Right, shift)
        assert v.CaptureState() == before
        v.exportOverlay.active = False
        print("PASS: grid nudging, Shift copies, exact paste in place, validation, history and focus/export guards.")
    finally:
        app.clipboard().clear()
        main.close()


if __name__ == "__main__":
    Main()
