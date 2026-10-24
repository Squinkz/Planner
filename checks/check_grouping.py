"""Group shortcuts, mode, membership changes, selection, movement and history."""
import os
import sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Stair, Door
from furnishings import Furnishing
from theme import BuildStyle
from planner_app.graphics.palette import themeColors
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    assert not main.groupActionButtons["Group"].isEnabled() and not main.groupActionButtons["Ungroup"].isEnabled()
    assert main.groupModeButton.y() < main.groupActionButtons["Group"].y() < main.groupActionButtons["Ungroup"].y()
    v = main.viewport
    p = QtCore.QPointF
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    left = QtCore.Qt.MouseButton.LeftButton
    originalGrid = v.showGrid
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_G, ctrl)
    assert v.showGrid == originalGrid and not v.undoHistory
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_G)
    assert v.showGrid != originalGrid and not v.undoHistory
    QtTest.QTest.keyClick(main.groupModeButton, QtCore.Qt.Key.Key_G)
    assert v.showGrid == originalGrid and not v.undoHistory
    walls = [Wall(p(-1200, y), p(1200, y), 120) for y in (-1100, -400, 300, 1000)]
    a, b, c, d = walls
    v.walls = walls
    v.snapEnabled = False
    main.connectedOptions["vertices"].setChecked(False)
    main.connectedOptions["objects"].setChecked(False)
    v.SetSelection([(a, None), (b, None)])
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_G)
    assert v.showGrid != originalGrid and not v.objectGroups
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_G)
    assert v.showGrid == originalGrid and not v.objectGroups
    assert main.groupActionButtons["Group"].isEnabled()
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_G, ctrl)
    assert v.showGrid == originalGrid
    assert len(v.objectGroups) == 1 and set(map(id, v.objectGroups[0])) == {id(a), id(b)}
    assert len(v.undoHistory) == 1
    assert main.groupActionButtons["Ungroup"].isEnabled()
    v.SetSelection([(walls[2], None)])
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_G, ctrl)
    assert v.showGrid == originalGrid and len(v.undoHistory) == 1
    v.Undo()
    assert not v.objectGroups
    v.Redo()
    assert set(map(id, v.objectGroups[0])) == {id(a), id(b)}
    v.SetSelection([])
    center = v.WorldToViewport(p(0, -1100)).toPoint()
    QtTest.QTest.mouseClick(v, left, pos = center)
    assert {id(obj) for obj, index in v.SelectionEntries()} == {id(a), id(b)}
    assert all(index is None for obj, index in v.SelectionEntries())
    QtTest.QTest.mouseClick(v, left, ctrl, center)
    assert not v.SelectionEntries()
    QtTest.QTest.mouseClick(v, left, QtCore.Qt.KeyboardModifier.ShiftModifier, center)
    assert {id(obj) for obj, index in v.SelectionEntries()} == {id(a), id(b)}
    originalA, originalB = p(a.firstVertex), p(b.firstVertex)
    Drag(v, center, center + QtCore.QPoint(30, 20))
    assert a.firstVertex != originalA and a.firstVertex - originalA == b.firstVertex - originalB
    v.Undo()
    assert a.firstVertex == originalA and b.firstVertex == originalB
    main.groupModeButton.click()
    assert not v.groupModeEnabled
    v.SetSelection([])
    QtTest.QTest.mouseClick(v, left, pos = center)
    assert v.SelectionEntries() == [(a, None)]
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_G, QtCore.Qt.KeyboardModifier.AltModifier)
    assert not v.objectGroups
    v.Undo()
    assert set(map(id, v.objectGroups[0])) == {id(a), id(b)} and not v.groupModeEnabled
    # Regroup only selected members while Group Mode is off.
    v.SetSelection([(a, None), (b, None), (c, None)])
    assert v.GroupSelection()
    v.SetSelection([(a, None), (d, None)])
    QtTest.QTest.keyClick(main.groupModeButton, QtCore.Qt.Key.Key_G, ctrl)
    assert {frozenset(map(id, group)) for group in v.objectGroups} == {frozenset((id(b), id(c))), frozenset((id(a), id(d)))}
    assert len([obj for group in v.objectGroups for obj in group]) == 4
    v.SetSelection([(b, None)])
    groupsBefore = list(v.objectGroups)
    historyCount = len(v.undoHistory)
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_U, ctrl)
    assert v.objectGroups == groupsBefore and len(v.undoHistory) == historyCount
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_G, QtCore.Qt.KeyboardModifier.AltModifier)
    assert v.objectGroups == [(a, d)]
    v.Undo()
    assert len(v.objectGroups) == 2
    # Selecting one member from each group merges their full memberships.
    main.groupModeButton.click()
    v.SetSelection([(a, None), (b, None)])
    assert len(v.SelectionEntries()) == 4
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_G, ctrl)
    assert len(v.objectGroups) == 1 and set(map(id, v.objectGroups[0])) == set(map(id, walls))
    historyCount = len(v.undoHistory)
    assert not v.GroupSelection() and len(v.undoHistory) == historyCount
    v.SetSelection([(c, None)])
    assert len(v.SelectionEntries()) == 4
    v.DeleteSelected()
    assert not v.walls and not v.objectGroups
    v.Undo()
    assert v.walls == walls and len(v.objectGroups) == 1
    # Group toggles remain available on every tab.
    for index in range(main.sidebarTabs.count()):
        main.sidebarTabs.setCurrentIndex(index)
        app.processEvents()
        assert main.groupModeButton.isVisible()
    assert main.groupModeButton.size() == QtCore.QSize(40, 40)
    # Export deliberately cancels selection and disables editing commands.
    main.sidebarTabs.setCurrentIndex(0)
    app.processEvents()
    # Membership supports structural objects, openings and furnishings together.
    stair = Stair(p(-1800, 0), p(-1800, 1000), 400)
    door = Door(a, .2, .4)
    furnishing = Furnishing(v.furnishingDefinitions["desk"], p(1800, 0))
    v.walls, v.windows, v.furnishings = [a, stair], [door], [furnishing]
    v.objectGroups = []
    v.SetSelection([(a, None), (stair, None), (door, None), (furnishing, None)])
    ordinaryImage = v.grab().toImage()
    main.groupActionButtons["Group"].click()
    assert len(v.objectGroups) == 1
    groupedImage = v.grab().toImage()
    assert groupedImage != ordinaryImage
    assert all(v.SelectionColor(obj) == themeColors["groupSelectionOutline"] for obj in [a, stair, door, furnishing])
    assert v.SelectionColor(d) == themeColors["selectionOutline"]
    assert furnishing.definition["key"] in v.groupedFurnishingRenderers
    main.sidebarTabs.setCurrentIndex(0)
    main.grab().save('screenshots/grouped-selection.png')
    v.Undo()
    assert v.grab().toImage() == ordinaryImage
    v.Redo()
    assert v.grab().toImage() == groupedImage
    v.SetSelection([(door, None)])
    assert {id(obj) for obj, index in v.SelectionEntries()} == {id(a), id(stair), id(door), id(furnishing)}
    main.groupModeButton.click()
    v.SetSelection([(stair, None)])
    main.groupActionButtons["Ungroup"].click()
    assert set(map(id, v.objectGroups[0])) == {id(a), id(door), id(furnishing)}
    main.close()
    print("PASS: G grid toggle, Ctrl+G grouping, Alt+G ungrouping, selection expansion, group movement, mode, reassignment/merging, deletion and undo/redo.")


if __name__ == "__main__":
    Main()
