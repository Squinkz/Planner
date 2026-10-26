"""Dimension actions reflect effective modes, facing, geometry and hidden state."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from check_exterior_hidden_dimensions import Capture
from planner_app.dimension_policy import AvailableDimensionActions
from planner_app.models import (Wall, Door, DoubleDoor, SwingingDoor, SlidingDoor, PocketDoor, BarnDoor,
    BifoldDoor, OpenDoorway, Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Fireplace)
from planner_app.geometry.measurements import MeasurementOpening, BuildOpeningDimensions


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        p = QtCore.QPointF
        v.showMeasurements = v.measurementVisibility["walls"] = True
        supported = (Door, DoubleDoor, SlidingDoor, BarnDoor, Window, SilledWindow,
                     CasementWindow, AwningWindow, DoubleCasementWindow)
        kinds = (*supported, SwingingDoor, PocketDoor, BifoldDoor, OpenDoorway, Fireplace)
        for kind in kinds:
            walls = Rectangle(-2000, -2000, 4000, 4000)
            opening = kind(walls[0], .2, .4)
            InstallScene(main, walls + [opening])
            category = "doors" if kind in (Door, DoubleDoor, SwingingDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway) else "windows"
            for mode in ("All", "Exterior", "Exterior stacked"):
                v.wallMeasurementMode = mode
                for split in (0, 1, 2):
                    v.measurementSettings[category] = split
                    for exteriorFacing in (False, True):
                        if kind is SlidingDoor:
                            opening.panelsFlipped = exteriorFacing
                        elif hasattr(opening, "swingsOutwards"):
                            opening.swingsOutwards = not exteriorFacing if kind is BarnDoor else exteriorFacing
                        opening.measurementFlipped = False
                        for hidden in (False, True):
                            opening.measurementHidden = hidden
                            actions = AvailableDimensionActions(v, opening)
                            expectedHide = mode == "Exterior stacked" or kind is Fireplace or split != 2
                            expectedFlip = not hidden and kind in supported and split == 1 and mode == "All"
                            assert (actions.canHide, actions.canFlip) == (expectedHide, expectedFlip), (kind, mode, split, exteriorFacing, hidden, actions)
            # Actual exterior geometry, rather than type alone, gates controls.
            partition = Wall(p(0, -2000), p(0, 2000), 200)
            inside = kind(partition, .2, .4)
            InstallScene(main, walls + [partition, inside])
            v.measurementSettings[category] = 1
            for mode in ("Exterior", "Exterior stacked"):
                v.wallMeasurementMode = mode
                assert AvailableDimensionActions(v, inside).canHide is False
                assert AvailableDimensionActions(v, inside).canFlip is False
                assert not AvailableDimensionActions(v, partition).canHide
        # Exterior ignores facing and old facing-side split preferences.
        walls = Rectangle(-2000, -2000, 4000, 4000)
        window = Window(walls[0], .2, .4)
        InstallScene(main, walls + [window])
        v.wallMeasurementMode = "Exterior"
        v.measurementSettings["windows"] = 1
        v.SetSelection([(window, None)])
        main.RefreshProperties()
        assert not main.doorProperties.layout().isRowVisible(main.doorFields["measurement"])
        position = v.WorldToViewport((window.firstVertex + window.secondVertex) / 2)
        v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
        labels = [action.defaultWidget().accessibleName() for action in v.objectContextMenu.actions() if not action.isSeparator()]
        assert "Flip Dimension" not in labels and "Hide Dimension" in labels
        v.objectContextMenu.hide()
        main.EditDoorProperty("measurement")
        assert not window.measurementFlipped and AvailableDimensionActions(v, window).canHide
        v.ApplyObjectContextAction([window], "measurementHidden", True)
        main.RefreshProperties()
        assert not main.doorProperties.layout().isRowVisible(main.doorFields["measurement"])
        v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
        labels = [action.defaultWidget().accessibleName() for action in v.objectContextMenu.actions() if not action.isSeparator()]
        assert "Show Dimension" in labels and "Flip Dimension" not in labels
        v.objectContextMenu.hide()
        # Hidden dimensions cannot be flipped away from their Show action.
        originalFlip = window.measurementFlipped
        assert v.ApplyObjectContextAction([window], "measurementFlipped") is False
        main.EditDoorProperty("measurement")
        assert window.measurementFlipped == originalFlip
        assert AvailableDimensionActions(v, window).canHide
        # Facing changes must not strand the hidden flag on an interior side.
        main.EditDoorProperty("swing")
        assert AvailableDimensionActions(v, window).canHide
        assert not AvailableDimensionActions(v, window).canFlip
        v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
        labels = [action.defaultWidget().accessibleName() for action in v.objectContextMenu.actions() if not action.isSeparator()]
        assert "Show Dimension" in labels and "Flip Dimension" not in labels
        v.objectContextMenu.hide()
        v.ApplyObjectContextAction([window], "measurementHidden", False)
        assert not AvailableDimensionActions(v, window).canFlip
        assert AvailableDimensionActions(v, window).canHide
        main.EditDoorProperty("swing")
        v.ApplyObjectContextAction([window], "measurementHidden", True)
        walls[0].measurementHidden = True
        assert not AvailableDimensionActions(v, window).canHide
        assert not AvailableDimensionActions(v, window).canFlip
        walls[0].measurementHidden = False
        # Stacked mode ignores stored split preferences, including Off.
        v.wallMeasurementMode = "Exterior stacked"
        v.measurementSettings["windows"] = 2
        assert AvailableDimensionActions(v, window).canHide and not AvailableDimensionActions(v, window).canFlip
        main.RefreshProperties()
        assert not main.doorFields["measurement"].isVisible()
        v.SetSelection([])
        Capture(v)
        assert all(window not in owners for first, second, owners in v.sceneMeasurements[1])
        v.showMeasurements = False
        assert not AvailableDimensionActions(v, window).canHide
        v.showMeasurements = True
        v.measurementVisibility["walls"] = False
        assert not AvailableDimensionActions(v, window).canFlip
    # Inactive openings cannot borrow dimensions from unrelated cutter spans.
    for mode, flipped in ((2, False), (1, True)):
        opening = MeasurementOpening("window", (20, 0), (80, 0), (0, 0), (100, 0), mode, True, flipped, False, False, None)
        # midpoint above the parent axis: flipped=True measures the other side.
        cutter = (((1, 0, 30, 70), (0, 1, -10, 10)),)
        spans = BuildOpeningDimensions((0, 1), (100, 1), (1, 0), 100, (50, 1), ["wall"], [opening], cutter)
        assert all("window" not in owners for first, second, owners in spans)
    print("PASS: dimension action matrix, opening variants, facing/exterior geometry, hidden states, parent/global suppression and inactive ownership")


if __name__ == "__main__":
    Main()
