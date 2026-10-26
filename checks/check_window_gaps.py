"""Every opening fits short walls and free intervals when placed or moved."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    none = QtCore.Qt.KeyboardModifier.NoModifier
    openingTypes = (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway)
    for direction in (point(1, 0), point(-1, 0), point(.6, .8)):
        parent = Wall(direction * -2500, direction * 2500)
        for openingType in openingTypes:
            viewport.walls = [parent]
            viewport.windows = [openingType(parent, 0, .2), openingType(parent, .35, .65), openingType(parent, .8, 1)]
            for snap in (False, True):
                viewport.snapEnabled = snap
                for gapStart, gapEnd in ((.2, .35), (.65, .8)):
                    cursor = parent.firstVertex + (parent.secondVertex - parent.firstVertex) * ((gapStart + gapEnd) / 2)
                    for placedType in openingTypes:
                        candidate = viewport.FindWindowPlacement(viewport.WorldToViewport(cursor), 1200, openingType = placedType, modifiers = none)
                        assert candidate is not None and abs(candidate.length - 750) < .01, placedType.__name__
                        assert abs(candidate.firstFraction - gapStart) < 1e-8
                        assert abs(candidate.secondFraction - gapEnd) < 1e-8
                        assert viewport.OpeningFits(candidate)
                occupied = parent.firstVertex + (parent.secondVertex - parent.firstVertex) * .5
                assert viewport.FindWindowPlacement(viewport.WorldToViewport(occupied), openingType = Window, modifiers = none) is None
    parent = Wall(point(-2500, 0), point(2500, 0))
    source = Wall(point(-2500, 1800), point(2500, 1800))
    moving = Window(source, .38, .62)
    viewport.walls = [parent, source]
    viewport.windows = [Door(parent, 0, .2), PocketDoor(parent, .35, .65), moving]
    viewport.snapEnabled = False
    viewport.selectedWall = moving
    viewport.undoHistory = []
    start = viewport.WorldToViewport((moving.firstVertex + moving.secondVertex) / 2).toPoint()
    target = viewport.WorldToViewport(point(-1125, 0)).toPoint()
    Drag(viewport, start, target)
    assert moving.parentWall is parent and abs(moving.length - 750) < .01
    assert abs(moving.firstFraction - .2) < 1e-8 and abs(moving.secondFraction - .35) < 1e-8
    viewport.Undo()
    assert moving.parentWall is source and abs(moving.length - 1200) < .01
    viewport.Redo()
    assert moving.parentWall is parent and abs(moving.length - 750) < .01
    # Ignore the moving window's previous interval when finding its new bounds.
    candidate = viewport.FindWindowPlacement(point(target), moving.length, parent, Window, moving, none)
    assert candidate is not None and abs(candidate.length - 750) < .01
    # Short empty walls use the same bounds for defaults and dragged objects.
    for direction in (point(1, 0), point(-1, 0), point(.6, .8)):
        parent = Wall(direction * -200, direction * 200)
        viewport.walls = [parent]
        viewport.windows = []
        for openingType in openingTypes:
            for snap in (False, True):
                viewport.snapEnabled = snap
                candidate = viewport.FindWindowPlacement(viewport.WorldToViewport(point()), openingType = openingType, modifiers = none)
                assert candidate is not None and abs(candidate.length - 400) < .01, openingType.__name__
                assert abs(candidate.firstFraction) < 1e-8 and abs(candidate.secondFraction - 1) < 1e-8
    # Complete drag/release, history and cancellation for every mounted type.
    for openingType in openingTypes:
        parent = Wall(point(-200, 0), point(200, 0))
        source = Wall(point(-2000, 1800), point(2000, 1800))
        moving = openingType(source, .35, .65)
        viewport.walls, viewport.windows = [parent, source], [moving]
        viewport.snapEnabled = False
        viewport.undoHistory, viewport.redoHistory = [], []
        viewport.SetSelection([(moving, None)])
        start = viewport.WorldToViewport(point(0, 1800)).toPoint()
        target = viewport.WorldToViewport(point()).toPoint()
        Drag(viewport, start, target)
        assert moving.parentWall is parent and abs(moving.length - 400) < .01, openingType.__name__
        viewport.Undo()
        assert moving.parentWall is source and abs(moving.length - 1200) < .01
        viewport.Redo()
        assert moving.parentWall is parent and abs(moving.length - 400) < .01
        viewport.Undo()
        QtWidgets.QApplication.sendEvent(viewport, QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress, point(start), point(viewport.mapToGlobal(start)),
            QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.LeftButton, none))
        viewport.UpdateInteraction(point(target), none)
        assert abs(moving.length - 400) < .01
        viewport.CancelInteraction()
        assert moving.parentWall is source and abs(moving.length - 1200) < .01
    # Short segments in angled wall chains have less clear space than their
    # control-axis length, because adjacent wall footprints occupy the joins.
    joins = [point(-700, 0), point(-200, 0), point(200, 300), point(0, 850)]
    chain = [Wall(first, second, 240) for first, second in zip(joins, joins[1:])]
    viewport.walls, viewport.windows = chain, []
    for parent in chain:
        cursor = (parent.firstVertex + parent.secondVertex) / 2
        for openingType in openingTypes:
            candidate = viewport.FindWindowPlacement(viewport.WorldToViewport(cursor), openingType = openingType, modifiers = none)
            assert candidate is not None and candidate.parentWall is parent, openingType.__name__
            assert 1 < candidate.length < QtCore.QLineF(parent.firstVertex, parent.secondVertex).length()
            assert viewport.OpeningFits(candidate)
    # Native movement onto the joined middle section, with reversible sizing.
    source = Wall(point(-1500, -1800), point(1500, -1800))
    parent = chain[1]
    cursor = (parent.firstVertex + parent.secondVertex) / 2
    for openingType in openingTypes:
        moving = openingType(source, .3, .7)
        viewport.walls, viewport.windows = chain + [source], [moving]
        viewport.undoHistory, viewport.redoHistory = [], []
        viewport.SetSelection([(moving, None)])
        Drag(viewport, viewport.WorldToViewport(point(0, -1800)).toPoint(), viewport.WorldToViewport(cursor).toPoint())
        assert moving.parentWall is parent and 1 < moving.length < 500, openingType.__name__
        assert viewport.OpeningFits(moving, moving)
        viewport.Undo()
        assert moving.parentWall is source and abs(moving.length - 1200) < .01
    viewport.walls, viewport.windows = chain, []
    for parent in chain:
        cursor = (parent.firstVertex + parent.secondVertex) / 2
        assert viewport.PlaceWindow(viewport.WorldToViewport(cursor)) is not None
    viewport.SetSelection([])
    viewport.grab().save(str(Path(__file__).resolve().parents[1] / "screenshots" / "joined-wall-openings.png"))
    window.close()
    print("PASS: all opening types fit free gaps and short walls, including snapping, movement, cancellation and undo/redo.")


if __name__ == "__main__":
    Main()
