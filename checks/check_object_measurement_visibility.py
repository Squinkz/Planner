"""Object measurement toggles invalidate rendering and survive undo/transports."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall, Door, Stair, Counter, Railing, Pillar, Label
from furnishings import Furnishing
from planner_app.project_codec import DecodeProject
from check_context_menus import OpenMenu, Click
from planner_app.export_plan import RenderPlan


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    wall = Wall(point(-2000, 0), point(2000, 0))
    door = Door(wall, .4, .6)
    v.walls, v.windows, v.labels, v.furnishings = [wall], [door], [], []
    v.snapEnabled = False
    v.showMeasurements = True
    assert OpenMenu(v, point(-1500, 0))[:6] == ["Subdivide Wall", "Material", "Flip Horizontal", "Flip Vertical", "Hide dimensions", None]
    Click(v, "Hide dimensions")
    assert wall.measurementHidden and not door.measurementHidden
    v.SetSelection([])
    v.grab()
    assert not any(wall in owners for first, second, owners in v.sceneMeasurements[1])
    assert OpenMenu(v, point(-1500, 0))[:6] == ["Subdivide Wall", "Material", "Flip Horizontal", "Flip Vertical", "Show dimensions", None]
    v.objectContextMenu.hide()
    v.Undo()
    assert not wall.measurementHidden
    v.Redo()
    assert wall.measurementHidden
    decoded = DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)
    assert decoded[0][0].measurementHidden and not decoded[1][0].measurementHidden
    main.ApplyProject(decoded, None)
    v.Undo()
    assert not v.walls[0].measurementHidden
    v.Redo()
    assert v.walls[0].measurementHidden
    # Selection dimensions stay visible despite the regular measurement override.
    door = v.windows[0]
    menu = OpenMenu(v, (door.firstVertex + door.secondVertex) / 2)
    assert menu[menu.index("Flip Dimension") + 1:][:4] == ["Flip Horizontal", "Flip Vertical", "Hide dimensions", None]
    Click(v, "Hide dimensions")
    v.grab()
    assert any(door in owners for first, second, owners in v.sceneMeasurements[1])
    v.SetSelection([])
    v.grab()
    assert not any(door in owners for first, second, owners in v.sceneMeasurements[1])
    hiddenImage = RenderPlan("measurement.plan", 80, (-3000, -2000, 6000, 4000), projectData = main.BuildProjectData(), applyTheme = False)
    v.ApplyObjectContextAction([v.walls[0], door], "measurementHidden", False)
    shownImage = RenderPlan("measurement.plan", 80, (-3000, -2000, 6000, 4000), projectData = main.BuildProjectData(), applyTheme = False)
    assert hiddenImage != shownImage
    v.showMeasurements = False
    assert "Hide dimensions" not in OpenMenu(v, point(-1500, 0))
    v.objectContextMenu.hide()
    v.showMeasurements = True
    # All capture categories, including furniture and text, support saved undo.
    objects = [cls(point(index * 3000, -3000), point(index * 3000 + 2000, -3000))
               for index, cls in enumerate((Stair, Counter, Railing, Pillar))]
    v.walls.extend(objects)
    v.furnishings = [Furnishing(v.furnishingDefinitions["desk"], point(0, -6000))]
    v.labels = [Label(point(3000, -6000))]
    allObjects = v.walls + v.windows + v.furnishings + v.labels
    v.undoHistory, v.redoHistory = [], []
    v.ApplyObjectContextAction(allObjects, "measurementHidden", True)
    data = main.BuildProjectData()
    decoded = DecodeProject(data, v.furnishingDefinitions)
    assert all(obj.measurementHidden for collection in (decoded[0], decoded[1], decoded[2], decoded[7]) for obj in collection)
    main.ApplyProject(decoded, None)
    v.Undo()
    assert not any(obj.measurementHidden for obj in v.walls + v.windows + v.furnishings + v.labels)
    v.Redo()
    v.SetSelection([(v.furnishings[0], None)])
    assert v.CopySelection()
    assert v.ReadClipboardSelection()["objects"][0]["measurementHidden"]
    v.collisionSettings = {key: False for key in v.collisionSettings}
    v.SetSelection([])
    assert v.PasteSelection(v.DrawingRect().center())
    assert v.SelectionEntries()[0][0].measurementHidden
    main.close()
    app.clipboard().clear()
    app.processEvents()


if __name__ == "__main__":
    Main()
