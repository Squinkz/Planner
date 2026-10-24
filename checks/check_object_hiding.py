"""Hide/unhide shortcuts, toolbar actions, group membership, HUD and history."""
import os
import sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Door, Stair
from furnishings import Furnishing
from planner_app.models import Label, Arrow, Counter, Railing, MeasurementGuide
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    p = QtCore.QPointF
    wall = Wall(p(-1500, -900), p(1500, -900), 240)
    stair = Stair(p(-1300, 100), p(-1300, 1100), 500)
    furnishing = Furnishing(v.furnishingDefinitions["desk"], p(700, 700))
    door = Door(wall, .2, .4)
    v.walls, v.windows, v.furnishings = [wall, stair], [door], [furnishing]
    main.RefreshVisibilityCounts()
    geometry = main.centralWidget().geometry()
    v.SetSelection([(wall, None)])
    assert main.groupActionButtons["Hide"].isEnabled()
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_H)
    assert v.hiddenObjectIds == {id(wall), id(door)}
    assert not v.SelectionEntries() and not v.IsObjectVisible(wall) and not v.IsObjectVisible(door)
    assert v.HitTest(v.WorldToViewport(p(0, -900))) == (None, None)
    assert main.groupActionButtons["Unhide"].isEnabled()
    assert main.visibilityItems["World"].text(0) == "World (4 objects)"
    hiddenImage = v.grab().toImage()
    v.Undo()
    assert not v.hiddenObjects and v.IsObjectVisible(wall)
    v.Redo()
    assert v.grab().toImage() == hiddenImage
    # Hidden furnishings have no hover handles and cannot be selected.
    v.SetSelection([(furnishing, None)])
    main.groupActionButtons["Hide"].click()
    v.hoverPosition = v.WorldToViewport((furnishing.firstVertex + furnishing.secondVertex) / 2)
    assert not v.VisibleFurnishingHandles()
    assert v.HitTest(v.hoverPosition) == (None, None)
    main.grab().save('screenshots/hidden-objects.png')
    main.groupActionButtons["Unhide"].click()
    assert not v.hiddenObjects and not main.groupActionButtons["Unhide"].isEnabled()
    # Group Mode expands the H selection to the whole group.
    v.SetSelection([(stair, None), (furnishing, None)])
    assert v.GroupSelection()
    v.SetSelection([(stair, None)])
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_H)
    assert v.hiddenObjectIds == {id(stair), id(furnishing)} and len(v.objectGroups) == 1
    # U is unassigned and text inputs retain plain H/U/G typing.
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_U)
    assert v.hiddenObjectIds == {id(stair), id(furnishing)}
    editor = QtWidgets.QLineEdit(main)
    editor.show()
    editor.setFocus()
    originalGrid = v.showGrid
    QtTest.QTest.keyClicks(editor, "hug")
    assert editor.text() == "hug" and len(v.hiddenObjects) == 2
    assert v.showGrid == originalGrid
    editor.hide()
    v.setFocus()
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_H, QtCore.Qt.KeyboardModifier.AltModifier)
    assert not v.hiddenObjects
    v.SetSelection([(furnishing, None)])
    assert len(v.SelectionEntries()) == 2
    # With Group Mode off, only the selected member is hidden.
    main.groupModeButton.click()
    v.SetSelection([(furnishing, None)])
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_H)
    assert v.hiddenObjectIds == {id(furnishing)} and v.IsObjectVisible(stair)
    # Unhide preserves class visibility choices.
    main.visibilityItems["Furnishings"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_H, QtCore.Qt.KeyboardModifier.AltModifier)
    assert not v.hiddenObjects and not v.IsObjectVisible(furnishing)
    assert main.centralWidget().geometry() == geometry
    # Ctrl+H isolates the selection across all object lists and retains it.
    main.visibilityItems["Furnishings"].setCheckState(0, QtCore.Qt.CheckState.Checked)
    extras = [Arrow(p(2000, 0), p(3000, 0)), Counter(p(2000, 1000), p(3000, 1000)),
              Railing(p(2000, 2000), p(3000, 2000)), MeasurementGuide(p(2000, 3000), p(3000, 3000))]
    label = Label(p(1800, 1800))
    v.walls.extend(extras)
    v.labels = [label]
    v.SetSelection([(stair, 1), (furnishing, None)])
    selected = list(v.SelectionEntries())
    objects = v.walls + v.windows + v.furnishings + v.labels
    keptIds = {id(stair), id(furnishing)}
    button = main.groupActionButtons["HideUnselected"]
    assert button.isEnabled() and button.toolTip() == "Hide unselected (Ctrl + H)"
    assert main.groupActionButtons["Hide"].toolTip() == "Hide selected (H)"
    assert main.viewportToolbar.layout().indexOf(button) == main.viewportToolbar.layout().indexOf(main.groupActionButtons["Hide"]) + 1
    QtTest.QTest.keyClick(main.groupModeButton, QtCore.Qt.Key.Key_H, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert v.hiddenObjectIds == {id(obj) for obj in objects} - keptIds
    assert v.SelectionEntries() == selected
    assert all(v.IsObjectVisible(obj) == (id(obj) in keptIds) for obj in objects)
    v.Undo()
    assert not v.hiddenObjects and v.SelectionEntries() == selected
    v.Redo()
    assert v.hiddenObjectIds == {id(obj) for obj in objects} - keptIds
    v.UnhideObjects()
    # A selected opening remains visible even when its unselected host is hidden.
    v.SetSelection([(door, None)])
    button.click()
    assert v.IsObjectVisible(door) and not v.IsObjectVisible(wall)
    assert v.hiddenObjectIds == {id(obj) for obj in objects if obj is not door}
    v.UnhideObjects()
    v.SetSelection([])
    assert not button.isEnabled() and not v.HideUnselected() and not v.hiddenObjects
    # Ctrl+H also respects focus in text fields.
    v.SetSelection([(stair, None)])
    editor.show()
    editor.setFocus()
    QtTest.QTest.keyClick(editor, QtCore.Qt.Key.Key_H, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert not v.hiddenObjects
    QtTest.QTest.keyClick(editor, QtCore.Qt.Key.Key_H, QtCore.Qt.KeyboardModifier.AltModifier)
    assert not v.hiddenObjects
    editor.hide()
    main.close()
    print("PASS: H, Ctrl+H, Alt+H, toolbar actions, attached openings, groups/individuals, HUD, hidden hit/handles, text fields, visibility and undo/redo.")


if __name__ == "__main__":
    Main()
