"""Mouse-up context commands respect class, selection and right-drag gestures."""
import os
import sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Stair, Door, SlidingDoor, PocketDoor, Window, SilledWindow, OpenDoorway
from furnishings import Furnishing
from planner_app.graphics.theme import HeaderIcon, UiIcon
from check_history import Drag


def OpenMenu(viewport, position):
    viewport.objectContextMenu.hide()
    screen = viewport.WorldToViewport(position).toPoint()
    before = list(viewport.SelectionEntries())
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.RightButton, pos = screen)
    assert not viewport.objectContextMenu.isVisible() and viewport.pendingWall is None
    assert viewport.SelectionEntries() == before
    QtTest.QTest.mouseRelease(viewport, QtCore.Qt.MouseButton.RightButton, pos = screen)
    assert viewport.objectContextMenu.isVisible() and viewport.pendingWall is None
    return [None if action.isSeparator() else action.defaultWidget().accessibleName()
            for action in viewport.objectContextMenu.actions()]


def Click(viewport, label):
    button = next(action.defaultWidget() for action in viewport.objectContextMenu.actions()
                  if not action.isSeparator() and action.defaultWidget().accessibleName() == label)
    assert not button.iconLabel.pixmap().isNull()
    QtTest.QTest.mouseClick(button, QtCore.Qt.MouseButton.LeftButton)
    assert not viewport.objectContextMenu.isVisible()


