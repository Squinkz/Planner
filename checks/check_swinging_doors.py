"""Double-acting doors have one hinge side, two swings and no facing state."""
import copy
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, SwingingDoor
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
        opening = v.PlaceWindow(v.WorldToViewport(p()), openingType = SwingingDoor)
        assert type(opening) is SwingingDoor and abs(opening.length - 900) < 1e-6
        assert not hasattr(opening, "swingsOutwards")
        assert main.selectionLabel.text().startswith("Swinging Door")
        assert not main.doorProperties.layout().isRowVisible(main.doorFields["swing"])
        assert main.doorProperties.layout().isRowVisible(main.doorFields["hinge"])
        assert not main.doorProperties.layout().isRowVisible(main.doorFields["measurement"])
        assert not main.windowWellFields["windowWell"].isVisibleTo(main.propertiesPanel)
        main.EditDoorProperty("hinge")
        assert opening.hingeAtSecond
        v.Undo()
        assert not opening.hingeAtSecond
        v.Redo()
        assert opening.hingeAtSecond
        before = v.CaptureState()
        main.EditDoorProperty("swing")
        assert v.CaptureState() == before and not hasattr(opening, "swingsOutwards")
        for x, y in ((-500, -500), (500, -500), (-500, 500), (500, 500)):
            v.OrientDoor(opening, v.WorldToViewport(p(x, y)))
            assert opening.hingeAtSecond == (x > 0) and not hasattr(opening, "swingsOutwards")
        assert v.CloneOpening(opening, wall).hingeAtSecond
        assert v.InactiveOpening(p(), SwingingDoor, opening).hingeAtSecond
        v.visibility["Doors"] = False
        assert not v.IsObjectVisible(opening)
        v.visibility["Doors"] = True
        assert v.IsObjectVisible(opening)
        for mode in (0, 1, 2):
            v.measurementSettings["doors"] = mode
            v.measurementSettings["windows"] = 2
            spans = v.WallDimensions([wall], v.ConnectedWallPath([wall]))
            for side in (-1, 1):
                assert len([span for span in spans if ((span[0] + span[1]) / 2).y() * side > 0]) == (1 if mode == 2 else 3)
        before = v.CaptureState()
        main.EditDoorProperty("hinge")
        changed = opening.hingeAtSecond
        data = main.BuildProjectData()
        record = data["scene"]["objects"][1]
        assert record["type"] == "SwingingDoor" and "swingsOutwards" not in record
        restored = DecodeProject(data, v.furnishingDefinitions)[1][0]
        assert type(restored) is SwingingDoor and restored.hingeAtSecond == changed
        legacy = copy.deepcopy(data)
        del legacy["settings"]["buildSettings"]["openingSizes"]["SwingingDoor"]
        assert DecodeProject(legacy, v.furnishingDefinitions)[5]["buildSettings"]["openingSizes"]["SwingingDoor"] == 90
        path = folder / "Swinging.plan"
        assert main.SaveProject(path) and main.OpenProject(path)
        opening = v.windows[0]
        v.Undo()
        assert v.CaptureState()[3][0][4] == before[3][0][4]
        v.Redo()
        assert opening.hingeAtSecond == changed
        v.SetSelection([(opening, None)])
        try:
            assert v.CopySelection() and v.PasteSelection(v.WorldToViewport(p(2500, 0)))
            assert type(v.selectedWall) is SwingingDoor and v.selectedWall.hingeAtSecond == changed
            assert not hasattr(v.selectedWall, "swingsOutwards")
            v.Undo()
        finally:
            QtGui.QGuiApplication.clipboard().clear()
        for format in ("png", "svg"):
            output = RenderPlan(path, 100, bounds = [-4500, -2000, 9000, 4000], projectData = data,
                                outputFormat = format, applyTheme = False)
            assert output if format == "png" else QtSvg.QSvgRenderer(output).isValid()
        InstallScene(main, [wall])
        mime = QtCore.QMimeData()
        mime.setData("application/x-planner-swinging-door", b"swinging-door")
        position = v.WorldToViewport(p())
        enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                      QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, enter)
        assert enter.isAccepted()
        move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                    QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, move)
        assert move.isAccepted() and type(v.windowDropPreview) is SwingingDoor
        drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
                                QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, drop)
        assert drop.isAccepted() and type(v.windows[0]) is SwingingDoor

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
            for hinge in (False, True):
                image.fill(QtCore.Qt.GlobalColor.transparent)
                arcs, lines = [], []
                with SymbolPainter(image) as painter:
                    DrawOpeningSymbol(painter, first, second, 40, SwingingDoor, hingeAtSecond = hinge, color = "white")
                assert len(arcs) == 2 and len(lines) == 4
                center = second if hinge else first
                tips = [arc.currentPosition() for arc in arcs]
                assert all(abs(line.length() - 200) < 1e-6 for line in (lines[2], lines[3]))
                assert (tips[0] - center) == -(tips[1] - center)
                assert all(QtCore.QLineF(tip, line.p2()).length() < .001 for tip, line in zip(tips, lines[2:]))
    print("Swinging doors: two opposed swings, hinge-only controls, measurements, placement, history, clipboard and exports passed")


if __name__ == "__main__":
    Main()
