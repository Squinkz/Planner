"""Barn door placement, exterior panel, facing, history and persistence."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, BarnDoor, DrawOpeningSymbol
from planner_app.project_codec import DecodeProject
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.unitsMode = "Adaptive Metric"  # Assertions below use meters/centimeters.
    v.snapEnabled = False
    point = QtCore.QPointF
    wall = Wall(point(-4000, 0), point(4000, 0))
    v.walls = [wall]
    position = v.WorldToViewport(point())
    door = v.PlaceWindow(position, openingType = BarnDoor)
    assert isinstance(door, BarnDoor) and abs(door.length - 1800) < .001
    assert main.selectionLabel.text().startswith("Barn Door")
    assert main.propertyFields["doorSize"].value() == .9
    assert main.doorProperties.layout().isRowVisible(main.doorFields["swing"])
    assert v.IsObjectVisible(door)
    main.EditDoorProperty("swing")
    assert door.swingsOutwards
    v.Undo()
    assert not door.swingsOutwards
    v.Redo()
    assert door.swingsOutwards
    for x, y in ((-500, -500), (500, -500), (-500, 500), (500, 500)):
        v.OrientDoor(door, v.WorldToViewport(point(x, y)))
        assert door.hingeAtSecond == (x > 0) and door.swingsOutwards == (y < 0)
    clone = v.CloneOpening(door, wall)
    assert clone.hingeAtSecond == door.hingeAtSecond and clone.swingsOutwards == door.swingsOutwards
    # Both directions/facings retain a full panel outside the wall, 75% over the aperture.
    for slide in (False, True):
        for facing in (False, True):
            image = QtGui.QImage(260, 180, QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtGui.QColor("#0e0e0e"))
            painter = QtGui.QPainter(image)
            DrawOpeningSymbol(painter, point(30, 90), point(230, 90), 40, BarnDoor,
                              hingeAtSecond = slide, swingsOutwards = facing, color = "#ffffff", pixelsPerMillimeter = .2)
            painter.end()
            panelY = 116 if facing else 64
            startX, endX = (105, 205) if slide else (55, 155)
            assert image.pixelColor((startX + endX) // 2, panelY).name() == "#ffffff"
            oppositeY = 64 if facing else 116
            assert image.pixelColor(130, oppositeY).name() == "#0e0e0e"
            image.save(str(Path(__file__).resolve().parent.parent / "screenshots" / "barn-door.png"))
    # Facing-only measurements split the side opposite the exterior panel.
    for facing in (False, True):
        door.swingsOutwards = facing
        spans = v.WallDimensions([wall], v.ConnectedWallPath([wall]))
        cutSide = 1 if facing else -1
        cut = [span for span in spans if ((span[0] + span[1]) / 2).y() * cutSide > 0]
        continuous = [span for span in spans if ((span[0] + span[1]) / 2).y() * cutSide < 0]
        assert len(cut) == 3 and len(continuous) == 1
    v.SetSelection([(door, None)])
    try:
        assert v.CopySelection() and v.ReadClipboardSelection() is not None
        v.zoom = .5
        assert v.PasteSelection(v.WorldToViewport(point(2700, 0)))
        assert v.selectedWall.swingsOutwards == door.swingsOutwards
    finally:
        app.clipboard().clear()
        app.processEvents()
    main.ShowSettings()
    assert "BarnDoor" in main.settingsWindow.sizeFields
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "Barn.plan"
        assert main.SaveProject(path) and main.NewProject() and main.OpenProject(path)
        assert all(isinstance(obj, BarnDoor) and obj.swingsOutwards for obj in v.windows)
        legacy = main.BuildProjectData()
        del legacy["settings"]["buildSettings"]["openingSizes"]["BarnDoor"]
        assert DecodeProject(legacy, v.furnishingDefinitions)[5]["buildSettings"]["openingSizes"]["BarnDoor"] == 90
    main.close()
    restored = MainWindow()
    assert all(isinstance(obj, BarnDoor) and obj.swingsOutwards for obj in restored.viewport.windows)
    restored.close()
    print("PASS: barn palette/default, placement, orientation, exterior panel, history, clones, clipboard and recovery.")


if __name__ == "__main__":
    Main()
