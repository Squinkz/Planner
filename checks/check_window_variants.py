"""Awning/double casement symbols and per-window wells across editing/transports."""
import copy
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Door
from planner_app.graphics.symbols import DrawOpeningSymbol
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan
from planner_app.export_bounds import AutomaticBounds
from planner_app.geometry_recovery import FindGeometryIssue


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.unitsMode = "Millimeters"
        v.snapEnabled = False
        for cls in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow):
            wall = Wall(p(-4000, 0), p(4000, 0), 240)
            opening = cls(wall, .4, .6)
            InstallScene(main, [wall, opening])
            v.SetSelection([(opening, None)])
            assert not opening.windowWell
            assert main.windowWellFields["windowWell"].isVisibleTo(main.propertiesPanel)
            assert not main.propertyFields["wellDepth"].isVisibleTo(main.propertiesPanel)
            QtWidgets.QApplication.processEvents()
            checkbox = main.windowWellFields["windowWell"]
            facing = main.doorFields["swing"]
            row = main.windowWellRows["windowWell"]
            assert row.height() == main.propertyFields["length"].height() == facing.height()
            assert row.mapTo(main.propertiesPanel, p().toPoint()).x() == facing.mapTo(main.propertiesPanel, p().toPoint()).x()
            option = QtWidgets.QStyleOptionButton()
            checkbox.initStyleOption(option)
            indicator = checkbox.style().subElementRect(QtWidgets.QStyle.SubElement.SE_CheckBoxIndicator, option, checkbox)
            center = checkbox.mapTo(main.propertiesPanel, indicator.center()).x()
            assert abs(center - facing.mapTo(main.propertiesPanel, facing.rect().center()).x()) <= 1
            gap = facing.mapTo(main.propertiesPanel, p().toPoint()).y() - row.mapTo(main.propertiesPanel, p().toPoint()).y() - row.height()
            assert gap == 8, gap
            if cls is DoubleCasementWindow:
                main.propertiesPanel.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/window-well-properties.png"))
            main.windowWellFields["windowWell"].click()
            assert opening.windowWell and main.propertyFields["wellDepth"].isVisibleTo(main.propertiesPanel)
            form = main.wallProperties.layout()
            assert form.getWidgetPosition(main.propertyFields["wellDepth"])[0] == form.getWidgetPosition(main.windowWellRows["windowWell"])[0] + 1
            v.Undo()
            assert not opening.windowWell
            v.Redo()
            assert opening.windowWell
            main.propertyFields["wellDepth"].setValue(1800)
            assert opening.wellDepth == 1800
            main.windowWellFields["wellDashed"].click()
            assert opening.wellDashed
            v.Undo()
            assert not opening.wellDashed
            v.Redo()
            assert opening.wellDashed
            for facing in (False, True):
                opening.swingsOutwards = facing
                side = 1 if facing else -1
                target = p(0, side * (120 + opening.wellDepth))
                assert v.HitTest(v.WorldToViewport(target)) == (opening, None)
                bounds = AutomaticBounds(v)
                assert QtCore.QRectF(*bounds).contains(target)
            clone = v.CloneOpening(opening, wall)
            preview = v.InactiveOpening(p(), cls, opening)
            for obj in (clone, preview):
                assert (obj.windowWell, obj.wellDepth, obj.wellDashed) == (True, 1800, True)
            # Make the facing change part of history before serializing the journal.
            opening.swingsOutwards = False
            before = v.CaptureState()
            main.EditDoorProperty("swing")
            assert opening.swingsOutwards
            v.Undo()
            assert v.CaptureState() == before
            v.Redo()
            data = main.BuildProjectData()
            decoded = DecodeProject(data, v.furnishingDefinitions)
            restored = decoded[1][0]
            assert type(restored) is cls
            assert (restored.windowWell, restored.wellDepth, restored.wellDashed, restored.swingsOutwards) == (True, 1800, True, True)
            # The real session/project round-trip must retain usable well history.
            path = folder / (cls.__name__ + ".plan")
            assert main.SaveProject(path)
            assert main.OpenProject(path)
            opening = v.windows[0]
            v.Undo()
            assert not opening.swingsOutwards and opening.windowWell
            v.Redo()
            assert opening.swingsOutwards
            v.SetSelection([(opening, None)])
            try:
                v.zoom = .5
                assert v.CopySelection()
                assert v.PasteSelection(v.WorldToViewport(p(2500, 0)))
                pasted = v.selectedWall
                assert type(pasted) is cls and pasted.windowWell and pasted.wellDepth == 1800 and pasted.wellDashed
                v.Undo()
            finally:
                QtGui.QGuiApplication.clipboard().clear()
            for format in ("png", "svg"):
                result = RenderPlan(path, 100, bounds = [-4500, -2500, 9000, 5000], projectData = data,
                                    outputFormat = format, applyTheme = False)
                assert result if format == "png" else QtSvg.QSvgRenderer(result).isValid()
            legacy = copy.deepcopy(data)
            for record in legacy["scene"]["objects"]:
                for name in ("windowWell", "wellDepth", "wellDashed"):
                    record.pop(name, None)
            assert not DecodeProject(legacy, v.furnishingDefinitions)[1][0].windowWell
            for field, value in (("wellDepth", 0), ("wellDepth", True), ("windowWell", "yes"), ("wellDashed", 1)):
                invalid = copy.deepcopy(data)
                invalid["scene"]["objects"][1][field] = value
                try:
                    DecodeProject(invalid, v.furnishingDefinitions)
                except ValueError:
                    pass
                else:
                    raise AssertionError((field, value, "invalid well property accepted"))
                if field == "wellDepth":
                    issue = FindGeometryIssue(1, invalid, v.furnishingDefinitions)
                    assert issue["code"] == "dimensions" and issue["repair"]["wellDepth"] == 600
        # Each new type can be placed at its own default size and flipped without a hinge action.
        wall = Wall(p(-4000, 0), p(4000, 0), 240)
        for cls in (AwningWindow, DoubleCasementWindow):
            InstallScene(main, [wall])
            opening = v.PlaceWindow(v.WorldToViewport(p()), openingType = cls)
            assert type(opening) is cls and abs(opening.length - 1200) < 1e-6
            assert main.doorProperties.layout().isRowVisible(main.doorFields["swing"])
            assert not main.doorProperties.layout().isRowVisible(main.doorFields["hinge"])
            v.OrientDoor(opening, v.WorldToViewport(p(0, 1000)))
            assert opening.swingsOutwards
            # Native drag/drop uses the new MIME type and creates the right class.
            InstallScene(main, [wall])
            kind = "awning-window" if cls is AwningWindow else "double-casement-window"
            mime = QtCore.QMimeData()
            mime.setData("application/x-planner-" + kind, kind.encode())
            position = v.WorldToViewport(p())
            enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                          QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
            QtWidgets.QApplication.sendEvent(v, enter)
            assert enter.isAccepted()
            move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
            QtWidgets.QApplication.sendEvent(v, move)
            assert move.isAccepted() and type(v.windowDropPreview) is cls
            drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
                                    QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
            QtWidgets.QApplication.sendEvent(v, drop)
            assert drop.isAccepted() and type(v.windows[0]) is cls
            # Multi-selection applies one well state and one depth to both windows.
            first, second = cls(wall, .2, .35), cls(wall, .65, .8)
            InstallScene(main, [wall, first, second])
            first.windowWell = True
            v.SetSelection([(first, None), (second, None)])
            assert main.windowWellFields["windowWell"].checkState() == QtCore.Qt.CheckState.PartiallyChecked
            main.windowWellFields["windowWell"].click()
            assert first.windowWell and second.windowWell
            main.propertyFields["wellDepth"].setValue(900)
            assert first.wellDepth == second.wellDepth == 900
            v.Undo()
            assert first.wellDepth == second.wellDepth == 600
        InstallScene(main, [wall, Door(wall, .4, .6)])
        v.SetSelection([(v.windows[0], None)])
        assert not main.windowWellFields["windowWell"].isVisibleTo(main.propertiesPanel)

        class SymbolPainter(QtGui.QPainter):
            def drawLine(self, line):
                lines.append(line)
                super().drawLine(line)

            def drawPath(self, path):
                paths.append(path)
                super().drawPath(path)

            def drawPolyline(self, polygon):
                polylines.append((polygon, self.pen().style()))
                super().drawPolyline(polygon)

        image = QtGui.QImage(400, 300, QtGui.QImage.Format.Format_ARGB32)
        for cls in (AwningWindow, DoubleCasementWindow):
            for facing in (False, True):
                lines, paths, polylines = [], [], []
                image.fill(QtCore.Qt.GlobalColor.transparent)
                with SymbolPainter(image) as painter:
                    DrawOpeningSymbol(painter, p(80, 160), p(320, 160), 40, cls,
                                      swingsOutwards = facing, color = "white")
                if cls is AwningWindow:
                    assert len(polylines) == 1 and polylines[0][1] == QtCore.Qt.PenStyle.DashLine
                    assert polylines[0][0].boundingRect().left() == 80 and polylines[0][0].boundingRect().right() == 320
                    assert not paths
                else:
                    assert len(paths) == 2 and not polylines
                    leaves = [line for line in lines if abs(line.dx()) > .001 and abs(line.dy()) > .001]
                    assert len(leaves) == 2 and all(abs(line.length() - 120) < 1e-6 for line in leaves)
                    assert leaves[0].dx() == -leaves[1].dx()
                    assert not any(abs(line.x1() - 200) < .001 and abs(line.dx()) < .001 for line in lines)
        # Save a visual specimen for review, without modifying any help illustrations.
        image.save(str(folder / "double-casement.png"))
    print("Windows: well controls/history/clipboard/project/legacy/export, new placement/facing and exact symbol geometry passed")


if __name__ == "__main__":
    Main()
