"""Paired standard door leaves share a facing, without a center jamb or hinge control."""
import copy
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Door, DoubleDoor
from planner_app.graphics.symbols import DrawOpeningSymbol
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.snapEnabled = False
        v.zoom = .5
        wall = Wall(p(-4000, 0), p(4000, 0), 240)
        InstallScene(main, [wall])
        opening = v.PlaceWindow(v.WorldToViewport(p()), openingType = DoubleDoor)
        assert type(opening) is DoubleDoor and abs(opening.length - 1800) < 1e-6
        assert not hasattr(opening, "hingeAtSecond")
        assert main.selectionLabel.text().startswith("Double Door")
        assert main.doorProperties.layout().isRowVisible(main.doorFields["swing"])
        assert not main.doorProperties.layout().isRowVisible(main.doorFields["hinge"])
        main.EditDoorProperty("swing")
        assert opening.swingsOutwards
        v.Undo()
        assert not opening.swingsOutwards
        v.Redo()
        assert opening.swingsOutwards
        before = v.CaptureState()
        main.EditDoorProperty("hinge")
        assert v.CaptureState() == before
        for x, y in ((-500, -500), (500, -500), (-500, 500), (500, 500)):
            v.OrientDoor(opening, v.WorldToViewport(p(x, y)))
            assert opening.swingsOutwards == (y < 0) and not hasattr(opening, "hingeAtSecond")
        assert not v.CloneOpening(opening, wall).swingsOutwards
        assert not v.InactiveOpening(p(), DoubleDoor, opening).swingsOutwards
        v.visibility["Doors"] = False
        assert not v.IsObjectVisible(opening)
        v.visibility["Doors"] = True
        # Measurement cuts match a standard door of the same overall span.
        v.SetSelection([])
        for facing in (False, True):
            for mode in (0, 1, 2):
                v.measurementSettings["doors"], v.measurementSettings["windows"] = mode, 2
                results = []
                for cls in (DoubleDoor, Door):
                    obj = cls(wall, opening.firstFraction, opening.secondFraction)
                    obj.swingsOutwards = facing
                    v.windows = [obj]
                    spans = v.WallDimensions([wall], v.ConnectedWallPath([wall]))
                    results.append([(first, second) for first, second, owners in spans])
                assert results[0] == results[1], (facing, mode)
        InstallScene(main, [wall, opening])
        v.SetSelection([(opening, None)])
        main.EditDoorProperty("swing")
        data = main.BuildProjectData()
        record = data["scene"]["objects"][1]
        assert record["type"] == "DoubleDoor" and "hingeAtSecond" not in record
        assert DecodeProject(data, v.furnishingDefinitions)[1][0].swingsOutwards
        legacy = copy.deepcopy(data)
        del legacy["settings"]["buildSettings"]["openingSizes"]["DoubleDoor"]
        assert DecodeProject(legacy, v.furnishingDefinitions)[5]["buildSettings"]["openingSizes"]["DoubleDoor"] == 180
        path = folder / "Double.plan"
        assert main.SaveProject(path) and main.OpenProject(path)
        opening = v.windows[0]
        v.Undo()
        assert not opening.swingsOutwards
        v.Redo()
        assert opening.swingsOutwards
        v.SetSelection([(opening, None)])
        try:
            assert v.CopySelection() and v.PasteSelection(v.WorldToViewport(p(2500, 0)))
            assert type(v.selectedWall) is DoubleDoor and v.selectedWall.swingsOutwards
            v.Undo()
        finally:
            QtGui.QGuiApplication.clipboard().clear()
        for format in ("png", "svg"):
            output = RenderPlan(path, 100, bounds = [-4500, -2000, 9000, 4000], projectData = data,
                                outputFormat = format, applyTheme = False)
            assert output if format == "png" else QtSvg.QSvgRenderer(output).isValid()
        InstallScene(main, [wall])
        mime = QtCore.QMimeData()
        mime.setData("application/x-planner-double-door", b"double-door")
        position = v.WorldToViewport(p())
        enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                      QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, enter)
        assert enter.isAccepted()
        move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                    QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, move)
        assert move.isAccepted() and type(v.windowDropPreview) is DoubleDoor
        drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
                                QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, drop)
        assert drop.isAccepted() and type(v.windows[0]) is DoubleDoor

        class SymbolPainter(QtGui.QPainter):
            def drawPath(self, path):
                arcs.append(path)
                super().drawPath(path)

            def drawLine(self, line):
                lines.append(line)
                super().drawLine(line)

        image = QtGui.QImage(500, 500, QtGui.QImage.Format.Format_ARGB32)
        for vertical in (False, True):
            first, second = (p(250, 150), p(250, 350)) if vertical else (p(150, 250), p(350, 250))
            tangent = (second - first) / 200
            for facing in (False, True):
                image.fill(QtCore.Qt.GlobalColor.transparent)
                arcs, lines = [], []
                with SymbolPainter(image) as painter:
                    DrawOpeningSymbol(painter, first, second, 40, DoubleDoor, swingsOutwards = facing, color = "white")
                assert len(arcs) == 2 and len(lines) == 4
                # Each swing is a standard half-span leaf, with the same facing.
                assert all(abs(line.length() - 100) < 1e-6 for line in lines[2:])
                assert lines[2].p2() - lines[2].p1() == lines[3].p2() - lines[3].p1()
                assert arcs[0].pointAtPercent(0) == arcs[1].pointAtPercent(0)
                for endpoint, jamb in zip((first, second), lines[:2]):
                    assert (jamb.p1() + jamb.p2()) / 2 == endpoint
                assert abs(QtCore.QPointF.dotProduct(lines[2].p1() - first, tangent)) < 1e-6
                assert abs(QtCore.QPointF.dotProduct(lines[3].p1() - second, tangent)) < 1e-6
                assert all(QtCore.QLineF(arc.currentPosition(), line.p2()).length() < .001 for arc, line in zip(arcs, lines[2:]))
    print("Double doors: opposing half-span leaves, outer jambs only, shared facing, measurement cuts, history, clipboard and exports passed")


if __name__ == "__main__":
    Main()
