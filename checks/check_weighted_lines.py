"""Dashed/solid boundary-style lines inherit class linework across all transports."""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch
import xml.etree.ElementTree as ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtSvg
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import DashedLine, SolidLine, Wall, lineWeightClasses
from planner_app.project_codec import DecodeProject
from planner_app.project_recovery import RecoverProject
from planner_app.export_plan import RenderPlan
from planner_app.viewport import rendering
from check_history import Drag
from check_scene_render_cache import CompareDirect


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.showTips = v.showGrid = v.showMeasurements = v.snapEnabled = False
        for cls, mimeName in ((DashedLine, "dashed-line"), (SolidLine, "solid-line")):
            InstallScene(main, [])
            position = v.WorldToViewport(p())
            mime = QtCore.QMimeData()
            mime.setData("application/x-planner-" + mimeName, mimeName.encode())
            enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                          QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
            QtWidgets.QApplication.sendEvent(v, enter)
            move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
            QtWidgets.QApplication.sendEvent(v, move)
            assert type(v.arrowPreview) is cls
            drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
                                    QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
            v.dropEvent(drop)
            line = v.walls[0]
            assert type(line) is cls and line.weightClass == "Objects" and line.width == 0
            assert main.lineWeightField.isVisibleTo(main.propertiesPanel)
            assert [main.lineWeightField.itemText(index) for index in range(main.lineWeightField.count())] == ["Walls", "Objects", "Furnishings", "Dimensions"]
            assert [main.lineWeightField.itemData(index) for index in range(main.lineWeightField.count())] == list(lineWeightClasses)
            form = main.arrowProperties.layout()
            assert form.getWidgetPosition(main.lineWeightField)[0] == form.getWidgetPosition(main.arrowFields["length"])[0] + 1
            wall = Wall(p(-1500, 0), p(1500, 0), 400)
            v.walls.append(wall)
            v.SetSelection([(wall, None)])
            assert v.HitTest(v.WorldToViewport((line.firstVertex + line.secondVertex) / 2))[0] is line
            v.walls.remove(wall)
            for weight, (colorRole, widthRole) in lineWeightClasses.items():
                v.SetSelection([(line, None)])
                main.lineWeightField.setCurrentIndex(main.lineWeightField.findData(weight))
                assert line.weightClass == weight
                v.SetSelection([])
                with patch.object(rendering, "LinePen", wraps = rendering.LinePen) as pen:
                    v.viewportSceneKey = None
                    v.grab()
                style = QtCore.Qt.PenStyle.SolidLine if cls is SolidLine else QtCore.Qt.PenStyle.DashLine
                assert any(call.args[:3] == (rendering.themeColors[colorRole], v.lineWidths[widthRole], style) for call in pen.call_args_list), (cls, weight)
                CompareDirect(v)
            v.SetSelection([(line, None)])
            main.lineWeightField.setCurrentText("Walls")
            v.Undo()
            assert line.weightClass == "Measurements"
            v.Redo()
            assert line.weightClass == "Walls"
            endpoint = p(line.secondVertex)
            Drag(v, v.WorldToViewport(endpoint).toPoint(), v.WorldToViewport(endpoint + p(0, 300)).toPoint())
            assert line.secondVertex != endpoint
            v.Undo()
            assert line.secondVertex == endpoint and line.weightClass == "Walls"
            assert not v.ObjectsOverlap(line, Wall(p(-1000, 0), p(1000, 0)))
            try:
                assert v.CopySelection() and v.ReadClipboardSelection()["objects"][0]["weightClass"] == "Walls"
                assert v.PasteSelection(v.WorldToViewport(p(0, 1000)))
                assert type(v.selectedWall) is cls and v.selectedWall.weightClass == "Walls"
                v.Undo()
                copies = v.DuplicateSelectionObjects([line], [])
                assert copies[id(line)].weightClass == "Walls"
                v.walls = [line]
                v.undoHistory, v.redoHistory = [], []
                v.SetSelection([(line, None)])
                main.lineWeightField.setCurrentText("Furnishings")
                path = folder / f"{mimeName}.plan"
                assert main.SaveProject(path) and main.OpenProject(path)
                line = v.walls[0]
                assert type(line) is cls and line.weightClass == "Furnishings"
                v.Undo()
                assert line.weightClass == "Walls"
                v.Redo()
                assert line.weightClass == "Furnishings"
                data = main.BuildProjectData()
                decoded, notices = RecoverProject(data, v.furnishingDefinitions, main.defaultProjectData)
                assert not notices and decoded[0][0].weightClass == "Furnishings", notices
                invalid = copy.deepcopy(data)
                invalid["scene"]["objects"][0]["weightClass"] = "invalid"
                try:
                    DecodeProject(invalid, v.furnishingDefinitions)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Invalid weight was accepted")
                for format in ("png", "svg"):
                    result = RenderPlan(path, 200, bounds = [-1500, -1000, 3000, 2000], projectData = data,
                                        outputFormat = format, applyTheme = False)
                    if format == "svg":
                        assert QtSvg.QSvgRenderer(result).isValid()
                        root = ElementTree.fromstring(result)
                        dashed = any("stroke-dasharray" in element.attrib for element in root.iter())
                        assert dashed == (cls is DashedLine)
                        assert not any(element.tag.rsplit("}", 1)[-1] == "text" for element in root.iter())
                    else:
                        assert not result.isNull()
                category = "Solid lines" if cls is SolidLine else "Dashed lines"
                v.visibility[category] = False
                assert not v.IsObjectVisible(line)
                v.visibility[category] = True
            finally:
                QtGui.QGuiApplication.clipboard().clear()
    print("PASS: weighted line placement, styles, editing, history, clipboard, recovery and PNG/SVG export")


if __name__ == "__main__":
    Main()
