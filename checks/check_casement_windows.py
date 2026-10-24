"""Casement facing, swing geometry, measurements and project recovery."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, CasementWindow, DrawOpeningSymbol
from planner_app.project_codec import DecodeProject


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.unitsMode = "Adaptive Metric"  # Assertions below use meters/centimeters.
    v.snapEnabled = False
    point = QtCore.QPointF
    wall = Wall(point(-4000, 0), point(4000, 0), 240)
    v.walls = [wall]
    opening = v.PlaceWindow(v.WorldToViewport(point()), openingType = CasementWindow)
    assert abs(opening.length - 600) < .001
    assert main.selectionLabel.text().startswith("Casement Window")
    assert main.doorProperties.layout().isRowVisible(main.doorFields["swing"])
    assert main.doorProperties.layout().isRowVisible(main.doorFields["hinge"])
    assert not main.wallProperties.layout().isRowVisible(main.propertyFields["sillDepth"])
    main.EditDoorProperty("swing")
    assert opening.swingsOutwards
    v.Undo()
    assert not opening.swingsOutwards
    v.Redo()
    assert opening.swingsOutwards
    main.EditDoorProperty("hinge")
    assert opening.hingeAtSecond
    v.Undo()
    assert not opening.hingeAtSecond
    v.Redo()
    assert opening.hingeAtSecond
    for x, y in ((-500, -500), (500, -500), (-500, 500), (500, 500)):
        v.OrientDoor(opening, v.WorldToViewport(point(x, y)))
        assert opening.swingsOutwards == (y > 0) and opening.hingeAtSecond == (x > 0)
    assert v.CloneOpening(opening, wall).hingeAtSecond and v.CloneOpening(opening, wall).swingsOutwards
    assert v.InactiveOpening(point(), CasementWindow, opening).hingeAtSecond and v.InactiveOpening(point(), CasementWindow, opening).swingsOutwards
    assert v.IsObjectVisible(opening)
    v.visibility["Windows"] = False
    assert not v.IsObjectVisible(opening)
    v.visibility["Windows"] = True

    class SymbolPainter(QtGui.QPainter):
        def drawPath(self, path):
            arcs.append(path)
            super().drawPath(path)

        def drawLine(self, line):
            lines.append(line)
            super().drawLine(line)

    image = QtGui.QImage(320, 260, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtGui.QColor("#0e0e0e"))
    for hingeAtSecond in (False, True):
        for facing in (False, True):
            arcs, lines = [], []
            painter = SymbolPainter(image)
            DrawOpeningSymbol(painter, point(30, 130), point(270, 130), 40, CasementWindow,
                              hingeAtSecond = hingeAtSecond, swingsOutwards = facing,
                              color = "#ffffff", pixelsPerMillimeter = .2)
            painter.end()
            assert len(arcs) == 1 and len(lines) == 7
            # Identify perimeter and swing geometry independently of draw order.
            faces = [line for line in lines if abs(line.dy()) < .001 and line.y1() in (110, 150)]
            assert {line.y1() for line in faces} == {110, 150}
            assert len(faces) == 2 and all(abs(line.length() - 240) < .001 for line in faces)
            swings = [line for line in lines if abs(line.dx()) > .001 and abs(line.dy()) > .001]
            assert len(swings) == 1
            swing = swings[0]
            assert abs(swing.length() - 240) < .001
            assert (swing.dy() < 0) == facing
            assert swing.p1().x() == (270 if hingeAtSecond else 30)
            assert (swing.dx() < 0) == hingeAtSecond
            assert abs(abs(swing.dy()) - 120) < .001
            assert QtCore.QLineF(arcs[0].currentPosition(), swing.p2()).length() < .1
            # The end crossbars cover the perimeter and swing junctions last.
            assert {line.x1() for line in lines[-2:]} == {30, 270}
            assert all(line.dx() == 0 and {line.y1(), line.y2()} == {110, 150} for line in lines[-2:])
    image.save(str(Path(__file__).resolve().parent.parent / "screenshots" / "casement-window.png"))
    for mode in (0, 1, 2):
        v.measurementSettings["windows"] = mode
        for facing in (False, True):
            opening.swingsOutwards = facing
            spans = v.WallDimensions([wall], v.ConnectedWallPath([wall]))
            cutSide = -1 if facing else 1
            for side in (-1, 1):
                expected = 3 if mode == 0 or (mode == 1 and side == cutSide) else 1
                assert len([span for span in spans if ((span[0] + span[1]) / 2).y() * side > 0]) == expected
    v.SetSelection([(opening, None)])
    try:
        assert v.CopySelection()
        v.zoom = .5
        assert v.PasteSelection(v.WorldToViewport(point(2700, 0)))
        assert type(v.selectedWall) is CasementWindow and v.selectedWall.swingsOutwards and v.selectedWall.hingeAtSecond
    finally:
        app.clipboard().clear()
        app.processEvents()
    v.openingPlacementIndices["Window"] = v.openingPlacementTypes["Window"].index(CasementWindow)
    main.ShowSettings()
    assert main.settingsWindow.sizeFields["CasementWindow"].value() == 60
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "Casement.plan"
        assert main.SaveProject(path) and main.NewProject() and main.OpenProject(path)
        assert len(v.windows) == 2
        assert all(type(obj) is CasementWindow and obj.swingsOutwards and obj.hingeAtSecond for obj in v.windows)
        assert v.openingPlacementTypes["Window"][v.openingPlacementIndices["Window"]] is CasementWindow
        legacy = main.BuildProjectData()
        for record in legacy["scene"]["objects"]:
            if record["type"] == "CasementWindow":
                del record["hingeAtSecond"]
        assert all(not obj.hingeAtSecond for obj in DecodeProject(legacy, v.furnishingDefinitions)[1])
        del legacy["settings"]["buildSettings"]["openingSizes"]["CasementWindow"]
        assert DecodeProject(legacy, v.furnishingDefinitions)[5]["buildSettings"]["openingSizes"]["CasementWindow"] == 60
    main.close()
    restored = MainWindow()
    assert len(restored.viewport.windows) == 2
    assert all(type(obj) is CasementWindow and obj.hingeAtSecond for obj in restored.viewport.windows)
    restored.close()
    print("PASS: casement controls, facing arc, opposite measurements, clipboard and recovery.")


if __name__ == "__main__":
    Main()