def Main():
    app = QtWidgets.QApplication([])
    try:
        QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
        main = MainWindow()
        main.show()
        app.processEvents()
        viewport = main.viewport
        for field, iconName in (("swing", "flip_v"), ("hinge", "flip_h"), ("measurement", "measure")):
            assert main.doorFields[field].icon().pixmap(18, 18).toImage() == UiIcon(iconName).pixmap(18, 18).toImage()
        for field, iconName in (("flipHorizontal", "flip_h"), ("flipVertical", "flip_v")):
            assert main.furnishingFlipFields[field].icon().pixmap(18, 18).toImage() == UiIcon(iconName).pixmap(18, 18).toImage()
        viewport.snapEnabled = False
        point = QtCore.QPointF
        generic = ["Hide measurement", None, "Transform", None, "Cut", "Copy", None, "Delete"]
        groupGeneric = ["Hide measurement", None, "Group selected", None] + generic[2:]
        parent = Wall(point(-1800, 0), point(1800, 0))
        viewport.walls = [parent]
        assert OpenMenu(viewport, point(0, 900)) == ["Paste"]
        assert not viewport.objectContextMenu.actions()[0].defaultWidget().isEnabled()
        viewport.objectContextMenu.hide()
        assert OpenMenu(viewport, point()) == ["Subdivide Wall", "Material"] + generic
        moveButton = next(action.defaultWidget() for action in viewport.objectContextMenu.actions()
                          if not action.isSeparator() and action.defaultWidget().accessibleName() == "Transform")
        assert moveButton.shortcutLabel.text() == "T"
        before = viewport.CaptureState()
        Click(viewport, "Transform")
        assert main.moveSpecialWindow.isVisible() and main.moveSpecialWindow.windowTitle() == "Transform"
        main.moveSpecialWindow.reject()
        assert viewport.CaptureState() == before
        OpenMenu(viewport, point())
        for label in ("Copy",):
            before = viewport.CaptureState()
            Click(viewport, label)
            assert viewport.CaptureState() == before
            OpenMenu(viewport, point())
        Click(viewport, "Cut")
        assert not viewport.walls
        viewport.Undo()
        assert viewport.walls == [parent]
        cases = [(Door, [("Flip Swing Direction", "swingsOutwards"), ("Flip Hinge Side", "hingeAtSecond")]),
                 (SlidingDoor, [("Flip Panel Side", "panelsFlipped"), ("Flip Slide Direction", "hingeAtSecond")]),
                 (PocketDoor, [("Flip Pocket Side", "hingeAtSecond")]),
                 (Window, [("Flip Facing", "swingsOutwards")]),
                 (SilledWindow, [("Flip Facing", "swingsOutwards")]),
                 (OpenDoorway, [])]
        for objectType, options in cases:
            if objectType in (Door, SlidingDoor, Window, SilledWindow):
                options = options + [("Flip Measurement", "measurementFlipped")]
            first = objectType(parent, .1, .35)
            second = objectType(parent, .65, .9)
            viewport.windows = [first, second]
            viewport.SetSelection([(first, None), (second, None)])
            center = (first.firstVertex + first.secondVertex) / 2
            expected = [label for label, attr in options] + groupGeneric
            assert OpenMenu(viewport, center) == expected
            for action in viewport.objectContextMenu.actions():
                if action.isSeparator():
                    continue
                button = action.defaultWidget()
                if button is None:
                    continue
                attr = next((attr for label, attr in options if label == button.accessibleName()), None)
                if attr in ("hingeAtSecond", "panelsFlipped", "swingsOutwards", "measurementFlipped"):
                    iconName = "measure" if attr == "measurementFlipped" else "flip_h" if attr == "hingeAtSecond" else "flip_v"
                    assert button.iconLabel.pixmap().toImage() == UiIcon(iconName).pixmap(18, 18).toImage()
            assert len(viewport.SelectionEntries()) == 2
            for label, attr in options:
                OpenMenu(viewport, center)
                historyCount = len(viewport.undoHistory)
                Click(viewport, label)
                assert getattr(first, attr) and getattr(second, attr)
                assert len(viewport.undoHistory) == historyCount + 1
                viewport.Undo()
                assert not getattr(first, attr) and not getattr(second, attr)
                viewport.Redo()
                assert getattr(first, attr) and getattr(second, attr)
        # Different opening classes have no class-specific section.
        viewport.windows = [Door(parent, .1, .35), Window(parent, .65, .9)]
        viewport.SetSelection([(obj, None) for obj in viewport.windows])
        first = viewport.windows[0]
        assert OpenMenu(viewport, (first.firstVertex + first.secondVertex) / 2) == groupGeneric
        Click(viewport, "Delete")
        assert not viewport.windows and viewport.walls == [parent]
        viewport.Undo()
        assert len(viewport.windows) == 2
        # Right-clicking an unselected object switches the context to that object.
        viewport.SetSelection([(viewport.windows[0], None)])
        second = viewport.windows[1]
        assert OpenMenu(viewport, (second.firstVertex + second.secondVertex) / 2) == ["Flip Facing", "Flip Measurement"] + generic
        assert viewport.SelectionEntries() == [(second, None)]
        viewport.objectContextMenu.hide()
        viewport.windows = []
        stair = Stair(point(-400, 700), point(400, 700), 300)
        viewport.walls.append(stair)
        viewport.measurementVisibility["stairs"] = True
        assert OpenMenu(viewport, point(0, 700)) == ["Flip Direction"] + generic
        for expectedIcon in ("Redo", "Undo", "Redo"):
            OpenMenu(viewport, point(0, 700))
            button = viewport.objectContextMenu.actions()[0].defaultWidget()
            assert button.iconLabel.pixmap().toImage() == HeaderIcon(expectedIcon).pixmap(18, 18).toImage()
            assert main.stairDirectionButton.icon().pixmap(18, 18).toImage() == HeaderIcon(expectedIcon).pixmap(18, 18).toImage()
            Click(viewport, "Flip Direction")
        assert stair.directionReversed
        viewport.Undo()
        assert not stair.directionReversed
        for expectedIcon in ("Redo", "Undo"):
            assert main.stairDirectionButton.icon().pixmap(18, 18).toImage() == HeaderIcon(expectedIcon).pixmap(18, 18).toImage()
            main.stairDirectionButton.click()
        assert not stair.directionReversed
        viewport.Undo()
        assert stair.directionReversed
        assert main.stairDirectionButton.icon().pixmap(18, 18).toImage() == HeaderIcon("Undo").pixmap(18, 18).toImage()
        viewport.Redo()
        assert not stair.directionReversed
        assert main.stairDirectionButton.icon().pixmap(18, 18).toImage() == HeaderIcon("Redo").pixmap(18, 18).toImage()
        OpenMenu(viewport, point(0, 700))
        Click(viewport, "Flip Direction")
        assert stair.directionReversed
        viewport.Undo()
        assert not stair.directionReversed
        # Furnishing group ordering preserves relative order and has one undo entry.
        viewport.walls = []
        definitions = viewport.furnishingDefinitions
        items = [Furnishing(definitions["desk"], point(x, 0)) for x in (-900, 0, 900)]
        viewport.furnishings = items.copy()
        viewport.SetSelection([(items[0], None), (items[1], None)])
        assert OpenMenu(viewport, point(-900, 0)) == ["Create Furnishing from Selection…", "Bring to Front", "Move to Back", "Flip Horizontal", "Flip Vertical", None] + groupGeneric[2:]
        for action in viewport.objectContextMenu.actions():
            if action.isSeparator():
                continue
            button = action.defaultWidget()
            iconName = {"Bring to Front": "flip_to_front", "Move to Back": "flip_to_back",
                        "Flip Horizontal": "flip_h", "Flip Vertical": "flip_v"}.get(button.accessibleName())
            if iconName:
                assert button.iconLabel.pixmap().toImage() == UiIcon(iconName).pixmap(18, 18).toImage()
        historyCount = len(viewport.undoHistory)
        Click(viewport, "Bring to Front")
        assert viewport.furnishings == [items[2], items[0], items[1]]
        assert len(viewport.undoHistory) == historyCount + 1
        viewport.Undo()
        assert viewport.furnishings == items
        OpenMenu(viewport, point(-900, 0))
        historyCount = len(viewport.undoHistory)
        Click(viewport, "Group selected")
        assert len(viewport.objectGroups) == 1 and len(viewport.objectGroups[0]) == 2
        assert len(viewport.undoHistory) == historyCount + 1
        labels = OpenMenu(viewport, point(-900, 0))
        assert "Ungroup selected" in labels and "Group selected" not in labels
        Click(viewport, "Ungroup selected")
        assert not viewport.objectGroups
        viewport.Undo()
        assert len(viewport.objectGroups) == 1
        viewport.Redo()
        assert not viewport.objectGroups
        # A right drag creates a wall and never opens a menu.
        viewport.objectContextMenu.hide()
        viewport.furnishings = []
        start = viewport.WorldToViewport(point(-800, -700)).toPoint()
        end = viewport.WorldToViewport(point(800, -700)).toPoint()
        Drag(viewport, start, end, button = QtCore.Qt.MouseButton.RightButton)
        assert len(viewport.walls) == 1 and not viewport.objectContextMenu.isVisible()
        main.close()
        print("PASS: mouse-up menus, clipboard commands, class actions, atomic bulk flips/layers, mixed selections, delete/undo and right-drag walls.")
    finally:
        app.clipboard().clear()
        app.processEvents()



if __name__ == "__main__":
    Main()
