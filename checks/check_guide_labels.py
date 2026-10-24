"""Linear and angular guide label dragging, reset, persistence and independent geometry."""
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from planner import MainWindow
from planner_app.models import MeasurementGuide, AngleGuide, ObjectControlPoints
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan
from planner_app.export_bounds import AutomaticBounds
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    for units in ("Millimeters", "Feet and Inches"):
        for cls in (MeasurementGuide, AngleGuide):
            assert main.NewProject()
            v.unitsMode = units
            v.snapEnabled = v.connectedEnabled = False
            guide = cls(point(-900, 0), point(900, 600)) if cls is MeasurementGuide else cls(point(900, 0), point(0, 900), middleVertex = point())
            before = v.CaptureState()
            v.walls = [guide]
            v.SetSelection([(guide, None)])
            v.RecordEdit(before)
            vertices = tuple(point(vertex) for vertex in ObjectControlPoints(guide))
            center = v.MeasurementLabelLayout(guide)[0] if cls is MeasurementGuide else v.AngleLayout(guide)[1].center()
            assert v.HitTest(center) == (guide, 3)
            Drag(v, center.toPoint(), (center + point(110, -70)).toPoint())
            moved = point(guide.textOffset)
            assert not moved.isNull() and ObjectControlPoints(guide) == vertices
            newCenter = v.MeasurementLabelLayout(guide)[0] if cls is MeasurementGuide else v.AngleLayout(guide)[1].center()
            assert QtCore.QLineF(newCenter, center + point(110, -70)).length() < 2
            assert v.HitTest(newCenter) == (guide, 3)
            v.Undo()
            assert guide.textOffset.isNull() and ObjectControlPoints(guide) == vertices
            v.Redo()
            assert guide.textOffset == moved
            # Double click resets the label, with a separate reversible edit.
            QtTest.QTest.mouseDClick(v, QtCore.Qt.MouseButton.LeftButton, pos = newCenter.toPoint())
            assert guide.textOffset.isNull() and ObjectControlPoints(guide) == vertices
            v.Undo()
            assert guide.textOffset == moved
            v.Redo()
            assert guide.textOffset.isNull()
            historyCount = len(v.undoHistory)
            defaultCenter = v.MeasurementLabelLayout(guide)[0] if cls is MeasurementGuide else v.AngleLayout(guide)[1].center()
            camera = v.zoom, point(v.panOffset)
            QtTest.QTest.mouseDClick(v, QtCore.Qt.MouseButton.LeftButton, pos = defaultCenter.toPoint())
            assert len(v.undoHistory) == historyCount and (v.zoom, v.panOffset) == camera
            v.Undo()
            # Cancel restores label placement without moving any control point.
            center = v.MeasurementLabelLayout(guide)[0] if cls is MeasurementGuide else v.AngleLayout(guide)[1].center()
            QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = center.toPoint())
            v.UpdateInteraction(center + point(-70, 40), QtCore.Qt.KeyboardModifier.NoModifier)
            assert guide.textOffset != moved
            v.CancelInteraction()
            assert guide.textOffset == moved and ObjectControlPoints(guide) == vertices
            v.SetSelection([(guide, None)])
            if cls is MeasurementGuide:
                middle = v.WorldToViewport((guide.firstVertex + guide.secondVertex) / 2)
                assert v.HitTest(middle + (center - middle) * .5)[0] is guide, "The visible label leader must remain selectable"
            assert v.CopySelection() and v.PasteSelection(v.WorldToViewport(point(-1800, -1400)))
            copy = v.walls[-1]
            assert copy is not guide and type(copy) is cls and copy.textOffset == moved
            v.Undo()
            v.SetSelection([(guide, 3)])
            v.NudgeSelection(QtCore.Qt.Key.Key_Right)
            assert guide.textOffset != moved and ObjectControlPoints(guide) == vertices
            v.Undo()
            assert guide.textOffset == moved
            # Old linear-guide records omit the offset and retain their centred label.
            data = main.BuildProjectData()
            decoded = DecodeProject(data, v.furnishingDefinitions)
            assert decoded[0][0].textOffset == moved
            if cls is MeasurementGuide:
                record = data["scene"]["objects"][0]
                record.pop("textOffset")
                assert DecodeProject(data, v.furnishingDefinitions)[0][0].textOffset.isNull()
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "Labels.plan"
                assert main.SaveProject(path) and main.NewProject() and main.OpenProject(path)
                guide = v.walls[0]
                assert guide.textOffset == moved and ObjectControlPoints(guide) == vertices
                center = v.MeasurementLabelLayout(guide)[0] if cls is MeasurementGuide else v.AngleLayout(guide)[1].center()
                QtTest.QTest.mouseDClick(v, QtCore.Qt.MouseButton.LeftButton, pos = center.toPoint())
                assert guide.textOffset.isNull()
                v.Undo()
                assert guide.textOffset == moved
            # Offscreen labels participate in automatic crops and vector/raster export.
            originalOffset = point(guide.textOffset)
            guide.textOffset = point(20000, 18000)
            x, y, width, height = AutomaticBounds(v)
            assert x + width > 18000 and y + height > 16000
            guide.textOffset = originalOffset
            data = main.BuildProjectData()
            image = RenderPlan("Labels.plan", 200, (-2500, -2000, 6000, 5000), projectData = data, applyTheme = False)
            svg = RenderPlan("Labels.plan", 200, (-2500, -2000, 6000, 5000), projectData = data, applyTheme = False, outputFormat = "svg")
            assert not image.isNull() and b"<svg" in svg
            if cls is MeasurementGuide and units == "Feet and Inches":
                image.save(str(root / "diagnostics/measurement-guide-label-export.png"))
                main.grab().save(str(root / "diagnostics/measurement-guide-label.png"))
            app.clipboard().clear()
    main.MarkProjectClean()
    main.close()
    print("PASS: linear/angular label drag and double-click reset, geometry isolation, cancel, undo, clipboard, legacy records, save/load and export")


if __name__ == "__main__":
    Main()
