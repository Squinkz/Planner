"""Required room-fill theme roles, inheritance and live canvas rendering."""
import json
import os
from pathlib import Path
import sys
import tempfile
import warnings

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics import palette
from planner_app.viewport.widget import DrawingViewport
from planner_app.paths import themesDirectory
from check_theme_collection import Contrast


def Main():
    assert "roomFill" in palette.canvasRoles and "roomFill" not in palette.uiRoles
    colors = dict(palette.themeDefinitions["Light Canvas"]["colors"])
    missing = dict(colors)
    del missing["roomFill"]
    sources = [
        dict(name = "Complete", type = "canvas", colors = colors),
        dict(name = "MissingRoom", type = "canvas", colors = missing),
        dict(name = "CustomRoom", type = "canvas", extends = "Complete", colors = {"roomFill": "#123456"}),
        dict(name = "BadUI", type = "ui", colors = {**palette.themeDefinitions["Light UI"]["colors"], "roomFill": "#123456"}),
    ]
    with tempfile.TemporaryDirectory() as directory:
        for index, source in enumerate(sources):
            (Path(directory) / f"{index}.json").write_text(json.dumps(source), encoding = "utf-8")
        with warnings.catch_warnings(record = True) as messages:
            themes = palette.LoadThemes(Path(directory))
        assert set(themes) == {"Complete", "CustomRoom"}
        assert len(messages) == 2 and any("missing color roles: roomFill" in str(message.message) for message in messages)
        assert themes["CustomRoom"]["colors"]["canvas"] == colors["canvas"]
        assert themes["CustomRoom"]["colors"]["roomFill"] == "#123456"
        assert themes["Complete"]["colors"]["roomFill"] == colors["roomFill"]
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    v = DrawingViewport()
    v.resize(900, 700)
    v.showGrid = v.showMeasurements = v.showTips = False
    from check_room_detection import Rectangle
    v.walls = Rectangle(-1100, -1100, 2200, 2200)
    v.roomDetection.Check()
    sample = v.WorldToViewport(QtCore.QPointF()).toPoint()
    originalUI, originalCanvas = palette.activeUITheme, palette.activeCanvasTheme
    try:
        for name, definition in palette.themeDefinitions.items():
            if definition["type"] != "canvas":
                continue
            # Every bundled canvas explicitly authors a room color.
            source = next(source for source in themesDirectory.glob("*.jsonc")
                          if '"name": "' + name + '"' in source.read_text(encoding = "utf-8"))
            assert '"roomFill"' in source.read_text(encoding = "utf-8"), name
            roleColors = definition["colors"]
            assert roleColors["roomFill"] != roleColors["canvas"], name
            assert Contrast(roleColors["objectOutline"], roleColors["roomFill"]) >= 7, name
            assert Contrast(roleColors["measurementLine"], roleColors["roomFill"]) >= 3, name
            palette.SetThemes(canvasTheme = name)
            assert v.grab().toImage().pixelColor(sample) == QtGui.QColor(roleColors["roomFill"]), name
        # The room role alone invalidates retained backgrounds and scene pixels.
        previous = v.viewportBackgroundKey, v.viewportSceneKey
        palette.themeColors["roomFill"] = "#13579b"
        assert v.grab().toImage().pixelColor(sample) == QtGui.QColor("#13579b")
        assert (v.viewportBackgroundKey, v.viewportSceneKey) != previous
    finally:
        palette.SetThemes(originalUI, originalCanvas)
        v.close()
    print("Room themes: strict required canvas role, inheritance/override, all bundled fills, contrast and live cache invalidation passed")


if __name__ == "__main__":
    Main()
