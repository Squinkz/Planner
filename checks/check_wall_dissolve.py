"""Dissolve appears only at a two-wall joint and inherits the lowest ID."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow, Wall, Door, Window


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF

    def OpenMenu(vertex):
        position = v.WorldToViewport(vertex)
        v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
        buttons = [action.defaultWidget() for action in v.objectContextMenu.actions() if not action.isSeparator()]
        return buttons

    older = Wall(point(-2000, 0), point(), 120, .3, .8, "Lumber")
    newer = Wall(point(2000, 0), point(), 240, .7, .4, "Brick")
    older.objectId, newer.objectId = 20, 30
    # Reverse list order to ensure properties are chosen by ID, not draw order.
    v.walls = [newer, older]
    assert OpenMenu(point())[0].accessibleName() == "Dissolve Control Point"
    v.objectContextMenu.hide()
    assert "Dissolve Control Point" not in [button.accessibleName() for button in OpenMenu(point(-2000, 0))]
    v.objectContextMenu.hide()
    third = Wall(point(), point(0, 2000))
    v.walls.append(third)
    assert "Dissolve Control Point" not in [button.accessibleName() for button in OpenMenu(point())]
    v.objectContextMenu.hide()
    v.walls.remove(third)
    v.windows = [Window(older, .15, .35), Door(newer, .2, .45, True, True)]
    savedPositions = [(point(obj.firstVertex), point(obj.secondVertex)) for obj in v.windows]
    # A member from the lower-ID wall's group remains grouped with the new wall.
    v.objectGroups = [(older, v.windows[0])]
    v.groupModeEnabled = False
    buttons = OpenMenu(point())
    assert [button.accessibleName() for button in buttons[:3]] == ["Dissolve Control Point", "Subdivide Wall", "Material"]
    history = len(v.undoHistory)
    QtTest.QTest.mouseClick(buttons[0], QtCore.Qt.MouseButton.LeftButton)
    assert not v.objectContextMenu.isVisible() and len(v.walls) == 1
    merged = v.walls[0]
    assert merged is not older and merged is not newer
    assert merged.firstVertex == point(-2000, 0) and merged.secondVertex == point(2000, 0)
    assert (merged.width, merged.material, merged.firstMiter, merged.secondMiter) == (120, "Lumber", .3, .7)
    assert merged.objectId is not None and merged.objectId not in (20, 30)
    assert all(obj.parentWall is merged for obj in v.windows)
    assert v.objectGroups == [(v.windows[0], merged)]
    for index, opening in enumerate(v.windows):
        expected = savedPositions[index] if index == 0 else tuple(reversed(savedPositions[index]))
        assert QtCore.QLineF(opening.firstVertex, expected[0]).length() < .001
        assert QtCore.QLineF(opening.secondVertex, expected[1]).length() < .001
    assert not v.windows[1].hingeAtSecond and not v.windows[1].swingsOutwards
    assert len(v.undoHistory) == history + 1
    v.Undo()
    assert v.walls == [newer, older] and v.windows[0].parentWall is older and v.windows[1].parentWall is newer
    assert v.windows[1].hingeAtSecond and v.windows[1].swingsOutwards
    v.Redo()
    assert v.walls == [merged]
    # A bend becomes the straight chord connecting the two outer endpoints.
    a = Wall(point(), point(1000, 0), 180)
    b = Wall(point(), point(0, 1000), 240)
    a.objectId, b.objectId = 40, 50
    v.walls, v.windows, v.objectGroups = [b, a], [], []
    assert v.DissolveWalls(point())
    assert v.walls[0].firstVertex == point(0, 1000) and v.walls[0].secondVertex == point(1000, 0)
    assert v.walls[0].width == 180
    # Coincident outer endpoints cannot create a zero-length wall.
    v.walls = [Wall(point(), point(1000, 0)), Wall(point(), point(1000, 0))]
    before = v.CaptureState()
    assert not v.DissolveWalls(point()) and v.CaptureState() == before
    main.close()
    print("PASS: two-wall joint menu, lower-ID properties, outer endpoints, openings/orientation, groups and undo.")


if __name__ == "__main__":
    Main()
