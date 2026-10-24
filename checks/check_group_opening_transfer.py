"""Multiple attached openings transfer together, including Shift copies."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Window, Door, SlidingDoor, SilledWindow, CasementWindow
from check_history import Drag


def Main():
    point = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.snapEnabled = v.connectedEnabled = False
        v.zoom = .4
        for case in range(8):
            duplicate = bool(case % 2)
            v.snapEnabled = case == 6
            source = Wall(point(-4000, 0), point(4000, 0), 240)
            if case // 2 == 0:
                target = Wall(point(-4000, 2000), point(4000, 2000), 360)
                destination = point(-2000, 2000)
            elif case // 2 == 1:
                target = Wall(point(4000, 2000), point(-4000, 2000), 120)
                destination = point(-2000, 2000)
            elif case // 2 == 2:
                target = Wall(point(2000, 1000), point(2000, 9000), 360)
                destination = point(2000, 3000)
            else:
                target = Wall(point(-4000, 2000), point(2000, 6500), 360)
                destination = point(-2500, 3125)
            firstType = (Window, Door, SlidingDoor, SilledWindow)[case // 2]
            secondType = CasementWindow if case >= 6 else Door
            first, second = firstType(source, .2, .3), secondType(source, .55, .65)
            second.hingeAtSecond = True
            InstallScene(main, [source, target, first, second])
            v.SetSelection([(first, None), (second, None)])
            start = (first.firstVertex + first.secondVertex) / 2
            modifiers = QtCore.Qt.KeyboardModifier.ShiftModifier if duplicate else QtCore.Qt.KeyboardModifier.NoModifier
            Drag(v, v.WorldToViewport(start).toPoint(), v.WorldToViewport(destination).toPoint(), modifiers)
            moved = [opening for opening in v.windows if opening.parentWall is target]
            assert len(moved) == 2, ("transfer", case, duplicate, [(obj.parentWall is source, obj.centerFraction) for obj in v.windows])
            assert all(abs(opening.length - 800) < .01 for opening in moved)
            assert abs(abs(moved[1].centerFraction - moved[0].centerFraction) * QtCore.QLineF(target.firstVertex, target.secondVertex).length() - 2800) < .01
            assert moved[1].hingeAtSecond
            assert len(v.windows) == (4 if duplicate else 2)
            if duplicate:
                assert first.parentWall is source and second.parentWall is source
            assert len(v.undoHistory) == 1 and v.OpeningsValid()
            v.Undo()
            assert len(v.windows) == 2 and all(obj.parentWall is source for obj in v.windows)
            v.Redo()
            assert len([obj for obj in v.windows if obj.parentWall is target]) == 2

        # A destination that cannot hold the entire set must not transfer only one.
        v.snapEnabled = False
        for blocked in (False, True):
            source = Wall(point(-4000, 0), point(4000, 0), 240)
            target = Wall(point(-4000, 2000), point(4000 if blocked else -2500, 2000), 240)
            first, second = Window(source, .2, .3), Door(source, .55, .65)
            blocker = Door(target, .55, .65) if blocked else None
            InstallScene(main, [source, target, first, second] + ([blocker] if blocker else []))
            v.SetSelection([(first, None), (second, None)])
            start = (first.firstVertex + first.secondVertex) / 2
            Drag(v, v.WorldToViewport(start).toPoint(), v.WorldToViewport(start + point(0, 2000)).toPoint())
            assert first.parentWall is source and second.parentWall is source
            assert abs(first.centerFraction - .25) < 1e-10 and abs(second.centerFraction - .6) < 1e-10
            assert not v.undoHistory

        # A stationary opening in the space between the selected pair is allowed.
        target = Wall(point(-4000, 2000), point(4000, 2000), 240)
        first, second = Window(source, .2, .3), Door(source, .55, .65)
        blocker = Window(target, .4, .45)
        InstallScene(main, [source, target, first, second, blocker])
        v.SetSelection([(first, None), (second, None)])
        start = (first.firstVertex + first.secondVertex) / 2
        Drag(v, v.WorldToViewport(start).toPoint(), v.WorldToViewport(start + point(0, 2000)).toPoint())
        assert all(obj.parentWall is target for obj in v.windows) and v.OpeningsValid()

        # Previewing another wall and returning must restore the original state;
        # toggling Shift must not leave temporary copies after cancellation.
        first, second = Window(source, .2, .3), Door(source, .55, .65)
        InstallScene(main, [source, target, first, second])
        v.SetSelection([(first, None), (second, None)])
        startPosition = v.WorldToViewport(start)
        endPosition = v.WorldToViewport(start + point(0, 2000))
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = startPosition.toPoint())
        v.UpdateInteraction(endPosition, QtCore.Qt.KeyboardModifier.NoModifier)
        assert all(obj.parentWall is target for obj in v.windows)
        v.UpdateInteraction(startPosition, QtCore.Qt.KeyboardModifier.NoModifier)
        assert all(obj.parentWall is source for obj in v.windows)
        v.UpdateInteraction(endPosition, QtCore.Qt.KeyboardModifier.ShiftModifier)
        assert len(v.windows) == 4 and first.parentWall is source and second.parentWall is source
        v.UpdateInteraction(endPosition, QtCore.Qt.KeyboardModifier.NoModifier)
        assert len(v.windows) == 2 and all(obj.parentWall is target for obj in v.windows)
        v.CancelInteraction()
        assert len(v.windows) == 2 and all(obj.parentWall is source for obj in v.windows)
        assert abs(first.centerFraction - .25) < 1e-10 and abs(second.centerFraction - .6) < 1e-10
        assert not v.undoHistory
        # In empty space the whole set follows the cursor as detached ghosts,
        # rather than staying drawn on its old parent until a wall is reached.
        for duplicate in (False, True):
            first, second = Window(source, .2, .3), Door(source, .55, .65)
            InstallScene(main, [source, target, first, second])
            v.SetSelection([(first, None), (second, None)])
            originalCenters = [(obj.firstVertex + obj.secondVertex) / 2 for obj in (first, second)]
            startPosition = v.WorldToViewport(originalCenters[0])
            modifiers = QtCore.Qt.KeyboardModifier.ShiftModifier if duplicate else QtCore.Qt.KeyboardModifier.NoModifier
            QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, modifiers, startPosition.toPoint())
            for delta in (point(200, 850), point(300, 1000)):
                position = v.WorldToViewport(originalCenters[0] + delta)
                v.UpdateInteraction(position, modifiers)
                assert len(v.groupOpeningPreviews) == 2
                assert v.inactiveOpeningPreview is v.groupOpeningPreviews[0]
                for preview, center in zip(v.groupOpeningPreviews, originalCenters):
                    assert QtCore.QLineF((preview.firstVertex + preview.secondVertex) / 2, center + delta).length() < .01
                    assert abs(preview.length - 800) < .01
                assert first.parentWall is source and second.parentWall is source
                assert abs(first.centerFraction - .25) < 1e-10 and abs(second.centerFraction - .6) < 1e-10
            capture = Path(__file__).resolve().parents[1] / "diagnostics" / ("opening-group-copy-ghost.png" if duplicate else "opening-group-ghost.png")
            assert v.grab().save(str(capture))
            v.UpdateInteraction(endPosition, modifiers)
            assert not v.groupOpeningPreviews and v.inactiveOpeningPreview is None
            assert len([obj for obj in v.windows if obj.parentWall is target]) == 2
            v.UpdateInteraction(position, modifiers)
            assert len(v.groupOpeningPreviews) == 2
            QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, modifiers, position.toPoint())
            assert not v.groupOpeningPreviews and v.inactiveOpeningPreview is None
            assert v.dragStart is None and len(v.windows) == 2 and not v.undoHistory
            assert first.parentWall is source and second.parentWall is source
    print("Group opening transfer and Shift copies retain spacing, properties and history")


if __name__ == "__main__":
    Main()
