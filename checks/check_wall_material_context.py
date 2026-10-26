"""Wall material context dropdown matches property choices and bulk undo."""
import os, sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Stair
from theme import BuildStyle
from planner_app.graphics.theme import wallMaterials


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    p = QtCore.QPointF
    a = Wall(p(-1000, -500), p(-1000, 500), 120)
    b = Wall(p(1000, -500), p(1000, 500), 240)
    v.walls = [a, b]
    v.SetSelection([(a, None), (b, None)])
    position = v.WorldToViewport(p())
    v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
    parent = v.objectContextMenu
    buttons = [action.defaultWidget() for action in parent.actions() if not action.isSeparator()]
    assert [button.accessibleName() for button in buttons] == ["Subdivide Wall", "Material", "Flip Horizontal", "Flip Vertical", "Hide dimensions", "Group selected", "Transform", "Cut", "Copy", "Delete"]
    QtGui.QCursor.setPos(buttons[1].mapToGlobal(buttons[1].rect().center()))
    QtTest.QTest.mouseMove(buttons[1], buttons[1].rect().center())
    app.processEvents()
    submenu = parent.materialMenu
    assert submenu.isVisible() and parent.isVisible()
    choices = [action.defaultWidget() for action in submenu.actions()]
    assert [choice.accessibleName() for choice in choices] == list(wallMaterials)
    assert [main.materialField.itemText(index) for index in range(main.materialField.count())] == list(wallMaterials)
    assert all(not choice.iconLabel.pixmap().isNull() for choice in choices)
    assert [choice.accessibleName() for choice in choices if choice.isChecked()] == ["Generic"]
    submenu.grab().save('screenshots/wall-material-context.png')
    history = len(v.undoHistory)
    QtTest.QTest.mouseClick(choices[wallMaterials.index("Ceramic")], QtCore.Qt.MouseButton.LeftButton)
    assert a.material == b.material == "Ceramic"
    assert not parent.isVisible() and not submenu.isVisible()
    assert main.materialField.currentText() == "Ceramic" and len(v.undoHistory) == history + 1
    v.Undo()
    assert a.material == b.material == "Generic"
    v.Redo()
    assert a.material == b.material == "Ceramic"
    b.material = "Wood"
    v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
    controller = parent.materialController
    QtGui.QCursor.setPos(controller.parentButton.mapToGlobal(controller.parentButton.rect().center()))
    controller.ShowChildMenu()
    assert not any(action.defaultWidget().isChecked() for action in parent.materialMenu.actions())
    parent.hide()
    v.SetSelection([(a, None)])
    position = v.WorldToViewport(p(-1000, 0))
    v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
    controller = parent.materialController
    QtGui.QCursor.setPos(controller.parentButton.mapToGlobal(controller.parentButton.rect().center()))
    controller.ShowChildMenu()
    choice = parent.materialMenu.actions()[wallMaterials.index("Metal")].defaultWidget()
    choice.click()
    assert a.material == "Metal" and b.material == "Wood"
    v.walls.append(Stair(p(-500, 0), p(500, 0), 200))
    v.SetSelection([(a, None), (v.walls[-1], None)])
    v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
    assert not hasattr(parent, "materialMenu")
    main.close()
    print("PASS: material submenu, matching icons/choices, common/mixed values, single/bulk edits and undo/redo.")


if __name__ == "__main__":
    Main()
