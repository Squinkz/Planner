"""Measurement context actions follow regular measurements, never selection bounds."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtWidgets
from planner import MainWindow
from planner_app.models import Wall, Pillar, Column, Stair, Counter, Railing, Door, Window, Fireplace, Label, NorthArrow, Furnishing, Arrow, MeasurementGuide


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.wallMeasurementMode = "All"  # Exercise facing-side flips independently of exterior-mode gating.
    point = QtCore.QPointF

    def MenuFor(obj):
        v.objectContextMenu.hide()
        v.walls, v.windows, v.furnishings, v.labels = [], [], [], []
        if isinstance(obj, Window):
            v.walls, v.windows = [obj.parentWall], [obj]
        elif isinstance(obj, Label):
            v.labels = [obj]
        elif isinstance(obj, Furnishing):
            v.furnishings = [obj]
        else:
            v.walls = [obj]
        v.SetSelection([(obj, None)])
        corners = v.ObjectCorners(obj)
        center = sum(corners, point()) / len(corners)
        position = v.WorldToViewport(center)
        assert v.HitTest(position)[0] is obj
        v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
        return [action.defaultWidget().accessibleName() for action in v.objectContextMenu.actions() if not action.isSeparator()]

    for obj in (Label(), NorthArrow(), Furnishing(v.furnishingDefinitions["desk"]), Arrow(point(-1000, 0), point(1000, 0))):
        assert "Hide Dimension" not in MenuFor(obj)
        obj.measurementHidden = True
        assert "Show Dimension" not in MenuFor(obj)
    for cls, category in ((Wall, "walls"), (Pillar, "walls"), (Column, "walls"),
                          (Stair, "stairs"), (Counter, "counters"), (Railing, "railings")):
        obj = cls(point(-1000, 0), point(1000, 0))
        v.measurementVisibility[category] = True
        assert "Hide Dimension" in MenuFor(obj)
        obj.measurementHidden = True
        assert "Show Dimension" in MenuFor(obj)
        v.measurementVisibility[category] = False
        assert "Show Dimension" not in MenuFor(obj)
        obj.measurementHidden = False
        assert "Hide Dimension" not in MenuFor(obj)
        v.measurementVisibility[category] = True
    wall = Wall(point(-2000, 0), point(2000, 0))
    for cls, category in ((Door, "doors"), (Window, "windows")):
        obj = cls(wall, .4, .6)
        for mode in (0, 1):
            v.measurementSettings[category] = mode
            assert "Hide Dimension" in MenuFor(obj)
        v.measurementSettings[category] = 2
        assert "Hide Dimension" not in MenuFor(obj)
        v.measurementSettings[category] = 1
        v.measurementVisibility["walls"] = False
        assert "Hide Dimension" not in MenuFor(obj)
        assert "Flip Dimension" not in MenuFor(obj)
        assert not main.doorProperties.layout().isRowVisible(main.doorFields["measurement"])
        v.measurementVisibility["walls"] = True
        v.showMeasurements = False
        for hidden in (False, True):
            obj.measurementHidden = hidden
            labels = MenuFor(obj)
            assert not any(label in labels for label in ("Flip Dimension", "Hide Dimension", "Show Dimension"))
            assert not main.doorProperties.layout().isRowVisible(main.doorFields["measurement"])
        v.showMeasurements = True
        assert "Show Dimension" in MenuFor(obj)
        assert "Flip Dimension" not in MenuFor(obj)
        assert not main.doorProperties.layout().isRowVisible(main.doorFields["measurement"])
        obj.measurementHidden = False
        assert "Flip Dimension" in MenuFor(obj)
        assert main.doorProperties.layout().isRowVisible(main.doorFields["measurement"])
    main.SetViewOption("showMeasurements")
    assert not main.doorProperties.layout().isRowVisible(main.doorFields["measurement"])
    main.SetViewOption("showMeasurements")
    assert main.doorProperties.layout().isRowVisible(main.doorFields["measurement"])
    main.ShowSettings()
    main.settingsWindow.SetMeasurementVisibility("walls", False)
    assert not main.doorProperties.layout().isRowVisible(main.doorFields["measurement"])
    main.settingsWindow.SetMeasurementVisibility("walls", True)
    assert main.doorProperties.layout().isRowVisible(main.doorFields["measurement"])
    fireplace = Fireplace(wall, .4, .6)
    assert "Hide Dimension" in MenuFor(fireplace)
    v.measurementVisibility["walls"] = False
    assert "Hide Dimension" not in MenuFor(fireplace)
    v.measurementVisibility["walls"] = True
    guide = MeasurementGuide(point(-1000, 0), point(1000, 0))
    assert "Hide Dimension" in MenuFor(guide)
    v.showMeasurements = False
    assert "Hide Dimension" in MenuFor(guide)  # Standalone annotations still draw with ambient dimensions off.
    v.objectContextMenu.hide()
    main.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
