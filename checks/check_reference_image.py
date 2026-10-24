"""Independent reference visibility, panel restoration, canvas editing and embedded project data."""
import copy
import math
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.project_codec import DecodeProject
from planner_app.project_recovery import RecoverProject
from check_pan_dpi import CompareDirect
from planner_app import reference_image


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    ApplyApplicationTheme(app)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "reference.png"
        image = QtGui.QImage(320, 160, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor("#cc4030"))
        assert image.save(str(path))
        main = MainWindow()
        main.show()
        app.processEvents()
        v, reference = main.viewport, main.referenceImage
        v.showTips = False
        v.showGrid = False
        item = main.referenceImageItem
        main.sidebarTabs.setCurrentWidget(main.visibilityPage)
        assert item.parent() is None and item.checkState(0) == QtCore.Qt.CheckState.Unchecked
        assert reference.state is None and not reference.active
        main.sidebarTabs.setCurrentIndex(0)
        v.setFocus()
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", side_effect = AssertionError("Alt+B must not load an image")):
            QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_B, QtCore.Qt.KeyboardModifier.AltModifier)
        assert reference.state is None and main.sidebarTabs.currentIndex() == 0
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value = ("", "")) as dialog:
            main.viewOptions["referenceImage"].click()
            assert dialog.call_count == 1
            assert item.checkState(0) == QtCore.Qt.CheckState.Unchecked and reference.state is None
            assert main.sidebarTabs.currentIndex() == 0
        wall = Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), 200)
        v.walls = [wall]
        v.SetSelection([(wall, None)])
        main.SetPropertiesCollapsed(True)
        sizes = main.sidebarContentSplitter.sizes()
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value = (str(path), "")) as dialog:
            main.viewOptions["referenceImage"].click()
            assert dialog.call_count == 1
        app.processEvents()
        assert main.sidebarTabs.currentWidget() is main.visibilityPage
        main.ShowViewMenu()
        assert not main.viewOptions["referenceImage"].iconLabel.pixmap().isNull()
        main.viewMenu.hide()
        assert main.viewOptions["referenceImage"].shortcutLabel.text() == "B"
        v.setFocus()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_B)
        assert not reference.state["visible"] and not reference.active
        main.sidebarTabs.setCurrentIndex(0)
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", side_effect = AssertionError("Alt+B must leave disabled images alone")):
            QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_B, QtCore.Qt.KeyboardModifier.AltModifier)
        assert not reference.state["visible"] and not reference.active and main.sidebarTabs.currentIndex() == 0
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_B)
        assert reference.state["visible"] and reference.active
        originalPath = reference.pathField.text()
        reference.pathField.setFocus()
        reference.pathField.setCursorPosition(len(originalPath))
        QtTest.QTest.keyClick(reference.pathField, QtCore.Qt.Key.Key_B)
        assert reference.pathField.text() == originalPath + "b" and reference.state["visible"]
        reference.pathField.setText(originalPath)
        v.setFocus()
        main.sidebarTabs.setCurrentIndex(0)
        assert not reference.active and reference.state["visible"]
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", side_effect = AssertionError("Alt+B must reuse the image")):
            QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_B, QtCore.Qt.KeyboardModifier.AltModifier)
        assert main.sidebarTabs.currentWidget() is main.visibilityPage and reference.active and reference.state["visible"]
        assert reference.active and reference.panel.isVisible() and not main.propertiesCollapsed
        assert v.SelectionEntries() == [] and main.wallProperties.isHidden()
        assert reference.pathField.text() == str(path)
        assert "locked" not in reference.state and not hasattr(reference, "lockedField")
        assert len(reference.Handles()) == 8
        assert reference.Handles() == [handle for handle in v.FurnishingHandles(reference.proxy, pivot = QtCore.QPointF(*reference.state["center"]))
                                       if handle[0] == "resize"]
        assert v.VisibleFurnishingHandles() == []
        assert reference.calibrateButton.isEnabled()
        assert reference.browseButton.objectName() == main.exportPanel.browseButton.objectName()
        assert reference.browseButton.size() == main.exportPanel.browseButton.size()
        reference.opacitySlider.setValue(65)
        assert reference.state["opacity"] == .65 and reference.opacityValue.text() == "65%"
        beforeCenter = list(reference.state["center"])
        reference.opacitySlider.setFocus()
        QtTest.QTest.keyClick(reference.opacitySlider, QtCore.Qt.Key.Key_Right)
        assert reference.state["opacity"] == .66 and reference.state["center"] == beforeCenter
        reference.opacitySlider.setValue(65)
        main.sidebarTabs.setCurrentIndex(0)
        app.processEvents()
        assert not reference.active and reference.panel.isHidden() and main.propertiesCollapsed
        assert not main.selectionLabel.isHidden() and "Wall" in main.selectionLabel.text()
        assert main.sidebarContentSplitter.sizes() == sizes
        assert v.SelectionEntries() == [(wall, None)]
        main.sidebarTabs.setCurrentWidget(main.visibilityPage)
        assert not reference.active, "Changing back to Visibility unexpectedly replaced the properties"
        rect = main.visibilityTree.visualItemRect(item)
        QtTest.QTest.mouseClick(main.visibilityTree.viewport(), QtCore.Qt.MouseButton.LeftButton,
                               pos = QtCore.QPoint(rect.left() + 90, rect.center().y()))
        assert reference.active and not main.propertiesCollapsed
        # Reference mode blocks scene selection; clicking void cancels without selecting through it.
        other = Wall(QtCore.QPointF(2000, 2000), QtCore.QPointF(3000, 2000), 150)
        v.walls.append(other)
        v.SetSelection([(other, None)])
        assert reference.active and v.SelectionEntries() == []
        assert v.HitTest(v.WorldToViewport(QtCore.QPointF())) == (None, None)
        beforeScene = v.CaptureState()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_A, QtCore.Qt.KeyboardModifier.ControlModifier)
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_D)
        assert reference.active and not v.SelectionEntries() and v.openingPlacementMode is None
        assert v.CaptureState() == beforeScene
        void = (v.DrawingRect().topLeft() + QtCore.QPointF(10, 10)).toPoint()
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.LeftButton, pos = void)
        assert not reference.active and main.propertiesCollapsed
        assert v.SelectionEntries() == [(wall, None)]
        assert v.CaptureState()[0] == beforeScene[0]
        reference.Show()
        main.viewOptions["referenceImage"].click()
        assert not reference.active and v.SelectionEntries() == [(wall, None)]
        main.sidebarTabs.setCurrentIndex(1)
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", side_effect = AssertionError("Asked for image again")):
            main.viewOptions["referenceImage"].click()
        assert main.sidebarTabs.currentWidget() is main.visibilityPage and reference.active
        main.visibilityItems["World"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        assert reference.state["visible"] and item.checkState(0) == QtCore.Qt.CheckState.Checked
        assert not v.visibility["World"]
        # Reference is behind geometry, independently visible even with World off.
        center = (v.WorldToViewport(QtCore.QPointF(*reference.state["center"])) * v.devicePixelRatioF()).toPoint()
        visible = v.grab().toImage().pixelColor(center)
        assert visible.red() != visible.green(), "Reference editing must preserve image color"
        reference.Hide()
        normal = v.grab().toImage().pixelColor(center)
        assert normal == visible, "Reference editing must preserve image opacity and background appearance"
        reference.Show()
        assert v.grab().toImage().pixelColor(center) == visible, "Entering reference editing should also work with warm scene caches"
        reference.opacitySlider.setValue(0)
        hidden = v.grab().toImage().pixelColor(center)
        assert visible != hidden
        reference.opacitySlider.setValue(65)
        main.visibilityItems["World"].setCheckState(0, QtCore.Qt.CheckState.Checked)
        wallPixel = v.grab().toImage().pixelColor(center)
        assert wallPixel != visible, "Reference image painted above the wall"
        reference.Hide(restoreSelection = False)
        normalWall = v.grab().toImage().pixelColor(center)
        contrast = lambda color: sum(abs(a - b) for a, b in zip(color.getRgb()[:3], visible.getRgb()[:3]))
        assert contrast(normalWall) * .4 < contrast(wallPixel) < contrast(normalWall) * .6, "Inactive objects should retain about half their contrast"
        reference.Show()
        assert v.grab().toImage().pixelColor(center) == wallPixel
        cached = v.grab().toImage()
        limit = v.viewportRasterByteLimit
        v.viewportRasterByteLimit = 0
        uncached = v.grab().toImage()
        cached.save(str(root / "diagnostics/reference-focus-cached.png"))
        uncached.save(str(root / "diagnostics/reference-focus-uncached.png"))
        assert uncached == cached, "Low-budget focus rendering should match cached rendering"
        v.viewportRasterByteLimit = limit
        # Panning must remain available while reference controls are open.
        savedReference, pan = reference.Snapshot(), QtCore.QPointF(v.panOffset)
        position = v.DrawingRect().center().toPoint()
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.MiddleButton, pos = position)
        QtTest.QTest.mouseMove(v, position + QtCore.QPoint(25, 10))
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.MiddleButton, pos = position + QtCore.QPoint(25, 10))
        assert v.panOffset != pan and reference.Snapshot() == savedReference
        CompareDirect(v)
        # Exercise the exposed-strip pan cache with the reference behind the grid.
        v.isPanning = True
        v.grab()
        for delta in (QtCore.QPointF(3, 1), QtCore.QPointF(-7, 4)):
            v.panOffset += delta
            v.grab()
            CompareDirect(v)
        v.isPanning = False
        # Handles and single-object transform math come from the furnishing implementation.
        v.snapEnabled = False
        pan = QtCore.QPointF(v.panOffset)
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.MiddleButton, pos = position)
        QtTest.QTest.mouseMove(v, position + QtCore.QPoint(10, 5))
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.MiddleButton, pos = position + QtCore.QPoint(10, 5))
        assert v.panOffset != pan and reference.drag is None
        before = reference.Snapshot()
        position = v.WorldToViewport(QtCore.QPointF(*before["center"])) + QtCore.QPointF(0, 70)
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = position.toPoint())
        assert reference.drag is not None
        QtTest.QTest.mouseMove(v, (position + QtCore.QPointF(25, 15)).toPoint())
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = (position + QtCore.QPointF(25, 15)).toPoint())
        assert reference.drag is None and reference.state["center"] != before["center"]
        assert math.isclose(reference.state["width"], before["width"])
        reference.fields["width"].setValue(2000)
        reference.fields["length"].setValue(1000)
        before = reference.Snapshot()
        corner = next(handle[3] for handle in reference.Handles() if handle[1] == "corner" and handle[2] == (1, -1))
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = corner.toPoint())
        assert reference.drag is not None
        QtTest.QTest.mouseMove(v, (corner + QtCore.QPointF(20, 10)).toPoint())
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = (corner + QtCore.QPointF(20, 10)).toPoint())
        assert reference.state["width"] != before["width"]
        assert math.isclose(reference.state["width"] / reference.state["height"], 2)
        before = reference.Snapshot()
        edge = next(handle[3] for handle in reference.Handles() if handle[1] == "width" and handle[2] == 1)
        QtTest.QTest.mouseMove(v, edge.toPoint())
        resizeCursor = v.cursor().shape()
        with patch.object(v, "setCursor", wraps = v.setCursor) as setCursor:
            for unused in range(5):
                v.UpdateCanvasCursor()
                app.processEvents()
            assert v.cursor().shape() == resizeCursor and not setCursor.called, "Canvas resets the reference handle cursor"
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.ShiftModifier, pos = edge.toPoint())
        assert reference.drag is not None
        destination = edge + QtCore.QPointF(20, 0)
        move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, destination, QtCore.QPointF(v.mapToGlobal(destination.toPoint())),
                                QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.ShiftModifier)
        app.sendEvent(v, move)
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.ShiftModifier, pos = destination.toPoint())
        assert reference.state["width"] != before["width"] and math.isclose(reference.state["height"], before["height"])
        assert all(math.isclose(a, b) for a, b in zip(reference.state["center"], before["center"]))
        reference.state = before
        reference.SyncProperties()
        before = reference.Snapshot()
        body = v.WorldToViewport(QtCore.QPointF(*reference.state["center"]))
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.LeftButton, pos = body.toPoint())
        assert reference.rotating and all(handle[0] in ("rotate", "pivot") for handle in reference.Handles())
        rotation = next(handle[3] for handle in reference.Handles() if handle[0] == "rotate")
        QtTest.QTest.mouseMove(v, rotation.toPoint())
        rotationCursor = v.cursor().pixmap().cacheKey()
        assert not v.cursor().pixmap().isNull()
        with patch.object(v, "setCursor", wraps = v.setCursor) as setCursor:
            for unused in range(5):
                v.UpdateCanvasCursor()
                app.processEvents()
            assert v.cursor().pixmap().cacheKey() == rotationCursor and not setCursor.called
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = rotation.toPoint())
        QtTest.QTest.mouseMove(v, (rotation + QtCore.QPointF(40, 0)).toPoint())
        assert reference.state["angle"] != before["angle"]
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Escape)
        assert reference.Snapshot() == before and reference.drag is None
        # Moving the pivot changes the position readout, without moving the image.
        pivotHandle = next(handle[3] for handle in reference.Handles() if handle[0] == "pivot")
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = pivotHandle.toPoint())
        QtTest.QTest.mouseMove(v, (pivotHandle + QtCore.QPointF(30, 20)).toPoint())
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = (pivotHandle + QtCore.QPointF(30, 20)).toPoint())
        assert reference.Snapshot() == before and reference.pivot is not None
        assert math.isclose(reference.fields["x"].value(), reference.pivot.x(), abs_tol = .5)
        assert math.isclose(reference.fields["y"].value(), reference.pivot.y(), abs_tol = .5)
        pivot = QtCore.QPointF(reference.pivot)
        offset = QtCore.QPointF(*before["center"]) - pivot
        reference.fields["angle"].setValue(before["angle"] + 90)
        expected = pivot + QtCore.QPointF(-offset.y(), offset.x())
        assert QtCore.QLineF(QtCore.QPointF(*reference.state["center"]), expected).length() < 1e-6
        assert reference.pivot == pivot and reference.fields["angle"].suffix() == " °"
        # Typed X/Y translate the image and pivot together; cancelling a field drag restores both.
        old = reference.Snapshot()
        reference.BeginPropertyDrag()
        reference.fields["x"].setValue(pivot.x() + 100)
        assert math.isclose(reference.pivot.x(), reference.fields["x"].value())
        assert math.isclose(reference.state["center"][0] - old["center"][0], reference.pivot.x() - pivot.x())
        reference.FinishPropertyDrag(True)
        assert reference.Snapshot() == old and reference.pivot == pivot
        # Resize mode displays the center even if a custom pivot exists.
        reference.rotating = False
        reference.SyncProperties()
        assert math.isclose(reference.fields["x"].value(), reference.state["center"][0], abs_tol = .5)
        assert math.isclose(reference.fields["y"].value(), reference.state["center"][1], abs_tol = .5)
        center = list(reference.state["center"])
        reference.fields["angle"].setValue(0)
        assert reference.state["center"] == center
        reference.pivot = None
        # Center-position fields and independent dimensions use the normal draggable editors.
        from planner_app.ui.widgets import DragSpinBox
        assert all(isinstance(field, DragSpinBox) for field in reference.fields.values())
        reference.fields["x"].setValue(100)
        reference.fields["y"].setValue(200)
        reference.fields["width"].setValue(1600)
        reference.fields["length"].setValue(800)
        reference.fields["angle"].setValue(30)
        assert reference.state["center"] == [100, 200]
        assert reference.state["width"] == 1600 and reference.state["height"] == 800
        assert reference.state["angle"] == 30
        old = reference.Snapshot()
        editor = reference.fields["x"].lineEdit()
        main.propertiesScrollArea.ensureWidgetVisible(editor)
        start = editor.rect().center()
        QtTest.QTest.mousePress(editor, QtCore.Qt.MouseButton.LeftButton, pos = start)
        QtTest.QTest.mouseMove(editor, start + QtCore.QPoint(30, 0))
        assert reference.state["center"][0] != old["center"][0]
        QtTest.QTest.keyClick(editor, QtCore.Qt.Key.Key_Escape)
        QtTest.QTest.mouseRelease(editor, QtCore.Qt.MouseButton.LeftButton, pos = start + QtCore.QPoint(30, 0))
        assert reference.Snapshot() == old
        main.ShowSettings()
        main.settingsWindow.SetUnitsMode("Inches")
        assert math.isclose(reference.fields["width"].value(), 1600 / 25.4, abs_tol = .001)
        assert reference.Snapshot() == old
        main.settingsWindow.hide()
        app.processEvents()
        main.grab().save(str(root / "diagnostics/reference-image.png"))
        saved = reference.Snapshot()
        project = Path(directory) / "reference.plan"
        assert main.SaveProject(project)
        path.unlink()
        assert main.OpenProject(project)
        assert reference.Snapshot() == saved and not reference.image.isNull(), {
            key: (saved.get(key), (reference.state or {}).get(key)) for key in saved
            if key != "data" and saved.get(key) != (reference.state or {}).get(key)}
        assert not reference.active
        legacy = copy.deepcopy(main.BuildProjectData())
        legacy["settings"]["referenceImage"]["locked"] = True
        assert "locked" not in DecodeProject(legacy, v.furnishingDefinitions)[5]["referenceImage"]
        with patch.object(reference_image, "ReadReferenceImage", wraps = reference_image.ReadReferenceImage) as decode:
            decoded, notices = RecoverProject(main.BuildProjectData(), v.furnishingDefinitions, main.defaultProjectData)
            assert decoded[5]["referenceImage"] == saved and not notices
            assert decode.call_count == 1, "Recovery repeatedly decoded the image during metadata probes"
        bad = copy.deepcopy(main.BuildProjectData())
        bad["settings"]["referenceImage"]["data"] = "invalid"
        try:
            DecodeProject(bad, v.furnishingDefinitions)
            raise AssertionError("Accepted corrupt embedded image")
        except ValueError:
            pass
        decoded, notices = RecoverProject(bad, v.furnishingDefinitions, main.defaultProjectData)
        assert notices and "referenceImage" not in decoded[5]
        assert main.NewProject()
        assert reference.state is None and item.checkState(0) == QtCore.Qt.CheckState.Unchecked
        reference.Restore(saved)
        reference.Changed()
        main.MarkProjectClean()
        main.close()
        restored = MainWindow()
        assert restored.referenceImage.Snapshot() == saved
        assert not restored.referenceImage.image.isNull() and not restored.referenceImage.active
        restored.MarkProjectClean()
        restored.close()


if __name__ == "__main__":
    Main()
