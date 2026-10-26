"""North Marker placement, furnishing handles, no collisions and project/export paths."""
import os
import sys
from pathlib import Path
from copy import deepcopy

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.models import NorthArrow, Wall
from planner_app.project_codec import DecodeProject
from planner_app.graphics.north_arrow import DrawNorthArrow
from planner_app.graphics import palette
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from planner_app.project_history import EncodeHistoryState


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.resize(1300, 900)
    main.show()
    app.processEvents()
    v = main.viewport
    v.snapEnabled = False
    v.walls = [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), 1000)]
    v.EnsureObjectIds()
    point = v.WorldToViewport(QtCore.QPointF())
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-north-arrow", b"north-arrow")
    enter = QtGui.QDragEnterEvent(point.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                  QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    v.dragEnterEvent(enter)
    assert enter.isAccepted()
    move = QtGui.QDragMoveEvent(point.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    v.dragMoveEvent(move)
    assert isinstance(v.furnishingPreview, NorthArrow)
    v.grab()
    drop = QtGui.QDropEvent(point, QtCore.Qt.DropAction.CopyAction, mime,
                            QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    v.dropEvent(drop)
    assert drop.isAccepted() and v.furnishingPreview is None
    arrow = v.furnishings[0]
    assert isinstance(arrow, NorthArrow) and v.FurnishingFits(arrow)
    assert not v.ObjectsOverlap(arrow, v.walls[0]) and not v.JoinedObjectsOverlap(arrow, v.walls[0])
    assert v.HitTest(point) == (arrow, None), "North Marker was selected beneath the wall"
    assert main.northArrowButton.toolTip() == "North marker"
    assert "North Marker" in main.selectionLabel.text()
    assert main.wallProperties.isVisible() and not main.labelProperties.isVisible()
    assert main.northArrowOpacityRow.isVisible() and arrow.intensity == 1
    historyCount = len(v.undoHistory)
    main.northArrowIntensitySlider.sliderPressed.emit()
    main.northArrowIntensitySlider.setValue(70)
    main.northArrowIntensitySlider.setValue(40)
    main.northArrowIntensitySlider.sliderReleased.emit()
    assert arrow.intensity == .4 and len(v.undoHistory) == historyCount + 1
    v.Undo()
    assert arrow.intensity == 1
    v.Redo()
    assert arrow.intensity == .4
    assert all(not main.propertyFields[name].isHidden() for name in ("width", "length", "angle"))
    assert len(v.FurnishingHandles(arrow)) >= 8
    for field in ("width", "length"):
        handle = next(handle for handle in v.FurnishingHandles(arrow) if handle[:3] == ("resize", field, 1))
        axis = QtCore.QPointF(1, 0) if field == "width" else QtCore.QPointF(0, 1)
        originalSize = getattr(arrow, field)
        end = v.WorldToViewport(v.ViewportToWorld(handle[3]) + axis * 200)
        v.BeginFurnishingHandleDrag(arrow, handle, handle[3])
        v.UpdateFurnishingHandleDrag(end, QtCore.Qt.KeyboardModifier.NoModifier)
        assert abs(getattr(arrow, field) - originalSize - 200) < .001
        release = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonRelease, end,
                                   QtCore.QPointF(v.mapToGlobal(end.toPoint())), QtCore.Qt.MouseButton.LeftButton,
                                   QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
        v.mouseReleaseEvent(release)
        v.Undo()
        assert abs(getattr(arrow, field) - originalSize) < .001
    main.propertyFields["angle"].setValue(37)
    assert abs(arrow.angle - 37) < .001
    v.Undo()
    assert abs(arrow.angle) < .001
    v.Redo()
    assert abs(arrow.angle - 37) < .001
    clone = arrow.Clone()
    assert clone.intensity == .4
    assert type(clone) is NorthArrow and clone.width == arrow.width and abs(clone.angle - arrow.angle) < .001
    before = v.CaptureState()
    arrow.firstVertex += QtCore.QPointF(250, 300)
    arrow.secondVertex += QtCore.QPointF(250, 300)
    v.RecordEdit(before)
    v.Undo()
    assert QtCore.QLineF((arrow.firstVertex + arrow.secondVertex) / 2, QtCore.QPointF()).length() < .001
    v.Redo()
    assert v.CopySelection()
    assert v.PasteSelection(v.DrawingRect().center() + QtCore.QPointF(100, 0))
    assert len([obj for obj in v.furnishings if isinstance(obj, NorthArrow)]) == 2
    assert all(obj.intensity == .4 for obj in v.furnishings)
    v.Undo()
    assert len(v.furnishings) == 1
    assert EncodeHistoryState(v.CaptureState())["objects"][-1]["type"] == "NorthArrow"
    saved = main.BuildProjectData()
    legacy = deepcopy(saved)
    for record in legacy["scene"]["objects"]:
        if record["type"] == "NorthArrow":
            del record["intensity"]
    assert DecodeProject(legacy, v.furnishingDefinitions)[2][0].intensity == 1
    decoded = DecodeProject(saved, v.furnishingDefinitions)
    assert isinstance(decoded[2][0], NorthArrow) and decoded[2][0].width == arrow.width
    assert decoded[2][0].intensity == .4
    main.ApplyProject(decoded, None)
    v.Redo()
    assert len(v.furnishings) == 2 and all(isinstance(obj, NorthArrow) for obj in v.furnishings)
    assert all(obj.intensity == .4 for obj in v.furnishings)
    v.Undo()
    assert len(v.furnishings) == 1
    arrow = v.furnishings[0]
    v.SetSelection([(arrow, None)])
    main.RefreshProperties()
    main.northArrowIntensitySlider.setValue(65)
    main.ApplyProject(DecodeProject(main.BuildProjectData(), v.furnishingDefinitions), None)
    assert v.furnishings[0].intensity == .65
    v.Undo()
    assert v.furnishings[0].intensity == .4, "Saved undo history lost North Marker opacity"
    v.Redo()
    assert v.furnishings[0].intensity == .65
    v.Undo()
    v.grab()
    v.verifyRenderRevisions = True
    v.SceneRenderKey(("north-arrow-test",))
    panel = main.exportPanel
    main.sidebarTabs.setCurrentWidget(panel)
    panel.borderField.setCurrentText("None")
    panel.showGridField.setChecked(False)
    panel.SetOverride("measurementVisibility", {key: False for key in v.measurementVisibility})
    png = panel.Render("png")
    svg = panel.Render("svg")
    assert SvgPreviewRenderer(svg).isValid()
    arrow = v.furnishings[0]
    arrow.intensity = 0
    transparentPng = panel.Render("png")
    transparentSvg = panel.Render("svg")
    assert transparentPng != png and transparentSvg != svg, "Exports ignored North Marker opacity"
    v.visibility["North markers"] = False
    assert panel.Render("png") == transparentPng, "Zero opacity did not hide the complete North Marker"
    v.visibility["North markers"] = True
    arrow.intensity = .4
    panel.solidObjectsField.setChecked(False)
    assert panel.Render("png") != png, "Solid Objects did not change the North Marker background"
    v.visibility["North markers"] = False
    assert panel.Render("png") != png, "North Marker did not draw above the wall"
    v.visibility["North markers"] = True
    main.sidebarTabs.setCurrentWidget(main.visibilityPage)
    other = arrow.Clone()
    other.intensity = .8
    v.furnishings.append(other)
    v.SetSelection([(arrow, None), (other, None)])
    main.RefreshProperties()
    assert main.northArrowIntensityValue.text() == "(different)"
    main.northArrowIntensitySlider.setValue(50)
    assert arrow.intensity == other.intensity == .5
    v.Undo()
    assert arrow.intensity == .4 and other.intensity == .8
    class GlyphPainter(QtGui.QPainter):
        def fillPath(self, path, brush):
            self.glyph = QtGui.QPainterPath(path)
            super().fillPath(path, brush)
    sizes = []
    image = QtGui.QImage(400, 400, QtGui.QImage.Format.Format_ARGB32)
    for solidBackground in (True, False):
        image.fill("#ff00ff")
        with QtGui.QPainter(image) as painter:
            DrawNorthArrow(painter, QtCore.QPointF(200, 200), 100, 160, 0, "#000000", 1,
                           solidBackground = solidBackground)
        expected = QtGui.QColor(palette.themeColors["canvas"] if solidBackground else "#ff00ff")
        assert image.pixelColor(185, 240) == expected, "Outlined half has the wrong background fill"
    for angle in (0, 90, 180, 270):
        with GlyphPainter(image) as painter:
            DrawNorthArrow(painter, QtCore.QPointF(200, 200), 100, 160, angle, "#000000", 1)
            sizes.append(painter.glyph.boundingRect().size())
    assert all(size == sizes[0] for size in sizes), "N rotated with the arrow"
    image = QtGui.QImage(600, 400, QtGui.QImage.Format.Format_ARGB32)
    image.fill("#ffffff")
    with QtGui.QPainter(image) as painter:
        DrawNorthArrow(painter, QtCore.QPointF(150, 200), 180, 300, 0, "#202020", 3)
        DrawNorthArrow(painter, QtCore.QPointF(450, 200), 180, 300, 45, "#202020", 3)
    image.save(str(Path(__file__).resolve().parent.parent / "diagnostics" / "north-arrow-preview.png"))
    app.clipboard().clear()
    main.close()
    print("PASS: North Marker drop, properties, handles, collisions, clipboard, undo, persistence and PNG/SVG")


if __name__ == "__main__":
    Main()
