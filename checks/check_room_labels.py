"""Live centered room names/areas, native placement and geometry-safe transports."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets, QtTest
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import RoomLabel, Label, Door, Furnishing
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan
from planner_app.export_scene import PrepareExportScene
from planner_app.units import FormatArea
from planner_app.viewport.widget import DrawingViewport
from check_room_detection import Rectangle
from check_scene_render_cache import CompareDirect as CompareScene
from check_pan_dpi import CompareDirect as ComparePan
from planner_app.viewport.rendering import RenderingMixin


def Main():
    p = QtCore.QPointF
    assert FormatArea(14440000, "Adaptive Metric") == "14.44 m²"
    assert FormatArea(14440000, "Meters") == "14.44 m²"
    assert FormatArea(14440000, "Centimeters") == "144,400 cm²"
    assert FormatArea(14440000, "Millimeters") == "14,440,000 mm²"
    assert FormatArea(14440000, "Feet and Inches") == "155.43 ft²"
    assert FormatArea(25.4 ** 2, "Inches") == "1 in²"
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.snapEnabled = False
        v.unitsMode = "Meters"
        v.zoom = .5
        walls = Rectangle(-2000, -2000, 4000, 4000)
        label = RoomLabel(p(), "STUDY")
        InstallScene(main, walls + [label])
        v.roomDetection.Refresh(force = True)
        assert label.areaSquareMillimeters == 14440000
        v.windows = [Door(walls[0], .3, .5)]
        v.roomDetection.Refresh(force = True)
        assert label.areaSquareMillimeters == 14440000
        v.windows = []
        assert (label.firstVertex + label.secondVertex) / 2 == p()
        assert label.TextLayout()[4][-1][0] == "14.44 m²"
        assert label.TextLayout()[4][-1][2].pointSizeF() < label.TextLayout()[0].pointSizeF()
        for text, position, font in label.TextLayout()[4]:
            assert abs(position.x() + QtGui.QFontMetricsF(font).horizontalAdvance(text) / 2) < 1e-8
        v.SetSelection([(label, None)])
        assert main.selectionLabel.text().startswith("Room Label")
        assert main.labelProperties.layout().labelForField(main.roomNameField).text() == "Name"
        assert isinstance(main.roomNameField, QtWidgets.QLineEdit) and main.labelTextField.isHidden()
        assert main.roomAreaValue.text() == "14.44 m²"
        assert main.roomUnitsField.currentText() == "Project"
        QtWidgets.QApplication.processEvents()
        assert main.roomAreaValue.height() == main.labelFields["pointSize"].height(), (main.roomAreaValue.height(), main.labelFields["pointSize"].height())
        assert main.roomNameField.height() == main.roomAreaValue.height()
        rows = [main.roomNameField, main.roomAreaValue, main.roomUnitsField,
                main.labelPositionFields["x"], main.labelFields["width"], main.labelFields["pointSize"]]
        for first, second in zip(rows, rows[1:]):
            gap = second.mapTo(main.labelProperties, p().toPoint()).y() - first.mapTo(main.labelProperties, p().toPoint()).y() - first.height()
            assert gap == 8, (first.accessibleName(), second.accessibleName(), gap)
        main.propertiesPanel.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/room-label-properties.png"))
        main.roomUnitsField.setCurrentIndex(main.roomUnitsField.findData("Feet and Inches"))
        assert label.unitsOverride == "Feet and Inches" and main.roomAreaValue.text() == "155.43 ft²"
        assert label.Clone().unitsOverride == "Feet and Inches"
        v.Undo()
        assert label.unitsOverride is None
        v.Redo()
        assert label.unitsOverride == "Feet and Inches"
        main.roomUnitsField.setCurrentIndex(0)
        assert label.unitsOverride is None
        main.EditObjectIntensity(50)
        assert label.intensity == .5
        v.Undo()
        assert label.intensity == 1
        main.roomNameField.setText("BEDROOM")
        assert label.text == "BEDROOM" and (label.firstVertex + label.secondVertex) / 2 == p()
        v.Undo()
        assert label.text == "STUDY"
        v.Redo()
        assert label.text == "BEDROOM"
        saved = main.BuildProjectData()["scene"]
        captured = v.CaptureState()
        for mode in ("Millimeters", "Centimeters", "Meters", "Adaptive Metric", "Feet and Inches", "Inches"):
            v.unitsMode = mode
            v.roomDetection.Check()
            defaultMode = "Feet and Inches" if mode in ("Feet and Inches", "Inches") else "Meters"
            assert label.TextLayout()[4][-1][0] == FormatArea(14440000, defaultMode)
            for override in ("Millimeters", "Centimeters", "Meters", "Feet and Inches", "Inches"):
                label.unitsOverride = override
                v.roomDetection.UpdateLabels(force = True)
                assert label.TextLayout()[4][-1][0] == FormatArea(14440000, override)
            label.unitsOverride = None
            v.roomDetection.UpdateLabels(force = True)
            assert main.BuildProjectData()["scene"] == saved and v.CaptureState() == captured
        # Furniture motion doesn't cause room-area lookup or room detection.
        desk = Furnishing(v.furnishingDefinitions["desk"], p(500, 500))
        v.furnishings = [desk]
        v.roomDetection.Check()
        with patch.object(v.roomDetection, "UpdateLabel", side_effect = AssertionError("Unexpected room-label lookup")):
            v.roomDetection.Check()
            desk.firstVertex += p(50, 0)
            v.roomDetection.Check()
            v.panOffset += p(7, -3)
            v.roomDetection.Check()
        v.furnishings = []
        v.unitsMode = "Meters"
        v.roomDetection.UpdateLabels(force = True)
        center = (label.firstVertex + label.secondVertex) / 2
        label.firstVertex += p(8000, 0)
        label.secondVertex += p(8000, 0)
        v.roomDetection.Check()
        assert label.areaSquareMillimeters is None and label.TextLayout()[4][-1][0] == "—"
        label.firstVertex -= p(8000, 0)
        label.secondVertex -= p(8000, 0)
        v.roomDetection.Check()
        assert label.areaSquareMillimeters == 14440000
        # Derived areas must not resize labels or add edits to the journal.
        originalLabel = (QtCore.QPointF(label.firstVertex), QtCore.QPointF(label.secondVertex), label.width)
        count = len(v.undoHistory)
        v.walls = Rectangle(-2500, -2000, 5000, 4000)
        v.roomDetection.Refresh(force = True)
        assert label.areaSquareMillimeters == 18240000
        assert (label.firstVertex, label.secondVertex, label.width) == originalLabel and len(v.undoHistory) == count
        # Start a valid journal after the authored scene changes above.
        InstallScene(main, walls + [label])
        v.roomDetection.Refresh(force = True)
        v.SetSelection([(label, None)])
        main.roomNameField.setText("BATH")
        path = folder / "Rooms.plan"
        assert main.SaveProject(path)
        data = main.BuildProjectData()
        record = next(record for record in data["scene"]["objects"] if record["type"] == "RoomLabel")
        assert "areaSquareMillimeters" not in record and record["text"] == "BATH"
        decoded = DecodeProject(data, v.furnishingDefinitions)
        assert type(decoded[7][0]) is RoomLabel
        assert main.OpenProject(path)
        label = v.labels[0]
        v.roomDetection.Refresh(force = True)
        assert label.areaSquareMillimeters == 14440000 and label.text == "BATH"
        v.Undo()
        assert label.text == "BEDROOM"
        v.Redo()
        assert label.text == "BATH"
        v.SetSelection([(label, None)])
        try:
            assert v.CopySelection() and v.PasteSelection(v.WorldToViewport(p(500, 500)))
            assert type(v.selectedWall) is RoomLabel and v.selectedWall.text == "BATH"
            v.roomDetection.Check()
            assert v.selectedWall.areaSquareMillimeters == 14440000
            v.Undo()
        finally:
            QtGui.QGuiApplication.clipboard().clear()
        # Export previews must not mutate area/unit state on shared editor labels.
        source = DrawingViewport()
        source.walls, source.labels = list(v.walls), list(v.labels)
        source.furnishingRenderers = v.furnishingRenderers
        source.unitsMode, source.autoSizingUnitsMode = "Millimeters", "Feet and Inches"
        original = label.areaSquareMillimeters, label.areaUnitsMode
        PrepareExportScene(source)
        assert source.labels[0] is not label and source.labels[0].areaUnitsMode == "Meters"
        assert (label.areaSquareMillimeters, label.areaUnitsMode) == original
        source.close()
        drawLabels = RenderingMixin.DrawLabels
        observed = []

        def DrawLabels(viewport, *args, **kwargs):
            observed.extend((obj.areaSquareMillimeters, obj.areaUnitsMode) for obj in viewport.labels if isinstance(obj, RoomLabel))
            return drawLabels(viewport, *args, **kwargs)

        with patch.object(RenderingMixin, "DrawLabels", DrawLabels):
            for format in ("png", "svg"):
                output = RenderPlan(path, 100, bounds = [-3000, -3000, 6000, 6000], projectData = data,
                                    outputFormat = format, applyTheme = False, useExportSettings = True)
                assert output if format == "png" else QtSvg.QSvgRenderer(output).isValid()
        defaultMode = "Feet and Inches" if data["settings"]["unitsMode"] in ("Feet and Inches", "Inches") else "Meters"
        assert observed and all(value == (14440000, defaultMode) for value in observed)
        observed.clear()
        data["settings"].setdefault("exportSettings", {})["unitsMode"] = "Feet and Inches"
        with patch.object(RenderingMixin, "DrawLabels", DrawLabels):
            RenderPlan(path, 100, bounds = [-3000, -3000, 6000, 6000], projectData = data,
                       outputFormat = "svg", applyTheme = False, useExportSettings = True)
        assert observed and all(value == (14440000, "Feet and Inches") for value in observed)
        # An authored override survives file/history/clipboard and beats export units.
        v.SetSelection([(label, None)])
        main.roomUnitsField.setCurrentIndex(main.roomUnitsField.findData("Centimeters"))
        assert main.SaveProject(path)
        assert main.OpenProject(path)
        label = v.labels[0]
        assert label.unitsOverride == "Centimeters" and label.areaUnitsMode == "Centimeters"
        v.Undo()
        assert label.unitsOverride is None
        v.Redo()
        assert label.unitsOverride == "Centimeters"
        v.SetSelection([(label, None)])
        try:
            assert v.CopySelection() and v.PasteSelection(v.WorldToViewport(p(500, 500)))
            assert v.selectedWall.unitsOverride == "Centimeters"
            v.Undo()
        finally:
            QtGui.QGuiApplication.clipboard().clear()
        data = main.BuildProjectData()
        data["settings"].setdefault("exportSettings", {})["unitsMode"] = "Feet and Inches"
        observed.clear()
        with patch.object(RenderingMixin, "DrawLabels", DrawLabels):
            for format in ("png", "svg"):
                RenderPlan(path, 100, bounds = [-3000, -3000, 6000, 6000], projectData = data,
                           outputFormat = format, applyTheme = False, useExportSettings = True)
        assert observed and all(value == (14440000, "Centimeters") for value in observed)
        v.SetSelection([])
        CompareScene(v)
        v.isPanning = True
        for delta in (p(3, 1), p(-17, 5)):
            v.panOffset += delta
            ComparePan(v)
        v.isPanning = False
        # Room labels can be placed outside enclosed space, then moved into position.
        v.labels = []
        mime = QtCore.QMimeData()
        mime.setData("application/x-planner-room-label", b"room-label")
        position = v.WorldToViewport(p())
        enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                      QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, enter)
        assert enter.isAccepted()
        move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                    QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, move)
        assert move.isAccepted() and type(v.labelPreview) is RoomLabel
        drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
                                QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, drop)
        assert drop.isAccepted() and type(v.labels[0]) is RoomLabel
        assert (v.labels[0].firstVertex + v.labels[0].secondVertex) / 2 == p()
        outside = v.WorldToViewport(p(3500, 0))
        enter = QtGui.QDragEnterEvent(outside.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                      QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, enter)
        move = QtGui.QDragMoveEvent(outside.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                    QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, move)
        assert move.isAccepted() and isinstance(v.labelPreview, RoomLabel)
        drop = QtGui.QDropEvent(outside, QtCore.Qt.DropAction.CopyAction, mime,
                                QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        v.dropEvent(drop)
        assert drop.isAccepted() and len(v.labels) == 2
        assert v.labels[-1].areaSquareMillimeters is None
        v.SetSelection([])
        v.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/room-label-preview.png"))
        ordinary = Label(p(), "Ordinary label")
        v.labels.append(ordinary)
        v.SetSelection([(ordinary, None)])
        assert main.labelProperties.layout().labelForField(main.labelTextField).text() == "Text"
        assert not main.labelProperties.layout().isRowVisible(main.roomAreaValue)
        assert main.roomNameField.isHidden() and not main.labelTextField.isHidden()
        # Room names are single-line for typing, paste, models and file transports.
        label = v.labels[0]
        v.SetSelection([(label, None)])
        main.roomNameField.setText("FIRST\nSECOND")
        assert label.text == main.roomNameField.text() == "FIRST SECOND"
        main.roomNameField.setFocus()
        QtTest.QTest.keyClick(main.roomNameField, QtCore.Qt.Key.Key_Return)
        assert label.text == "FIRST SECOND"
        assert RoomLabel(text = "UPPER\r\nLOWER").text == "UPPER LOWER"
        ordinary.SetText("FIRST\nSECOND")
        assert ordinary.text == "FIRST\nSECOND"
    print("Room labels: centered mixed-size text, exact floor areas, all units, derived-state safety, editing/history/clipboard/export and native placement passed")


if __name__ == "__main__":
    Main()
