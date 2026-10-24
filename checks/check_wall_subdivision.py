"""Wall subdivision, nearest free cut, attached openings and undo."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow, Wall, Window, Door


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    wall = Wall(point(-2000, -1000), point(2000, 1000), 180, .3, .7, "Lumber")
    v.walls = [wall]
    v.SetSelection([(wall, None)])
    position = v.WorldToViewport(point())
    v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
    buttons = [action.defaultWidget() for action in v.objectContextMenu.actions() if not action.isSeparator()]
    assert [button.accessibleName() for button in buttons[:2]] == ["Subdivide Wall", "Material"]
    QtTest.QTest.mouseClick(buttons[0], QtCore.Qt.MouseButton.LeftButton)
    assert not v.objectContextMenu.isVisible()
    first, second = v.walls
    assert first is not wall and second is not wall
    assert first.firstVertex == wall.firstVertex and second.secondVertex == wall.secondVertex
    assert first.secondVertex == second.firstVertex == point()
    assert first.width == second.width == 180 and first.material == second.material == "Lumber"
    assert first.firstMiter == .3 and second.secondMiter == .7
    assert first.secondMiter == second.firstMiter == 0
    assert first.objectId != second.objectId and None not in (first.objectId, second.objectId)
    assert len(v.SelectionEntries()) == 2
    v.Undo()
    assert v.walls == [wall]
    v.Redo()
    assert v.walls == [first, second]
    v.Undo()
    # Occupied midpoint: nearest opening jamb, with no opening relocation.
    opening = Window(wall, .4, .7)
    other = Door(wall, .8, .95)
    v.windows = [opening, other]
    positions = [(point(obj.firstVertex), point(obj.secondVertex)) for obj in v.windows]
    v.objectGroups = [(wall, other)]
    assert v.SubdivideWalls([wall])
    first, second = v.walls
    assert QtCore.QLineF(first.secondVertex, wall.firstVertex + (wall.secondVertex - wall.firstVertex) * .4).length() < .001
    assert opening.parentWall is second and other.parentWall is second
    assert all(QtCore.QLineF(obj.firstVertex, positions[index][0]).length() < .001 and
               QtCore.QLineF(obj.secondVertex, positions[index][1]).length() < .001 for index, obj in enumerate(v.windows))
    assert len(v.objectGroups[0]) == 3
    v.Undo()
    assert v.walls == [wall] and all(obj.parentWall is wall for obj in v.windows)
    assert len(v.objectGroups[0]) == 2
    # An intersection with another wall also occupies the split point.
    wall = Wall(point(0, 0), point(1000, 0), 120)
    crossing = Wall(point(500, -1000), point(500, 1000), 200)
    v.walls, v.windows, v.objectGroups = [wall, crossing], [], []
    assert v.SubdivideWalls([wall])
    assert v.walls[0].secondVertex == point(400, 0)
    v.Undo()
    # Full coverage cancels the whole operation without touching scene/history.
    v.windows = [Window(wall, 0, 1)]
    before = v.CaptureState()
    history = len(v.undoHistory)
    assert not v.SubdivideWalls([wall, crossing])
    assert before == v.CaptureState() and len(v.undoHistory) == history
    assert "no clear wall segment" in v.clipboardError
    main.close()
    print("PASS: midpoint subdivision, preserved properties/IDs, nearest free cut, openings, groups, undo and invalid full coverage.")


if __name__ == "__main__":
    Main()
