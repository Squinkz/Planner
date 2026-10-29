"""Project preferences and panel-state validation can run without Qt."""
from pathlib import Path
import subprocess
import sys


def CheckWithoutQt():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
    from planner_app.project_settings import ReadProjectSettings, ReadEditorUi, snapNames, visibilityNames
    settings = dict(snapEnabled = True, connectedVertices = True, connectedObjects = True, groupMode = False,
        showGrid = True, showMeasurements = True, snap = {name: True for name in snapNames},
        visibility = {name: True for name in visibilityNames}, wallWidth = 240, wallMaterial = "Generic",
        doorType = "Door", windowType = "Window", floors = False)
    flags = ReadProjectSettings(settings, {"Generic"}, {"overall": 1}, str, dict)
    assert flags["roomStyle"] == "Canvas" and flags["floors"] is False
    assert flags["stairStepSizes"] == dict(minimum = 25., maximum = 30.)
    assert "roomStyle" not in settings
    ui = dict(mainSplitter = [100, 200], propertiesSplitter = [50, 100], propertiesCollapsed = False)
    ReadEditorUi(ui)
    recovered = dict(ui, geometry = "", scroll = [], tab = 0, expanded = {}, selection = [[7, 3]])
    ReadEditorUi(recovered, recovery = True, tabCount = 2, selectionLimit = lambda key: (2, True))
    recovered["selection"] = [[7, 2]]
    try:
        ReadEditorUi(recovered, recovery = True, tabCount = 2, selectionLimit = lambda key: (2, True))
    except ValueError:
        pass
    else:
        raise AssertionError("A guide's missing third control point was accepted")
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: project settings and panel-state policies without Qt")


if __name__ == "__main__":
    if "--without-qt" in sys.argv:
        CheckWithoutQt()
    else:
        result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"], capture_output = True, text = True, timeout = 10)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout.strip())
