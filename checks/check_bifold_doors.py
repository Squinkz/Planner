"""Bifold opening size, folded geometry, orientation and persistence."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, BifoldDoor, DrawOpeningSymbol


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.unitsMode = "Adaptive Metric"  # Assertions below use meters/centimeters.
    v.snapEnabled = False
    point = QtCore.QPointF
    wall = Wall(point(-4000, 0), point(4000, 0))
    v.walls = [wall]
    door = v.PlaceWindow(v.WorldToViewport(point()), openingType = BifoldDoor)
    assert abs(door.length - 1200) < .001 and not hasattr(door, "hingeAtSecond")
    assert main.selectionLabel.text().startswith("Bifold Door")
    assert main.propertyFields["length"].value() == 1.2
    assert main.doorProperties.layout().isRowVisible(main.doorFields["swing"])
    assert not main.doorProperties.layout().isRowVisible(main.doorFields["hinge"])
    main.EditDoorProperty("swing")
    assert door.swingsOutwards
    v.Undo()
    assert not door.swingsOutwards
    v.Redo()
    assert door.swingsOutwards
    for x, y in ((-500, -500), (500, -500), (-500, 500), (500, 500)):
        v.OrientDoor(door, v.WorldToViewport(point(x, y)))
        assert door.swingsOutwards == (y < 0)
    clone = v.CloneOpening(door, wall)
    assert clone.swingsOutwards == door.swingsOutwards

    class PanelPainter(QtGui.QPainter):
        def drawPolygon(self, polygon):
            panels.append(list(polygon))
            super().drawPolygon(polygon)

    image = QtGui.QImage(420, 260, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtGui.QColor("#0e0e0e"))
    for facing in (False, True):
        panels = []
        painter = PanelPainter(image)
        DrawOpeningSymbol(painter, point(30, 130), point(390, 130), 40, BifoldDoor,
                          swingsOutwards = facing, color = "#ffffff", pixelsPerMillimeter = .3)
        painter.end()
        assert len(panels) == 4
        for first, second in ((panels[0], panels[1]), (panels[2], panels[3])):
            assert first[1] == second[0]
            firstPath, secondPath = QtGui.QPainterPath(), QtGui.QPainterPath()
            firstPath.addPolygon(QtGui.QPolygonF(first))
            secondPath.addPolygon(QtGui.QPolygonF(second))
            assert firstPath.intersected(secondPath).isEmpty()
        for panel in panels:
            start, end = (panel[0] + panel[3]) / 2, (panel[1] + panel[2]) / 2
            axis = end - start
            assert abs(abs(axis.x()) - abs(axis.y())) < .001
            assert abs((axis.x() ** 2 + axis.y() ** 2) ** .5 - 90) < .001
            assert ((start.y() + end.y()) / 2 > 130) == facing
    image.save(str(Path(__file__).resolve().parent.parent / "screenshots" / "bifold-door.png"))
    for mode in (0, 1, 2):
        v.measurementSettings["doors"] = mode
        for facing in (False, True):
            door.swingsOutwards = facing
            spans = v.WallDimensions([wall], v.ConnectedWallPath([wall]))
            for side in (-1, 1):
                assert len([span for span in spans if ((span[0] + span[1]) / 2).y() * side > 0]) == (1 if mode == 2 else 3)
    v.SetSelection([(door, None)])
    try:
        assert v.CopySelection()
        v.zoom = .5
        assert v.PasteSelection(v.WorldToViewport(point(2700, 0)))
        assert isinstance(v.selectedWall, BifoldDoor) and v.selectedWall.swingsOutwards
    finally:
        app.clipboard().clear()
        app.processEvents()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "Bifold.plan"
        assert main.SaveProject(path) and main.NewProject() and main.OpenProject(path)
        assert len(v.windows) == 2
        assert all(isinstance(obj, BifoldDoor) and obj.swingsOutwards for obj in v.windows)
    main.close()
    restored = MainWindow()
    assert len(restored.viewport.windows) == 2
    assert all(isinstance(obj, BifoldDoor) for obj in restored.viewport.windows)
    restored.close()
    print("PASS: bifold size, swing-only controls, four 45-degree leaves, history, clipboard and persistence.")


if __name__ == "__main__":
    Main()
