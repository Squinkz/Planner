"""Nominal imperial catalog/default sizes change new placements, never existing geometry."""
import copy
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall, Door, SwingingDoor, DoubleDoor, Window, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow
from planner_app.models import Furnishing, Counter, Stair, Pillar, Column, Elevator, Railing, Fireplace
from planner_app.placement_sizing import NominalPlacementSize, FurnishingPlacementSize
from planner_app.furnishing_search import FurnishingDimensionText, FindFurnishings
from planner_app.project_codec import DecodeProject


def Main():
    for mode in ("Inches", "Feet and Inches"):
        for millimeters in list(range(100, 1001, 50)) + [2000, 3000]:
            assert math.isclose(NominalPlacementSize(millimeters, mode), millimeters / 25 * 25.4)
        assert math.isclose(NominalPlacementSize(337.5, mode), 14 * 25.4)
        assert NominalPlacementSize(1, mode) == 25.4
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    main.ShowSettings()
    app.processEvents()
    v, panel = main.viewport, main.settingsWindow
    v.snapEnabled = False
    point = QtCore.QPointF
    wall = Wall(point(-10000, 0), point(10000, 0), 200)
    v.walls = [wall]
    door = Door(wall, .4, .445)
    v.windows = [door]
    definition = dict(v.furnishingDefinitions["desk"], width = 900, length = 2000)
    originalDefinition = copy.deepcopy(definition)
    existing = Furnishing(definition, point(0, 5000))
    v.furnishings = [existing]
    before = v.CaptureState()
    metricDefaults = copy.deepcopy((v.wallPresetWidths, v.openingDefaultSizes, v.miscDefaultSizes))
    sourceStair = Stair(point(0, 8000), point(1000, 8000), 1000)
    for mode in ("Inches", "Feet and Inches", "Centimeters", "Inches"):
        panel.SetUnitsMode(mode)
        assert v.CaptureState() == before, "Switching units changed existing geometry"
        assert (v.wallPresetWidths, v.openingDefaultSizes, v.miscDefaultSizes) == metricDefaults
        assert existing.Clone().width == 900 and existing.Clone().length == 2000
        assert v.FindStairPlacement(v.WorldToViewport(point(8000, 8000)), source = sourceStair).width == 1000
        assert math.isclose(v.InactiveOpening(point(5000, 0), Door, source = door).length, 900)
        assert definition == originalDefinition
        imperial = mode in ("Inches", "Feet and Inches")
        width, length = (914.4, 2032) if imperial else (900, 2000)
        preview = v.FindFurnishingPlacement(v.WorldToViewport(point(5000, 5000)), definition, QtCore.Qt.KeyboardModifier.NoModifier)
        assert math.isclose(preview.width, width) and math.isclose(preview.length, length)
        assert FurnishingPlacementSize(definition, mode) == (width, length)
        text = FurnishingDimensionText(definition, mode)
        if mode == "Inches":
            assert text == '36" × 80"'
            assert FindFurnishings([definition], 'w:36in l:80in', mode) == [definition]
            assert FindFurnishings([definition], 'w:900mm', mode) == [definition]  # Explicit metric queries use authored dimensions.
        elif mode == "Feet and Inches":
            assert text == '3\' 0" × 6\' 8"'
        assert math.isclose(v.newWallWidth, 203.2 if imperial else 200)
        for index, value in enumerate(metricDefaults[0]):
            assert math.isclose(main.wallWidthSelector.widths[index] * 10, NominalPlacementSize(value * 10, mode))
        position = v.WorldToViewport(point(5000, 0))
        for cls in (Door, SwingingDoor, DoubleDoor, Window, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow):
            expected = NominalPlacementSize(metricDefaults[1][cls.__name__] * 10, mode)
            expected *= 2 if cls in (SlidingDoor, PocketDoor, BarnDoor) else 1
            opening = v.FindWindowPlacement(position, openingType = cls)
            assert opening is not None and math.isclose(opening.length, expected), cls
            assert math.isclose(v.InactiveOpening(point(), cls).length, expected)
        position = v.WorldToViewport(point(8000, 8000))
        for cls in (Pillar, Column, Elevator, Railing):
            obj = v.FindArrowPlacement(position, QtCore.Qt.KeyboardModifier.NoModifier, cls)
            assert math.isclose(obj.width, NominalPlacementSize(metricDefaults[2][cls.__name__] * 10, mode))
            if cls is not Railing:
                assert math.isclose(obj.length, obj.width)
        counter = v.FindCounterPlacement(position, QtCore.Qt.KeyboardModifier.NoModifier)
        assert math.isclose(counter.width, 609.6 if imperial else 600)
        assert math.isclose(QtCore.QLineF(counter.firstVertex, counter.secondVertex).length(), 1016 if imperial else 1000)
        stair = v.FindStairPlacement(position)
        assert stair is not None and math.isclose(stair.width, 1016 if imperial else 1000)
        fireplace = v.FindFireplacePlacement(v.WorldToViewport(point(8000, 0)), QtCore.Qt.KeyboardModifier.NoModifier)
        assert fireplace is not None and math.isclose(fireplace.length, 1219.2 if imperial else 1200)
    # An explicit imperial default must not be nominalized a second time.
    panel.SetDefaultSize("Door", 35.5)
    panel.SetDefaultSize(2, 7.5)
    assert v.openingDefaultSizes["Door"] == 90 and v.wallPresetWidths[2] == 20
    assert math.isclose(v.DefaultPlacementSize("Door"), 35.5 * 25.4)
    assert math.isclose(v.newWallWidth, 7.5 * 25.4)
    panel.SetUnitsMode("Centimeters")
    assert v.DefaultPlacementSize("Door") == 900 and v.newWallWidth == 200
    panel.SetUnitsMode("Inches")
    assert panel.sizeFields["Door"].value() == 35.5 and panel.sizeFields[2].value() == 7.5
    assert v.CaptureState() == before
    placed = v.PlaceWindow(v.WorldToViewport(point(1000, 0)), openingType = Door)
    assert placed is not None and math.isclose(placed.length, 35.5 * 25.4)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "nominal.plan"
        assert main.SaveProject(path)
        expected = dict(v.imperialDefaultSizes)
        assert main.OpenProject(path)
        assert v.imperialDefaultSizes == expected
        assert math.isclose(v.DefaultPlacementSize("Door"), 35.5 * 25.4)
        assert math.isclose(v.newWallWidth, 7.5 * 25.4)
        assert math.isclose(v.windows[0].length, 900) and v.furnishings[0].width == 900
        assert v.furnishings[0].length == 2000 and v.walls[0].width == 200
        data = main.BuildProjectData()
        del data["settings"]["buildSettings"]["imperialSizes"]
        assert "imperialSizes" not in DecodeProject(data, v.furnishingDefinitions)[5]["buildSettings"]
    panel.buildResetButtons["Door"].click()
    assert "Door" not in v.imperialDefaultSizes
    assert math.isclose(v.DefaultPlacementSize("Door"), 914.4)
    assert math.isclose(panel.sizeFields["Door"].value(), 36)
    main.MarkProjectClean()
    main.close()
    restored = MainWindow()
    assert restored.viewport.imperialDefaultSizes.get("2") == 7.5 * 25.4
    assert restored.viewport.unitsMode == "Inches"
    assert math.isclose(restored.viewport.DefaultPlacementSize(2), 7.5 * 25.4)
    restored.MarkProjectClean()
    restored.close()


if __name__ == "__main__":
    Main()
