"""Box/manual selections, shared property edits and atomic group movement."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Window, Door, Stair
from theme import BuildStyle
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.unitsMode = "Adaptive Metric"  # Property assertions below use meters and centimeters.
    point = QtCore.QPointF
    viewport.snapEnabled = False
    window.connectedOptions["vertices"].setChecked(False)
    left = QtCore.Qt.MouseButton.LeftButton
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    first = Wall(point(-1500, 600), point(1500, 600), 240)
    second = Wall(point(-1500, -600), point(1500, -600), 120, material = "Wood")
    outside = Wall(point(-2000, -1300), point(2000, -1300))
    viewport.walls = [first, second, outside]
    viewport.SetSelection([])
    app.processEvents()
    Drag(viewport, viewport.WorldToViewport(point(-1900, 1000)).toPoint(),
         viewport.WorldToViewport(point(1900, -1000)).toPoint())
    entries = viewport.SelectionEntries()
    assert len(entries) == 2 and all(index is None for obj, index in entries)
    assert {id(obj) for obj, index in entries} == {id(first), id(second)}
    # Modified boxes use the same containment rule, including grouped removal.
    boxStart = viewport.WorldToViewport(point(-1900, 1000)).toPoint()
    boxEnd = viewport.WorldToViewport(point(1900, 300)).toPoint()
    Drag(viewport, boxStart, boxEnd, ctrl)
    assert viewport.SelectionEntries() == [(second, None)]
    Drag(viewport, boxStart, boxEnd, ctrl)
    assert viewport.SelectionEntries() == [(second, None)]
    Drag(viewport, boxStart, boxEnd, shift)
    assert {id(obj) for obj, index in viewport.SelectionEntries()} == {id(first), id(second)}
    viewport.objectGroups = [(first, second)]
    viewport.SetSelection([(first, None)])
    Drag(viewport, boxEnd, boxStart, ctrl)
    assert not viewport.SelectionEntries()
    viewport.objectGroups = []
    viewport.SetSelection([(first, 0), (second, None)])
    Drag(viewport, boxStart, boxEnd, ctrl)
    assert viewport.SelectionEntries() == [(second, None)]
    # A box that only crosses a body leaves it selected.
    Drag(viewport, viewport.WorldToViewport(point(-500, -300)).toPoint(),
         viewport.WorldToViewport(point(500, -900)).toPoint(), ctrl)
    assert viewport.SelectionEntries() == [(second, None)]
    viewport.SetSelection(entries)
    assert "2 Walls" in window.selectionLabel.text()
    assert window.propertyFields["length"].value() == 3
    assert window.propertyFields["width"].lineEdit().placeholderText() == "(different)"
    assert window.materialField.currentIndex() == -1
    window.propertyFields["width"].setValue(16)
    assert first.width == second.width == 160 and len(viewport.undoHistory) == 1
    viewport.Undo()
    assert first.width == 240 and second.width == 120 and len(viewport.SelectionEntries()) == 2
    viewport.Redo()
    window.materialField.setCurrentText("Metal")
    assert first.material == second.material == "Metal"
    viewport.Undo()
    assert first.material == "Generic" and second.material == "Wood"
    app.processEvents()
    before = viewport.CaptureState()
    start = viewport.WorldToViewport(point(0, 600)).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(100, 40))
    assert first.firstVertex == point(-1000, 400) and second.firstVertex == point(-1000, -800)
    assert outside.firstVertex == point(-2000, -1300)
    viewport.Undo()
    assert viewport.CaptureState()[0] == before[0] and len(viewport.SelectionEntries()) == 2
    # Shift adds selection members; repeated Shift-clicks retain them. Ctrl removes.
    QtTest.QTest.mouseClick(viewport, left, shift, viewport.WorldToViewport(point(0, -1300)).toPoint())
    assert len(viewport.SelectionEntries()) == 3 and len(viewport.walls) == 3
    QtTest.QTest.mouseClick(viewport, left, shift, viewport.WorldToViewport(point(0, -1300)).toPoint())
    assert len(viewport.SelectionEntries()) == 3
    QtTest.QTest.mouseClick(viewport, left, ctrl, viewport.WorldToViewport(point(800, 1200)).toPoint())
    assert len(viewport.SelectionEntries()) == 3
    QtTest.QTest.mouseClick(viewport, left, ctrl, viewport.WorldToViewport(point(0, -1300)).toPoint())
    assert len(viewport.SelectionEntries()) == 2
    QtTest.QTest.mouseClick(viewport, left, ctrl, viewport.WorldToViewport(point(0, -1300)).toPoint())
    assert len(viewport.SelectionEntries()) == 2
    QtTest.QTest.mouseClick(viewport, left, shift, viewport.WorldToViewport(outside.firstVertex).toPoint())
    assert len(viewport.SelectionEntries()) == 3 and any(obj is outside and index == 0 for obj, index in viewport.SelectionEntries())
    QtTest.QTest.mouseClick(viewport, left, ctrl, viewport.WorldToViewport(outside.firstVertex).toPoint())
    assert len(viewport.SelectionEntries()) == 2
    QtTest.QTest.mouseClick(viewport, left, shift, viewport.WorldToViewport(outside.firstVertex).toPoint())
    assert len(viewport.SelectionEntries()) == 3
    app.processEvents()
    before = viewport.CaptureState()
    start = viewport.WorldToViewport(point(0, 600)).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(60, 0))
    assert outside.firstVertex == point(-1700, -1300) and outside.secondVertex == point(2000, -1300)
    viewport.Undo()
    assert viewport.CaptureState()[0] == before[0]
    opening = Window(first, .4, .6)
    viewport.windows = [opening]
    viewport.SetSelection([(first, None), (opening, None)])
    assert "Multiple types" in window.selectionLabel.text() and not window.wallProperties.isVisible()
    app.processEvents()
    start = viewport.WorldToViewport(point(-800, 600)).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(80, 0))
    assert first.firstVertex == point(-1100, 600)
    assert abs(opening.centerFraction - .5) < 1e-8 and abs(opening.length - 600) < .01
    viewport.Undo()
    # Mixed vertices share X/Y controls while retaining class properties.
    viewport.SetSelection([(first, 0), (second, 1)])
    assert window.vertexProperties.isVisible() and window.vertexProperties.title() == "Selected points (2)"
    assert window.propertyFields["x"].lineEdit().placeholderText() == "(different)"
    window.propertyFields["y"].setValue(.8)
    assert first.firstVertex.y() == 800 and second.secondVertex.y() == 800
    viewport.Undo()
    viewport.SetSelection([(first, None), (second, None)])
    viewport.DeleteSelected()
    assert len(viewport.walls) == 1 and not viewport.windows
    viewport.Undo()
    assert len(viewport.walls) == 3 and len(viewport.windows) == 1 and len(viewport.SelectionEntries()) == 2
    viewport.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "multi-selection.png"))
    window.close()
    print("PASS: containment boxes, manual body/vertex toggles, mixed classes/values, bulk edits, group moves, children, delete and undo.")


if __name__ == "__main__":
    Main()
