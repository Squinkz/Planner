"""Verify object identities, combined vertex panels and momentary door controls."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, Window, Door
from theme import BuildStyle
from planner_app.models import Furnishing, Pillar, Elevator, Label, Counter, Stair, Railing, Fireplace


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.unitsMode = "Adaptive Metric"  # Assertions below express lengths in meters.
    point = QtCore.QPointF
    wall = Wall(point(-2500, 0), point(2500, 0))
    opening = Window(wall, .15, .35)
    door = Door(wall, .6, .78)
    viewport.walls = [wall]
    viewport.windows = [opening, door]
    viewport.EnsureObjectIds()
    ids = [obj.objectId for obj in (wall, opening, door)]
    assert len(set(ids)) == 3 and all(isinstance(value, int) for value in ids)
    # Provisional placement candidates do not burn IDs.
    for index in range(10):
        viewport.FindWindowPlacement(viewport.WorldToViewport(point(0, 1500)))
    added = Wall(point(0, 2000), point(1000, 2000))
    viewport.walls.append(added)
    viewport.EnsureObjectIds()
    assert added.objectId == max(ids) + 1
    for obj, name in ((wall, "Wall"), (opening, "Standard Window"), (door, "Standard Door")):
        viewport.selectedWall = obj
        for vertexIndex in (None, 0, 1):
            viewport.selectedVertex = vertexIndex
            window.RefreshProperties()
            assert window.selectionLabel.text() == f"{name} (#{obj.objectId:04d})"
            assert window.wallProperties.isVisible()
            assert window.vertexProperties.isVisible() == (vertexIndex is not None)
            assert window.doorProperties.isVisible() == isinstance(obj, Window)
            if isinstance(obj, Window):
                assert abs(window.propertyFields["length"].value() * 1000 - obj.length) < .01
            else:
                assert window.propertyFields["length"].value() == 5
            if vertexIndex is not None:
                assert window.vertexProperties.title() == f"Point {vertexIndex + 1}"
                vertex = obj.firstVertex if vertexIndex == 0 else obj.secondVertex
                assert abs(window.propertyFields["x"].value() * 1000 - vertex.x()) < .01
            assert window.wallProperties.layout().isRowVisible(window.sizeRow) == (obj is wall)
    for fieldName, attribute in (("swing", "swingsOutwards"), ("hinge", "hingeAtSecond")):
        button = window.doorFields[fieldName]
        assert not button.isCheckable()
        text = button.text()
        original = getattr(door, attribute)
        button.click()
        assert getattr(door, attribute) != original and button.text() == text and not button.isChecked()
        button.click()
        assert getattr(door, attribute) == original
        viewport.Undo()
        assert getattr(door, attribute) != original
        viewport.Redo()
        assert getattr(door, attribute) == original
    # Object fields stay editable while a vertex is selected and refresh both sections.
    viewport.selectedVertex = 0
    window.RefreshProperties()
    window.propertyFields["length"].setValue(1.0)
    assert abs(door.length - 1000) < .01
    doorId = door.objectId
    viewport.DeleteSelected()
    assert all(obj is not door for obj in viewport.windows)
    viewport.Undo()
    assert door.objectId == doorId and any(obj is door for obj in viewport.windows)
    assert window.selectionLabel.text() == f"Standard Door (#{doorId:04d})"
    viewport.selectedVertex = 0
    window.RefreshProperties()
    app.processEvents()
    window.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "properties-preview.png"))
    # Center-position editors translate complete objects, with exact history and units.
    viewport.unitsMode = "Millimeters"
    for obj in (Furnishing(viewport.furnishingDefinitions["desk"]), Pillar(point(0, -200), point(0, 200)),
                Elevator(point(0, -600), point(0, 600)), Label(text = "Position")):
        viewport.walls = [obj] if isinstance(obj, Pillar) else []
        viewport.windows = []
        viewport.furnishings = [obj] if type(obj) is Furnishing else []
        viewport.labels = [obj] if isinstance(obj, Label) else []
        obj.angle = 37
        viewport.SetSelection([(obj, None)])
        fields = window.labelPositionFields if isinstance(obj, Label) else window.objectPositionFields
        row = window.labelPositionRow if isinstance(obj, Label) else window.objectPositionRow
        assert row.isVisible()
        dimensions = obj.width, obj.length, obj.angle
        old = point((obj.firstVertex + obj.secondVertex) / 2)
        fields["x"].setValue(1200)
        center = (obj.firstVertex + obj.secondVertex) / 2
        assert abs(center.x() - 1200) < 1e-6 and abs(center.y() - old.y()) < 1e-6
        assert all(abs(a - b) < 1e-6 for a, b in zip(dimensions, (obj.width, obj.length, obj.angle)))
        viewport.Undo()
        assert QtCore.QLineF((obj.firstVertex + obj.secondVertex) / 2, old).length() < 1e-6
        viewport.Redo()
        window.BeginPropertyDrag()
        fields["y"].setValue(-700)
        window.FinishPropertyDrag(True)
        assert abs(((obj.firstVertex + obj.secondVertex) / 2).y() - old.y()) < 1e-6
        viewport.unitsMode = "Inches"
        window.RefreshProperties()
        fields["x"].setValue(50)
        assert abs(((obj.firstVertex + obj.secondVertex) / 2).x() - 1270) < 1e-6
        viewport.unitsMode = "Millimeters"
        center = (obj.firstVertex + obj.secondVertex) / 2
        viewport.furnishingRotationObject = obj
        viewport.rotationPivot = center + point(300, -250)
        window.RefreshProperties()
        pivot = point(viewport.rotationPivot)
        assert abs(fields["x"].value() - pivot.x()) < .5
        assert abs(fields["y"].value() - pivot.y()) < .5
        window.BeginPropertyDrag()
        fields["x"].setValue(pivot.x() + 100)
        assert abs(viewport.rotationPivot.x() - pivot.x() - 100) < 1e-6
        assert QtCore.QLineF((obj.firstVertex + obj.secondVertex) / 2, center + point(100, 0)).length() < 1e-6
        window.FinishPropertyDrag(True)
        assert viewport.rotationPivot == pivot and viewport.furnishingRotationObject is obj
        assert QtCore.QLineF((obj.firstVertex + obj.secondVertex) / 2, center).length() < 1e-6
        viewport.furnishingRotationObject = None
        window.RefreshProperties()
        assert abs(fields["x"].value() - center.x()) < .5
        assert abs(fields["y"].value() - center.y()) < .5
        viewport.rotationPivot = None
    # Mixed center values use the same bulk-edit convention as other properties.
    first = Furnishing(viewport.furnishingDefinitions["desk"], point(0, 0))
    second = Furnishing(viewport.furnishingDefinitions["desk"], point(3000, 2000))
    viewport.walls, viewport.windows, viewport.labels = [], [], []
    viewport.furnishings = [first, second]
    viewport.SetSelection([(first, None), (second, None)])
    assert window.objectPositionFields["x"].mixedValue
    window.objectPositionFields["x"].setValue(-500)
    assert all(abs(((obj.firstVertex + obj.secondVertex) / 2).x() + 500) < 1e-6 for obj in (first, second))
    viewport.Undo()
    assert ((second.firstVertex + second.secondVertex) / 2).x() == 3000
    parent = Wall(point(-2000, 0), point(2000, 0))
    for obj in (parent, Counter(point(), point(0, 1000)), Stair(point(), point(0, 3000)),
                Railing(point(), point(0, 2000)), Fireplace(parent, .3, .7)):
        viewport.walls = [parent] if isinstance(obj, Fireplace) else [obj]
        viewport.windows = [obj] if isinstance(obj, Fireplace) else []
        viewport.furnishings = []
        viewport.SetSelection([(obj, None)])
        assert not window.objectPositionRow.isVisible()
    window.close()
    print("PASS: unique stable IDs, previews, combined properties, vertex sections, flips, edits and undo/redo.")


if __name__ == "__main__":
    Main()
