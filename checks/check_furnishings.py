"""Definitions, furnishing placement, footprint snaps, collision and scene editing."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Stair
from furnishings import LoadFurnishings, Furnishing
from theme import BuildStyle
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        (folder / "definitions").mkdir()
        (folder / "images").mkdir()
        for name, data in {"null": {"name": "Null", "image": "null", "width": 1100, "length": 1250,
                                   "icon": None, "category": "Miscellaneous", "inherits": None},
                           "parent": {"name": "Parent", "image": "missing", "width": 1500, "category": "Office"},
                           "child": {"inherits": "parent", "name": "Child", "length": 600},
                           "plain": {"name": "Plain"}}.items():
            (folder / "definitions" / f"{name}.json").write_text(json.dumps(data))
        definitions = {item["key"]: item for item in LoadFurnishings(folder)}
        child = definitions["child"]
        assert child["width"] == 1500 and child["length"] == 600 and child["category"] == "Office"
        assert child["imagePath"].name == "null.svg"
        assert definitions["parent"]["length"] == 1250
        assert definitions["plain"]["width"] == 1100 and definitions["plain"]["length"] == 1250
        assert definitions["plain"]["category"] == "Miscellaneous" and definitions["plain"]["icon"] is None
    window = MainWindow()
    window.show()
    app.processEvents()
    v = window.viewport
    v.unitsMode = "Centimeters"  # Property assertions below use centimeter values.
    v.snapEnabled = False
    window.sidebarTabs.setCurrentIndex(1)
    assert set(window.furnishingButtons) == {item["key"] for item in LoadFurnishings() if item["key"] != "null"}
    assert "desk" in window.furnishingButtons and "null" not in window.furnishingButtons
    assert "null" in window.viewport.furnishingDefinitions
    categories = [label.text() for label in window.furnishScrollArea.findChildren(QtWidgets.QLabel)
                  if label.objectName() == "objectSubheading" and label.isVisible()]
    expectedCategories = sorted({item["category"] for item in LoadFurnishings() if item["key"] != "null"},
                                key = lambda name: (name.casefold() in ("misc", "miscellaneous"), name.casefold()))
    assert categories == expectedCategories
    assert not any(label.text() == "Object Properties" for label in window.furnishScrollArea.findChildren(QtWidgets.QLabel))
    none = QtCore.Qt.KeyboardModifier.NoModifier
    left = QtCore.Qt.MouseButton.LeftButton
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-furnishing", b"desk")
    center = v.WorldToViewport(QtCore.QPointF())
    move = QtGui.QDragMoveEvent(center.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, left, none)
    v.dragMoveEvent(move)
    assert isinstance(v.furnishingPreview, Furnishing) and v.FurnishingFits(v.furnishingPreview)
    drop = QtGui.QDropEvent(center, QtCore.Qt.DropAction.CopyAction, mime, left, none)
    v.dropEvent(drop)
    assert drop.isAccepted() and len(v.furnishings) == 1
    desk = v.furnishings[0]
    assert desk.width == 1200 and desk.length == 600
    assert v.HitTest(v.WorldToViewport(desk.firstVertex)) == (desk, None)
    assert window.propertyFields["width"].value() == 120 and window.propertyFields["length"].value() == 60
    assert window.propertyFields["width"].suffix() == window.propertyFields["length"].suffix() == " cm"
    assert window.selectionLabel.text().startswith(desk.definition["name"] + " (#")
    v.Undo()
    assert not v.furnishings
    v.Redo()
    assert v.furnishings == [desk]
    window.propertyFields["length"].setValue(80)
    assert desk.length == 800
    v.Undo()
    assert desk.length == 600 and window.propertyFields["length"].value() == 60
    window.propertyFields["width"].setValue(140)
    assert desk.width == 1400
    v.Undo()
    assert desk.width == 1200
    # A furnishing can overlap other furnishings but not a wall or stair.
    second = Furnishing(desk.definition)
    v.furnishings.append(second)
    second.secondVertex = second.firstVertex + QtCore.QPointF(0, 500)
    v.SetSelection([(desk, None), (second, None)])
    assert window.propertyFields["length"].lineEdit().placeholderText() == "(different)"
    window.EditProperty("length", 75)
    assert desk.length == second.length == 750
    assert window.propertyFields["length"].value() == 75 and window.propertyFields["length"].suffix() == " cm"
    v.Undo()
    assert desk.length == 600 and second.length == 500
    assert v.OpeningsValid()
    v.furnishings.remove(second)
    v.SetSelection([(desk, None)])
    wall = Wall(QtCore.QPointF(-2000, 1000), QtCore.QPointF(2000, 1000), 200)
    v.walls = [wall]
    start = v.WorldToViewport(QtCore.QPointF()).toPoint()
    end = v.WorldToViewport(QtCore.QPointF(0, 1000)).toPoint()
    QtTest.QTest.mousePress(v, left, none, start)
    v.UpdateInteraction(QtCore.QPointF(end), none)
    assert not v.FurnishingFits(desk) and desk.firstVertex.y() > 0
    QtTest.QTest.mouseRelease(v, left, none, end)
    assert desk.firstVertex == QtCore.QPointF(0, -300)
    # Invalid intermediate positions can be dragged through to valid positions.
    Drag(v, start, v.WorldToViewport(QtCore.QPointF(0, 1600)).toPoint())
    assert desk.firstVertex == QtCore.QPointF(0, 1300)
    v.Undo()
    assert desk.firstVertex == QtCore.QPointF(0, -300)
    Drag(v, start, v.WorldToViewport(QtCore.QPointF(1400, 0)).toPoint(), QtCore.Qt.KeyboardModifier.ShiftModifier)
    assert len(v.furnishings) == 2
    assert v.furnishings[1].width == 1200 and v.furnishings[1].definition is desk.definition
    v.Undo()
    assert len(v.furnishings) == 1
    # Actual corners rather than wall/stair control vertices are snap targets.
    v.snapEnabled = True
    v.gridSnapEnabled = False
    v.midpointSnapEnabled = False
    targets = v.StairSnapTargets(desk)
    assert wall.firstVertex not in targets and wall.secondVertex not in targets
    snapped = v.FindFurnishingPlacement(v.WorldToViewport(QtCore.QPointF(0, 595)), desk.definition, none)
    assert max(corner.y() for corner in v.ObjectCorners(snapped)) == 900
    assert v.FurnishingFits(snapped)
    stair = Stair(QtCore.QPointF(0, -500), QtCore.QPointF(0, 500))
    v.walls = [stair]
    assert not v.FurnishingFits(desk)
    v.walls = []
    assert not v.StairFits(stair)
    second = Furnishing(desk.definition, QtCore.QPointF(1000, 0))
    second.width = 1600
    v.furnishings.append(second)
    v.SetSelection([(desk, None), (second, None)])
    assert window.propertyFields["width"].lineEdit().placeholderText() == "(different)"
    window.propertyFields["width"].setValue(130)
    assert desk.width == second.width == 1300
    v.Undo()
    assert desk.width == 1200 and second.width == 1600
    v.snapEnabled = False
    start = v.WorldToViewport(QtCore.QPointF()).toPoint()
    end = v.WorldToViewport(QtCore.QPointF(0, -1000)).toPoint()
    Drag(v, start, end)
    assert desk.firstVertex.y() == second.firstVertex.y() == -1300
    v.Undo()
    assert desk.firstVertex.y() == second.firstVertex.y() == -300
    v.furnishings.remove(second)
    v.SetSelection([(desk, None)])
    window.sidebarPanel.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "furnishings-sidebar.png"))
    v.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "furnishings-preview.png"))
    # Walls cover furnishing previews and selected furnishing borders.
    # Isolate occlusion from the wall's collision warning, which intentionally
    # changes its appearance when an intersecting furnishing is present.
    v.collisionSettings = dict.fromkeys(v.collisionSettings, False)
    v.walls = [Wall(QtCore.QPointF(-2000, 0), QtCore.QPointF(2000, 0), 200)]
    covered = v.grab().toImage()
    v.furnishings = []
    baseline = v.grab().toImage()
    sample = v.WorldToViewport(QtCore.QPointF(0, 0)).toPoint()
    assert covered.pixelColor(sample) == baseline.pixelColor(sample), (covered.pixelColor(sample).name(), baseline.pixelColor(sample).name())
    v.furnishings = [desk]
    v.walls = []
    v.DeleteSelected()
    assert not v.furnishings
    v.Undo()
    assert v.furnishings == [desk]
    window.close()
    print("PASS: inheritance/defaults/categories, SVG toolbar/drop, dimensions, no handles, property history, invalid rollback, duplication, footprint snaps and collisions.")


if __name__ == "__main__":
    Main()
