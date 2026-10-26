"""Boundary annotations: dash-dot artwork, selected-only dimensions and normal editing."""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch
import xml.etree.ElementTree as ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from fixtures.parity_examples import ExampleWindow
from planner_app.models import BoundaryLine, Wall
from planner_app.project_codec import DecodeProject
from planner_app.project_recovery import RecoverProject
from planner_app.export_plan import RenderPlan
from planner_app.viewport import rendering
from planner_app.graphics.palette import themeColors
from check_history import Drag


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        point = QtCore.QPointF
        v.showTips = v.showGrid = v.showMeasurements = v.snapEnabled = False
        v.unitsMode = "Meters"
        assert not main.boundaryLineButton.icon().isNull()
        mime = QtCore.QMimeData()
        mime.setData("application/x-planner-boundary-line", b"boundary-line")
        position = v.WorldToViewport(point())
        enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                     QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, enter)
        move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                   QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, move)
        assert enter.isAccepted() and type(v.arrowPreview) is BoundaryLine
        v.grab()
        drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
                               QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, drop)
        assert drop.isAccepted() and type(v.walls[0]) is BoundaryLine
        boundary = v.walls[0]
        assert boundary.width == 0 and "Boundary line" in main.selectionLabel.text()
        assert v.ObjectVisibilityCategory(boundary) == "Boundary lines"
        assert main.arrowFields["length"].isVisible() and not main.arrowFields["width"].isVisible()
        v.SetSelection([])
        v.hoverPosition = None
        v.measurementPictures = ()
        with patch.object(rendering, "FormatLength", wraps = rendering.FormatLength) as formatLength:
            image = v.grab().toImage()
            assert formatLength.call_count == 0, "Unselected boundary displayed a measurement"
        background = QtGui.QColor(themeColors["canvas"])
        first = v.WorldToViewport(boundary.firstVertex) * image.devicePixelRatioF()
        second = v.WorldToViewport(boundary.secondVertex) * image.devicePixelRatioF()
        ink = [any(image.pixelColor(x, round(first.y()) + offset) != background for offset in range(-2, 3))
               for x in range(round(first.x()) + 5, round(second.x()) - 5)]
        assert any(ink) and not all(ink), "Boundary stroke is missing or solid"
        assert v.HitTest(v.WorldToViewport(point(-250, 0)))[0] is boundary
        v.SetSelection([(boundary, None)])
        v.measurementPictures = ()
        v.sceneMeasurements = None
        with patch.object(rendering, "FormatLength", wraps = rendering.FormatLength) as formatLength:
            v.grab()
            assert any(call.args[0] == 1000 for call in formatLength.call_args_list), "Selected boundary has no dimension"
        endpoint = point(boundary.secondVertex)
        Drag(v, v.WorldToViewport(endpoint).toPoint(), v.WorldToViewport(endpoint + point(0, 500)).toPoint())
        assert QtCore.QLineF(boundary.secondVertex, endpoint + point(0, 500)).length() < 10
        v.Undo()
        assert boundary.secondVertex == endpoint
        main.EditArrowProperty("length", 2)
        assert QtCore.QLineF(boundary.firstVertex, boundary.secondVertex).length() == 2000
        v.Undo()
        assert QtCore.QLineF(boundary.firstVertex, boundary.secondVertex).length() == 1000
        before = v.CaptureState()
        boundary.textOffset = point(0, 300)
        v.RecordEdit(before)
        labelPosition = v.MeasurementLabelLayout(boundary)[0]
        assert v.HitTest(labelPosition) == (boundary, None)
        v.SetSelection([])
        assert v.HitTest(labelPosition)[0] is None, "Invisible dimension label remained clickable"
        assert not v.ObjectsOverlap(boundary, Wall(point(-1000, 0), point(1000, 0)))
        v.SetSelection([(boundary, None)])
        assert v.CopySelection() and v.ReadClipboardSelection()["objects"][0]["type"] == "BoundaryLine"
        assert v.PasteSelection(v.WorldToViewport(point(0, 1000)))
        assert len(v.walls) == 2 and all(type(obj) is BoundaryLine for obj in v.walls)
        data = main.BuildProjectData()
        decoded, notices = RecoverProject(data, v.furnishingDefinitions, main.defaultProjectData)
        assert not notices and all(type(obj) is BoundaryLine for obj in decoded[0]), notices
        assert decoded[0][0].textOffset == point(0, 300)
        legacy = copy.deepcopy(data)
        del legacy["settings"]["visibility"]["Boundary lines"]
        assert DecodeProject(legacy, v.furnishingDefinitions)[5]["visibility"]["Boundary lines"]
        project = Path(folder) / "boundary.plan"
        assert main.SaveProject(project) and main.OpenProject(project)
        assert len(v.walls) == 2 and all(type(obj) is BoundaryLine for obj in v.walls)
        v.Undo()
        assert len(v.walls) == 1
        v.Redo()
        assert len(v.walls) == 2
        for solid in (True, False):
            for output in ("png", "svg"):
                exportData = main.BuildProjectData(includeHistory = False)
                result = RenderPlan("boundary.plan", 200, bounds = (-1500, -1000, 3000, 3000),
                                    projectData = exportData, outputFormat = output, applyTheme = False,
                                    furnishingDefinitions = v.furnishingDefinitions, solidObjects = solid)
                if output == "svg":
                    root = ElementTree.fromstring(result)
                    assert any("stroke-dasharray" in element.attrib for element in root.iter()), "Vector export lost dash-dot strokes"
                    assert not any(element.tag.rsplit("}", 1)[-1] == "text" for element in root.iter()), "Boundary exported a dimension"
                else:
                    assert not result.isNull()
        v.visibility["Boundary lines"] = False
        assert all(not v.IsObjectVisible(obj) for obj in v.walls)
        QtWidgets.QApplication.clipboard().clear()
        QtWidgets.QApplication.processEvents()
    print("Boundary lines: placement, dash-dot rendering, selected dimensions, endpoint edits, label hit area, history, clipboard, recovery and PNG/SVG passed")


if __name__ == "__main__":
    Main()
