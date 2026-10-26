"""Per-opening measurement flips: context gating, history, cloning and persistence."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall, Door, SlidingDoor, BarnDoor, Window, SilledWindow, CasementWindow, PocketDoor, BifoldDoor, OpenDoorway
from planner_app.project_codec import DecodeProject
from check_context_menus import OpenMenu, Click


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.wallMeasurementMode = "All"
    main.ShowSettings()
    main.settingsWindow.hide()
    point = QtCore.QPointF
    wall = Wall(point(-1800, 0), point(1800, 0))
    v.walls = [wall]
    v.measurementSettings.update({"doors": 1, "windows": 1})
    for cls in (Door, SlidingDoor, BarnDoor, Window, SilledWindow, CasementWindow):
        opening = cls(wall, .2, .4)
        v.windows = [opening]
        v.SetSelection([(opening, None)])
        assert main.doorFields["measurement"].isVisible()
        main.settingsWindow.SetWallMeasurementMode("Exterior stacked")
        assert not main.doorFields["measurement"].isVisible()
        assert "Flip Dimension" not in OpenMenu(v, (opening.firstVertex + opening.secondVertex) / 2)
        originalFlip = opening.measurementFlipped
        v.ApplyObjectContextAction([opening], "measurementFlipped")
        main.EditDoorProperty("measurement")
        assert opening.measurementFlipped == originalFlip
        main.settingsWindow.SetWallMeasurementMode("Exterior")
        assert not main.doorFields["measurement"].isVisible()
        assert "Flip Dimension" not in OpenMenu(v, (opening.firstVertex + opening.secondVertex) / 2)
        main.settingsWindow.SetWallMeasurementMode("All")
        assert main.doorFields["measurement"].isVisible()
        path = v.ConnectedWallPath([wall])
        before = v.WallDimensions([wall], path)
        counts = [sum(((first + second) / 2).y() * side > 0 for first, second, owners in before) for side in (1, -1)]
        assert sorted(counts) == [1, 3]
        labels = OpenMenu(v, (opening.firstVertex + opening.secondVertex) / 2)
        assert "Flip Dimension" in labels
        Click(v, "Flip Dimension")
        assert opening.measurementFlipped
        after = v.WallDimensions([wall], path)
        flippedCounts = [sum(((first + second) / 2).y() * side > 0 for first, second, owners in after) for side in (1, -1)]
        assert flippedCounts == counts[::-1]
        assert v.CloneOpening(opening, wall).measurementFlipped
        v.Undo()
        assert not opening.measurementFlipped and v.WallDimensions([wall], path) == before
        v.Redo()
        assert opening.measurementFlipped
        main.doorFields["measurement"].click()
        assert not opening.measurementFlipped
        v.Undo()
        assert opening.measurementFlipped
        project = main.BuildProjectData()
        assert DecodeProject(project, v.furnishingDefinitions)[1][0].measurementFlipped
        for record in project["scene"]["objects"]:
            record.pop("measurementFlipped", None)
        assert not DecodeProject(project, v.furnishingDefinitions)[1][0].measurementFlipped
        key = "windows" if cls in (Window, SilledWindow, CasementWindow) else "doors"
        for mode in (0, 2):
            v.measurementSettings[key] = mode
            main.RefreshProperties()
            assert not main.doorFields["measurement"].isVisible()
            assert "Flip Dimension" not in OpenMenu(v, (opening.firstVertex + opening.secondVertex) / 2)
            spans = v.WallDimensions([wall], path)
            opening.measurementFlipped = False
            assert v.WallDimensions([wall], path) == spans
        v.measurementSettings[key] = 1
    for cls in (PocketDoor, BifoldDoor, OpenDoorway):
        opening = cls(wall, .2, .4)
        v.windows = [opening]
        v.SetSelection([(opening, None)])
        assert not main.doorFields["measurement"].isVisible()
        assert "Flip Dimension" not in OpenMenu(v, (opening.firstVertex + opening.secondVertex) / 2)
    # A homogeneous selection flips every opening; clipboard copies retain it.
    first, second = Door(wall, .1, .3), Door(wall, .6, .8)
    v.windows = [first, second]
    v.SetSelection([(first, None), (second, None)])
    OpenMenu(v, (first.firstVertex + first.secondVertex) / 2)
    Click(v, "Flip Dimension")
    assert first.measurementFlipped and second.measurementFlipped
    v.SetSelection([(wall, None), (first, None), (second, None)])
    v.CopySelection()
    records = v.ReadClipboardSelection()["objects"]
    assert all(record["measurementFlipped"] for record in records if record["type"] == "Door")
    v.PasteSelection(v.WorldToViewport(point(0, 2000)))
    assert len(v.windows) == 4 and all(opening.measurementFlipped for opening in v.windows)
    v.objectContextMenu.hide()
    v.SetSelection([(opening, None) for opening in v.windows])
    main.ShowSettings()
    main.settingsWindow.SetMeasurementMode("doors", 0)
    assert not main.doorFields["measurement"].isVisible()
    main.settingsWindow.SetMeasurementMode("doors", 1)
    assert main.doorFields["measurement"].isVisible()
    main.doorFields["measurement"].click()
    assert all(not opening.measurementFlipped for obj, index in v.SelectionEntries()
               for opening in ([obj] if isinstance(obj, Door) else []))
    main.close()
    app.clipboard().clear()
    app.processEvents()


if __name__ == "__main__":
    Main()

