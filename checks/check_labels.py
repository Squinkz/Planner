"""Multiline labels, anchored placement, transforms and persistence."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Label
from theme import BuildStyle
from check_history import Drag
from planner_app.project_codec import DecodeProject
from planner_app.graphics.text import PathTextPainter


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.resize(1300, 900)
    main.show()
    app.processEvents()
    v = main.viewport
    v.unitsMode = "Adaptive Metric"  # Dimension edits below use centimeters.
    v.snapEnabled = False
    point = QtCore.QPointF
    left = QtCore.Qt.MouseButton.LeftButton
    none = QtCore.Qt.KeyboardModifier.NoModifier
    origin = point(-500, -300)
    screen = v.WorldToViewport(origin)
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-label", b"label")
    enter = QtGui.QDragEnterEvent(screen.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, left, none)
    v.dragEnterEvent(enter)
    assert enter.isAccepted()
    move = QtGui.QDragMoveEvent(screen.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, left, none)
    v.dragMoveEvent(move)
    assert v.labelPreview is not None and QtCore.QLineF(v.labelPreview.origin, origin).length() < .001
    drop = QtGui.QDropEvent(screen, QtCore.Qt.DropAction.CopyAction, mime, left, none)
    v.dropEvent(drop)
    assert drop.isAccepted() and len(v.labels) == 1 and v.labelPreview is None
    label = v.labels[0]
    assert QtCore.QLineF(label.origin, origin).length() < .001
    assert main.labelProperties.isVisible() and not main.wallProperties.isVisible()
    assert main.labelProperties.layout().rowCount() == 8
    assert label.objectId is not None and main.selectionLabel.text() == f"Label (#{label.objectId:04d})"
    assert label.Font().pointSize() == 18 and label.intensity == 1
    assert abs(label.pointSize - 32) < 1e-6
    assert not main.labelFields["pointSize"].toolTip()
    historyCount = len(v.undoHistory)
    main.labelIntensitySlider.sliderPressed.emit()
    main.labelIntensitySlider.setValue(70)
    main.labelIntensitySlider.setValue(40)
    main.labelIntensitySlider.sliderReleased.emit()
    assert label.intensity == .4 and len(v.undoHistory) == historyCount + 1
    v.Undo()
    assert label.intensity == 1
    v.Redo()
    assert label.intensity == .4
    main.labelTextField.setPlainText("Living Room\nSecond line")
    assert label.text == "Living Room\nSecond line"
    v.Undo()
    assert label.text == "Label"
    v.Redo()
    assert label.text == "Living Room\nSecond line"
    center = v.WorldToViewport((label.firstVertex + label.secondVertex) / 2)
    assert v.HitTest(center) == (label, None)
    assert len(v.VisibleFurnishingHandles()[0][1]) == 4
    # Check the actual rendered line centers, including the shorter second line.
    centers = []
    opacities = []

    class TextPainter(PathTextPainter):
        def drawText(self, *args):
            if len(args) == 2 and isinstance(args[0], QtCore.QPointF) and args[1] in label.text.split("\n"):
                advance = QtGui.QFontMetricsF(self.font()).horizontalAdvance(args[1])
                centers.append(self.transform().map(args[0] + point(advance / 2, 0)))
                opacities.append(self.opacity())
            super().drawText(*args)

    with patch("planner_app.viewport.rendering.PathTextPainter", TextPainter):
        image = v.grab()
    assert len(centers) == 2 and all(abs(position.x() - center.x()) < .001 for position in centers)
    assert opacities == [.4, .4]
    main.labelIntensitySlider.setValue(0)
    opacities.clear()
    with patch("planner_app.viewport.rendering.PathTextPainter", TextPainter):
        v.grab()
    assert label.intensity == 0 and opacities == [0, 0]
    v.Undo()
    assert label.intensity == .4
    image.save(str(Path(__file__).resolve().parent.parent / "screenshots" / "labels.png"))
    app.processEvents()
    assert main.labelTextField.geometry().bottom() < main.labelFields["width"].geometry().top()
    main.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "label-properties.png"))
    handle = next(handle for handle in v.FurnishingHandles(label) if handle[:3] == ("resize", "corner", (-1, -1)))
    anchored = v.ObjectCorners(label)[2]
    width = label.width
    ratio = label.width / label.length
    pointSize = label.pointSize
    Drag(v, handle[3].toPoint(), (handle[3] + point(-80, 0)).toPoint())
    assert label.width > width
    assert abs(label.width / label.length - ratio) < 1e-6
    assert label.pointSize > pointSize
    assert QtCore.QLineF(v.ObjectCorners(label)[2], anchored).length() < .001
    v.Undo()
    assert abs(label.width - width) < .001
    anchor = point(label.origin)
    main.labelFields["pointSize"].setValue(72)
    assert abs(label.pointSize - 72) < 1e-6
    assert abs(label.width / label.length - ratio) < 1e-6
    assert QtCore.QLineF(label.origin, anchor).length() < 1e-6
    assert abs(label.length / (QtGui.QFontMetricsF(label.Font()).lineSpacing() * len(label.text.split("\n")))
               * QtGui.QFontInfo(label.Font()).pixelSize() - 25.4 * 20) < 1e-6
    v.Undo()
    assert abs(label.pointSize - pointSize) < 1e-6
    main.labelFields["width"].setValue(label.width / 10 * 2)
    assert abs(label.width - width * 2) < .01
    assert abs(label.width / label.length - ratio) < 1e-6
    v.Undo()
    main.labelFields["length"].setValue(label.length / 10 * 2)
    assert abs(label.width - width * 2) < .01
    assert abs(label.width / label.length - ratio) < 1e-6
    v.Undo()
    QtTest.QTest.mouseClick(v, left, pos = center.toPoint())
    assert v.furnishingRotationObject is label
    assert len(v.VisibleFurnishingHandles()[0][1]) == 5
    handle = next(handle for handle in v.FurnishingHandles(label) if handle[0] == "rotate")
    Drag(v, handle[3].toPoint(), (handle[3] + point(80, 70)).toPoint())
    assert min(label.angle, 360 - label.angle) > 1
    v.Undo()
    assert min(label.angle, 360 - label.angle) < .001
    # Labels never collide, even while a wall covers the complete text bounds.
    wall = Wall(point(-2000, 0), point(2000, 0), 1500)
    v.walls = [wall]
    assert not v.ObjectsOverlap(label, wall) and not v.ObjectsOverlap(wall, label)
    assert v.FurnishingFits(label) and v.OpeningsValid()
    v.furnishingRotationObject = None
    v.SetSelection([(label, None)])
    start = v.WorldToViewport((label.firstVertex + label.secondVertex) / 2)
    Drag(v, start.toPoint(), (start + point(100, -50)).toPoint())
    assert QtCore.QLineF(label.origin, origin).length() > 1
    v.Undo()
    assert QtCore.QLineF(label.origin, origin).length() < .001
    try:
        assert v.CopySelection() and v.ReadClipboardSelection() is not None
        assert v.PasteSelection(v.WorldToViewport(point(1000, 0)))
        second = v.selectedWall
        assert isinstance(second, Label) and second.text == label.text
        assert second.intensity == .4 and second.objectId != label.objectId
        assert len(v.labels) == 2 and not v.furnishings
        v.SetSelection([(label, None), (second, None)])
        assert len(v.VisibleFurnishingHandles()) == 1
        main.labelTextField.setPlainText("Shared\nText")
        assert label.text == second.text == "Shared\nText"
        originalPointSize = label.pointSize
        second.SetPointSize(originalPointSize * 2)
        main.RefreshProperties()
        assert all(field.mixedValue and field.lineEdit().placeholderText() == "(different)" for field in main.labelFields.values())
        assert all(handle[1] == "corner" for obj, handles in v.VisibleFurnishingHandles() for handle in handles if handle[0] == "resize")
        main.labelFields["pointSize"].setValue(100)
        assert abs(label.pointSize - 100) < 1e-6 and abs(second.pointSize - 100) < 1e-6
        assert not main.labelFields["pointSize"].mixedValue
        v.Undo()
        assert abs(label.pointSize - originalPointSize) < 1e-6
        second.SetPointSize(originalPointSize)
        second.text = "Different"
        main.RefreshProperties()
        assert main.labelTextField.placeholderText() == "(different)"
        main.labelTextField.setPlainText("Shared\nText")
        assert label.text == second.text
        second.intensity = .8
        main.RefreshProperties()
        assert main.labelIntensityValue.text() == "(different)"
        main.labelIntensitySlider.setValue(50)
        assert label.intensity == second.intensity == .5
    finally:
        app.clipboard().clear()
        app.processEvents()
    v.SetSelection([(label, None)])
    assert v.HideSelection() and not v.IsObjectVisible(label)
    assert v.UnhideObjects() and v.IsObjectVisible(label)
    v.SetSelection([(label, None)])
    v.DeleteSelected()
    assert len(v.labels) == 1
    v.Undo()
    assert len(v.labels) == 2
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "Labels.plan"
        assert main.SaveProject(path) and main.NewProject() and main.OpenProject(path)
        assert len(v.labels) == 2 and all(obj.text == "Shared\nText" for obj in v.labels)
        assert all(obj.intensity == .5 and obj.objectId is not None for obj in v.labels)
        legacy = main.BuildProjectData()
        del legacy["settings"]["visibility"]["Labels"]
        for record in legacy["scene"]["objects"]:
            if record["type"] == "Label":
                del record["intensity"]
        assert DecodeProject(legacy, v.furnishingDefinitions)[5]["visibility"]["Labels"]
        assert all(obj.intensity == 1 for obj in DecodeProject(legacy, v.furnishingDefinitions)[7])
        before = v.CaptureState()
        tiny = Label(text = "")
        tiny.SetPointSize(.15)
        assert 0 < tiny.width < 1
        v.labels.append(tiny)
        v.SetSelection([(tiny, None)])
        assert v.CopySelection() and v.ReadClipboardSelection() is not None
        assert v.PasteSelection(v.WorldToViewport(point(1500, 0)))
        assert abs(v.selectedWall.pointSize - .15) < 1e-6
        assert main.SaveProject(path) and main.OpenProject(path)
        assert sum(abs(obj.pointSize - .15) < 1e-6 for obj in v.labels) == 2
        v.RestoreState(before)
        app.clipboard().clear()
    main.close()
    restored = MainWindow()
    assert len(restored.viewport.labels) == 2
    assert all(obj.text == "Shared\nText" for obj in restored.viewport.labels)
    assert all(obj.intensity == .5 for obj in restored.viewport.labels)
    restored.close()
    print("PASS: label palette drops, multiline text, handles, no collisions, history, clipboard and recovery.")


if __name__ == "__main__":
    Main()
