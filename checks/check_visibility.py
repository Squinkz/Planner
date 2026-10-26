"""Cascading visibility, partial parent states and persistent grid/rulers."""
import os
import sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from planner import MainWindow, Wall, Stair, Door, Window
from furnishings import Furnishing
from theme import BuildStyle
from planner_app.project_codec import DecodeProject
from planner_app.graphics.palette import themeColors


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    p = QtCore.QPointF
    wall = Wall(p(-1600, -800), p(1600, -800), 240)
    stair = Stair(p(-1200, 100), p(-1200, 1100), 500)
    furnishing = Furnishing(v.furnishingDefinitions["desk"], p(700, 800))
    door = Door(wall, .1, .3)
    window = Window(wall, .6, .8)
    before = v.CaptureState()
    v.walls = [wall, stair]
    v.windows = [door, window]
    v.furnishings = [furnishing]
    v.SetSelection([(furnishing, None)])
    v.RecordEdit(before)
    main.sidebarTabs.setCurrentIndex(2)
    app.processEvents()
    assert main.sidebarTabs.tabText(2) == "Visibility"
    items = main.visibilityItems
    assert main.visibilityTree.topLevelItemCount() == 2
    assert main.referenceImageItem.parent() is None and main.referenceImageItem is not items["World"]
    assert main.referenceImageItem.checkState(0) == QtCore.Qt.CheckState.Unchecked
    assert [items["World"].child(i).text(0).split(" (")[0] for i in range(items["World"].childCount())] == [
        "Walls", "Elevators", "Stairs", "Counters", "Railings", "Furnishings", "Labels", "Arrows", "Dimension guides", "Boundary lines", "Dashed lines", "Solid lines", "North arrows"]
    assert [items["Walls"].child(i).text(0).split(" (")[0] for i in range(items["Walls"].childCount())] == ["Doors", "Windows", "Fireplaces"]
    assert items["World"].text(0) == "World (5 objects)"
    assert all(items[name].text(0) == f"{name} (1 object)" for name in ["Walls", "Doors", "Windows", "Stairs", "Furnishings"])
    v.DeleteSelected()
    assert items["World"].text(0) == "World (4 objects)" and items["Furnishings"].text(0) == "Furnishings (0 objects)"
    v.Undo()
    assert items["World"].text(0) == "World (5 objects)" and items["Furnishings"].text(0) == "Furnishings (1 object)"
    assert all(v.IsObjectVisible(obj) for obj in [wall, stair, furnishing, door, window])
    fullImage = v.grab().toImage()
    for name, obj in [("Doors", door), ("Windows", window), ("Stairs", stair), ("Furnishings", furnishing)]:
        items[name].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        assert not v.IsObjectVisible(obj)
        assert v.grab().toImage() != fullImage
        items[name].setCheckState(0, QtCore.Qt.CheckState.Checked)
        assert v.grab().toImage() == fullImage
    items["Walls"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
    assert all(not v.IsObjectVisible(obj) for obj in [wall, door, window])
    assert v.IsObjectVisible(stair) and v.IsObjectVisible(furnishing)
    assert not v.visibility["Doors"] and not v.visibility["Windows"]
    assert items["Walls"].checkState(0) == QtCore.Qt.CheckState.Unchecked
    assert items["World"].checkState(0) == QtCore.Qt.CheckState.PartiallyChecked
    items["Doors"].setCheckState(0, QtCore.Qt.CheckState.Checked)
    assert v.IsObjectVisible(door) and not v.IsObjectVisible(wall) and not v.IsObjectVisible(window)
    assert items["Walls"].checkState(0) == QtCore.Qt.CheckState.PartiallyChecked
    assert items["Doors"].foreground(0).color().name() == themeColors["text"]
    items["Walls"].setCheckState(0, QtCore.Qt.CheckState.Checked)
    assert v.grab().toImage() == fullImage
    main.grab().save('screenshots/visibility-tab.png')
    items["Windows"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
    assert items["Windows"].foreground(0).color().name() == themeColors["treeDisabledText"]
    items["Walls"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
    assert all(items[name].foreground(0).color().name() == themeColors["treeDisabledText"] for name in ["Walls", "Doors", "Windows"])
    assert items["Stairs"].foreground(0).color().name() == themeColors["text"]
    items["Walls"].setCheckState(0, QtCore.Qt.CheckState.Checked)
    assert items["Doors"].foreground(0).color().name() == themeColors["text"]
    assert items["Windows"].foreground(0).color().name() == themeColors["text"]
    assert v.visibility["Windows"] and v.visibility["Doors"]
    assert v.grab().toImage() == fullImage
    items["World"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
    assert all(node.foreground(0).color().name() == themeColors["treeDisabledText"] for node in items.values())
    assert all(node.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled for node in items.values())
    image = v.grab().toImage()
    assert not any(v.visibility.values())
    assert all(node.checkState(0) == QtCore.Qt.CheckState.Unchecked for node in items.values())
    assert all(not v.IsObjectVisible(obj) for obj in [wall, stair, furnishing, door, window])
    # Compare with an empty scene: the same grid, rulers and frame must remain.
    v.walls, v.windows, v.furnishings = [], [], []
    v.SetSelection([])
    items["World"].setCheckState(0, QtCore.Qt.CheckState.Checked)
    assert v.grab().toImage() == image
    v.walls, v.windows, v.furnishings = [wall, stair], [door, window], [furnishing]
    v.SetSelection([(furnishing, None)])
    items["World"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
    items["World"].setCheckState(0, QtCore.Qt.CheckState.Checked)
    assert all(v.visibility.values())
    assert all(node.checkState(0) == QtCore.Qt.CheckState.Checked for node in items.values())
    assert v.grab().toImage() == fullImage
    assert v.walls == [wall, stair] and v.windows == [door, window] and v.furnishings == [furnishing]
    items["World"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
    items["Windows"].setCheckState(0, QtCore.Qt.CheckState.Checked)
    assert v.IsObjectVisible(window)
    assert all(not v.IsObjectVisible(obj) for obj in (wall, door, stair, furnishing))
    assert items["Walls"].checkState(0) == QtCore.Qt.CheckState.PartiallyChecked
    assert items["World"].checkState(0) == QtCore.Qt.CheckState.PartiallyChecked
    main.grab().save('screenshots/visibility-partial.png')
    saved = main.BuildProjectData()
    main.ApplyProject(DecodeProject(saved, v.furnishingDefinitions), None)
    assert v.visibility["Windows"] and not v.visibility["Walls"] and not v.visibility["Doors"]
    assert items["Walls"].checkState(0) == QtCore.Qt.CheckState.PartiallyChecked
    assert items["World"].checkState(0) == QtCore.Qt.CheckState.PartiallyChecked
    assert v.IsObjectVisible(v.windows[1]) and not v.IsObjectVisible(v.walls[0])
    items["Windows"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
    assert all(node.checkState(0) == QtCore.Qt.CheckState.Unchecked for node in items.values())
    items["Doors"].setCheckState(0, QtCore.Qt.CheckState.Checked)
    main.visibilityTree.setCurrentItem(items["Walls"])
    QtTest.QTest.keyClick(main.visibilityTree, QtCore.Qt.Key.Key_Space)
    assert all(not v.visibility[name] for name in ("Walls", "Doors", "Windows"))
    assert items["Walls"].checkState(0) == QtCore.Qt.CheckState.Unchecked
    QtTest.QTest.keyClick(main.visibilityTree, QtCore.Qt.Key.Key_Space)
    assert all(v.visibility[name] for name in ("Walls", "Doors", "Windows"))
    assert not v.visibility["Stairs"]
    assert items["Walls"].checkState(0) == QtCore.Qt.CheckState.Checked
    assert items["World"].checkState(0) == QtCore.Qt.CheckState.PartiallyChecked
    worldIndex = main.visibilityTree.indexFromItem(items["World"])
    option = QtWidgets.QStyleOptionViewItem()
    option.widget = main.visibilityTree
    option.rect = main.visibilityTree.visualRect(worldIndex)
    main.visibilityTree.itemDelegate().initStyleOption(option, worldIndex)
    checkRect = main.visibilityTree.style().subElementRect(
        QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, main.visibilityTree)
    QtTest.QTest.mouseClick(main.visibilityTree.viewport(), QtCore.Qt.MouseButton.LeftButton, pos = checkRect.center())
    assert all(node.checkState(0) == QtCore.Qt.CheckState.Unchecked for node in items.values())
    items["World"].setCheckState(0, QtCore.Qt.CheckState.Checked)
    assert all(node.checkState(0) == QtCore.Qt.CheckState.Checked for node in items.values())
    main.close()
    print("PASS: cascading hierarchy, partial states, independent rendering, hidden handles and persistent grid/rulers.")


if __name__ == "__main__":
    Main()

