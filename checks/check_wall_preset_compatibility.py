"""Factory wall presets change without migrating stored presets or geometry."""
import copy
import json
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall
from planner_app.project_codec import DecodeProject


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        assert v.wallPresetWidths == [10, 15, 20, 30] and v.newWallWidth == 200
        main.ShowSettings()
        settings = main.settingsWindow
        assert [settings.sizeFields[index].value() for index in range(4)] == [100, 150, 200, 300]
        wall = Wall(QtCore.QPointF(-2000, 0), QtCore.QPointF(2000, 0), 240)
        InstallScene(main, [wall])
        stored = main.BuildProjectData(includeHistory = False)
        for widths in ([8, 12, 16, 24], [9, 13, 17, 31]):
            data = copy.deepcopy(stored)
            data["settings"]["buildSettings"]["wallWidths"] = widths
            data["settings"]["wallWidth"] = 237  # Preserve exact non-preset selection too.
            path = folder / "existing.plan"
            original = json.dumps(data, indent = 2).encode("utf-8")
            path.write_bytes(original)
            assert main.OpenProject(path)
            assert path.read_bytes() == original
            assert v.wallPresetWidths == widths and main.wallWidthSelector.widths == tuple(widths)
            assert v.newWallWidth == 237 and v.walls[0].width == 240
            assert [settings.sizeFields[index].value() for index in range(4)] == [width * 10 for width in widths]
            roundtrip = main.BuildProjectData(includeHistory = False)
            assert roundtrip["scene"] == data["scene"]
            assert roundtrip["settings"]["buildSettings"]["wallWidths"] == widths
            assert roundtrip["settings"]["wallWidth"] == 237
            decoded = DecodeProject(roundtrip, v.furnishingDefinitions)
            assert decoded[5]["buildSettings"]["wallWidths"] == widths and decoded[0][0].width == 240
            main.startupPath.write_bytes(original)
            assert main.NewProject()
            assert v.wallPresetWidths == widths and v.newWallWidth == 237 and v.walls[0].width == 240
            assert main.startupPath.read_bytes() == original and path.read_bytes() == original
            main.startupPath.unlink()
            assert main.NewProject()
            assert v.wallPresetWidths == [10, 15, 20, 30] and v.newWallWidth == 200 and not v.walls
        bundledStartup = Path(__file__).resolve().parents[1] / "planner-main" / "startup.plan"
        startupBytes = bundledStartup.read_bytes()
        main.startupPath.write_bytes(startupBytes)
        assert main.NewProject()
        assert v.wallPresetWidths == [10, 15, 20, 30] and v.newWallWidth == 200
        assert main.wallWidthSelector.slider.value() == 2
        assert main.wallWidthSelector.widths == (10, 15, 20, 30)
        assert [settings.sizeFields[index].value() for index in range(4)] == [100, 150, 200, 300]
        assert bundledStartup.read_bytes() == startupBytes
    print("Wall presets: factory and bundled startup defaults, old/custom projects and startup templates, exact widths and roundtrips passed")


if __name__ == "__main__":
    Main()
