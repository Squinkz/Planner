"""Obstructed openings cannot poison unrelated edits or destroy recovery data."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall, Window
from planner_app.project_codec import DecodeProject
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.resize(1300, 900)
    main.show()
    app.processEvents()
    v = main.viewport
    v.snapEnabled = False
    v.connectedVerticesEnabled = False
    v.connectedObjectsEnabled = False
    point = QtCore.QPointF
    parent = Wall(point(-1500, 0), point(1500, 0))
    opening = Window(parent, .4, .6)
    free = Wall(point(-1500, -1200), point(-600, -1200))
    v.walls, v.windows = [parent, free], [opening]
    v.EnsureObjectIds()
    assert v.OpeningsValid()
    crossing = Wall(point(0, -600), point(0, 600))
    assert not v.WallFits(crossing), "A new wall must not obstruct an existing opening."
    v.wallShape = "square"
    start, end = v.WorldToViewport(point(0, -600)), v.WorldToViewport(point(800, 600))
    Drag(v, start.toPoint(), end.toPoint(), button = QtCore.Qt.MouseButton.RightButton)
    assert len(v.walls) == 2 and v.OpeningsValid(), "An obstructing rectangle must be rejected as one action."
    before = v.CaptureState()
    v.walls.append(crossing)
    v.RecordEdit(before)
    assert not v.OpeningsValid()
    original = point(free.firstVertex)
    start = v.WorldToViewport((free.firstVertex + free.secondVertex) / 2)
    Drag(v, start.toPoint(), (start + point(0, -40)).toPoint())
    assert QtCore.QLineF(free.firstVertex, original).length() > 100
    assert v.dragStart is None and v.interactionBefore is None
    data = main.BuildProjectData()
    try:
        DecodeProject(data, v.furnishingDefinitions)
        raise AssertionError("Ordinary imports must still reject obstructed current placements.")
    except ValueError:
        pass
    assert main.WriteSession(wait = True)
    main.close()
    restored = MainWindow()
    restored.show()
    app.processEvents()
    v = restored.viewport
    assert restored.sessionRestored and len(v.walls) == 3 and len(v.windows) == 1
    assert v.undoHistory and not v.OpeningsValid()
    crossing = v.walls[2]
    start = v.WorldToViewport(crossing.firstVertex * .2 + crossing.secondVertex * .8)
    Drag(v, start.toPoint(), (start + point(200, 0)).toPoint())
    assert v.OpeningsValid(), "The obstructing object must be movable so the scene can be repaired."
    data = restored.BuildProjectData()
    decoded = DecodeProject(data, v.furnishingDefinitions)
    assert decoded[5]["history"]["undo"], "A repaired scene must retain history containing its old obstruction."
    restored.close()
    print("PASS: new walls cannot block openings, unrelated translations work, obstructed recovery and history survive, and repair remains possible.")


if __name__ == "__main__":
    Main()
