"""Click/drag calibration, one-use units, anchored scale and cancellation."""
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.theme import ApplyApplicationTheme


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    ApplyApplicationTheme(app)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "calibration.png"
        image = QtGui.QImage(400, 200, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor("#bc7647"))
        assert image.save(str(path))
        main = MainWindow()
        main.show()
        app.processEvents()
        v, reference = main.viewport, main.referenceImage
        main.sidebarTabs.setCurrentWidget(main.visibilityPage)
        assert reference.Load(path) and reference.active
        reference.Show()
        assert reference.active
        reference.state.update(center = [250, -100], width = 2000, height = 1000, angle = 37)
        reference.pivot = QtCore.QPointF(0, 200)
        reference.rotating = True
        reference.SyncProperties()
        reference.Changed()
        v.unitsMode = "Millimeters"
        scene = v.CaptureState()
        original = reference.Snapshot()
        first = v.WorldToViewport(QtCore.QPointF(-300, -100)).toPoint()
        second = v.WorldToViewport(QtCore.QPointF(300, -100)).toPoint()
        reference.calibrateButton.click()
        calibration = reference.calibration
        # A small movement remains a click; a longer held gesture places both
        # points, using the same Ctrl constraints as later point adjustments.
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = first)
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = first + QtCore.QPoint(1, 0))
        assert len(calibration.points) == 1 and calibration.placementPress is None
        for moveEvent in (False, True):
            calibration.Start()
            QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = first)
            assert len(calibration.points) == 1
            target = second + QtCore.QPoint(0, 23)
            if moveEvent:
                QtTest.QTest.mouseMove(v, target)
                assert calibration.draggedPoint == 1 and len(calibration.points) == 2
                QtTest.QTest.keyPress(v, QtCore.Qt.Key.Key_Control)
                assert v.axisConstraintOrigin is not None
            QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton,
                                     QtCore.Qt.KeyboardModifier.ControlModifier if moveEvent else QtCore.Qt.KeyboardModifier.NoModifier,
                                     pos = target)
            if moveEvent:
                QtTest.QTest.keyRelease(v, QtCore.Qt.Key.Key_Control)
            assert len(calibration.points) == 2 and calibration.draggedPoint is None and calibration.dialog is None
            assert calibration.points[0] == v.ViewportToWorld(QtCore.QPointF(first))
        calibration.Start()
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = first)
        QtTest.QTest.mouseMove(v, second)
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.RightButton, pos = second)
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = second)
        assert len(calibration.points) == 1 and calibration.draggedPoint is None
        assert reference.Snapshot() == original and v.CaptureState() == scene
        calibration.Start()
        assert calibration.active and not reference.panel.isEnabled() and reference.Handles() == []
        assert v.cursor().shape() == QtCore.Qt.CursorShape.CrossCursor
        v.grab().save(str(root / "diagnostics/reference-calibration-place.png"))
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Return)
        assert calibration.dialog is None
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.LeftButton, pos = first)
        assert len(calibration.points) == 1
        QtTest.QTest.mouseMove(v, second)
        assert len(calibration.points) == 1, "A mouse move placed the second point"
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Return)
        assert calibration.dialog is None
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.LeftButton, pos = second)
        assert len(calibration.points) == 2 and calibration.dialog is None
        assert reference.Snapshot() == original and v.CaptureState() == scene
        v.grab().save(str(root / "diagnostics/reference-calibration.png"))
        # Existing camera navigation stays available and does not move picked points.
        points = [QtCore.QPointF(point) for point in calibration.points]
        pan = QtCore.QPointF(v.panOffset)
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.MiddleButton, pos = first)
        QtTest.QTest.mouseMove(v, first + QtCore.QPoint(20, 10))
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.MiddleButton, pos = first + QtCore.QPoint(20, 10))
        assert v.panOffset != pan and calibration.points == points
        # Both placed control points can be adjusted without transforming the image.
        start = v.WorldToViewport(calibration.points[1]).toPoint()
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = start)
        QtTest.QTest.mouseMove(v, start + QtCore.QPoint(15, 5))
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = start + QtCore.QPoint(15, 5))
        assert calibration.points[1] != points[1] and reference.Snapshot() == original
        # Hover/drag cursors and Ctrl constraints match annotation control points.
        calibration.points[1] += QtCore.QPointF(17, 53)
        savedSnap, savedLocal = v.snapEnabled, v.localTransforms
        v.snapEnabled = False
        for local in (False, True):
            v.localTransforms = local
            for index in (0, 1):
                beforePoints = [QtCore.QPointF(point) for point in calibration.points]
                start = v.WorldToViewport(beforePoints[index]).toPoint()
                QtTest.QTest.mouseMove(v, start)
                assert v.cursor().shape() == QtCore.Qt.CursorShape.SizeAllCursor
                QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = start)
                direction = beforePoints[index] - beforePoints[1 - index]
                originAngle = math.atan2(direction.y(), direction.x()) if local else 0
                angle = originAngle + math.radians(19)
                target = v.WorldToViewport(beforePoints[1 - index] + QtCore.QPointF(math.cos(angle), math.sin(angle)) * 600).toPoint()
                QtTest.QTest.mouseMove(v, target)
                unconstrained = QtCore.QPointF(calibration.points[index])
                QtTest.QTest.keyPress(v, QtCore.Qt.Key.Key_Control)
                direction = calibration.points[index] - calibration.points[1 - index]
                steps = (math.atan2(direction.y(), direction.x()) - originAngle) / math.radians(15)
                assert math.isclose(steps, round(steps), abs_tol = 1e-6)
                assert v.axisConstraintOrigin is not None and v.axisConstraintDirection is not None
                assert calibration.active and reference.Snapshot() == original
                if not local and index == 1:
                    v.grab().save(str(root / "diagnostics/reference-calibration-drag.png"))
                QtTest.QTest.keyRelease(v, QtCore.Qt.Key.Key_Control)
                assert v.axisConstraintOrigin is None and v.axisConstraintDirection is None
                assert QtCore.QLineF(calibration.points[index], unconstrained).length() < 1e-6
                QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.RightButton, pos = target)
                QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = target)
                assert calibration.points == beforePoints and calibration.active and calibration.draggedPoint is None
        v.snapEnabled, v.localTransforms = savedSnap, savedLocal
        anchor = QtCore.QPointF(calibration.points[0])
        measured = QtCore.QLineF(*calibration.points).length()
        imagePoint = reference.ScreenTransform().inverted()[0].map(v.WorldToViewport(anchor))
        oldPivot = QtCore.QPointF(reference.pivot)
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Return)
        dialog = calibration.dialog
        assert dialog is not None and dialog.isVisible() and dialog.unitsField.currentData() == "Millimeters"
        assert dialog.distanceField.objectName() == "settingsValue"
        app.processEvents()
        assert dialog.unitsField.width() < dialog.distanceField.width()
        assert abs(dialog.unitsField.geometry().center().y() - dialog.distanceField.geometry().center().y()) <= 1
        dialog.grab().save(str(root / "diagnostics/reference-calibration-dialog.png"))
        dialog.unitsField.setCurrentIndex(dialog.unitsField.findData("Centimeters"))
        assert math.isclose(dialog.distanceField.value() * 10, measured, abs_tol = 1e-4)
        dialog.distanceField.setValue(measured * 2 / 10)
        factor = dialog.distanceField.value() * 10 / measured
        dialog.accept()
        assert not calibration.active and calibration.dialog is None and reference.panel.isEnabled()
        assert v.unitsMode == "Millimeters" and v.CaptureState() == scene
        assert math.isclose(reference.state["width"], original["width"] * factor)
        assert math.isclose(reference.state["height"], original["height"] * factor)
        assert reference.state["angle"] == original["angle"] and reference.state["opacity"] == original["opacity"]
        assert QtCore.QLineF(reference.ScreenTransform().map(imagePoint * factor), v.WorldToViewport(anchor)).length() < 1e-6
        assert QtCore.QLineF(reference.pivot, anchor + (oldPivot - anchor) * factor).length() < 1e-6
        saved = reference.Snapshot()
        # Reject invalid/degenerate values; cancelling the dialog preserves the two points.
        reference.calibrateButton.click()
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.LeftButton, pos = first)
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.LeftButton, pos = second)
        for invalid in (0, -1, float("nan"), float("inf"), 1e30):
            assert calibration.Apply(invalid) and reference.Snapshot() == saved
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Return)
        dialog = calibration.dialog
        assert dialog.unitsField.currentData() == "Millimeters", "One-use unit choice leaked to the next action"
        dialog.distanceField.setValue(0)
        dialog.accept()
        assert calibration.dialog is dialog and not dialog.errorLabel.isHidden() and reference.Snapshot() == saved
        dialog.reject()
        assert calibration.active and len(calibration.points) == 2 and reference.Snapshot() == saved
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Escape)
        assert not calibration.active and reference.active and reference.Snapshot() == saved
        # Mixed feet/inches input uses the existing unit editor and stays local to this action.
        v.unitsMode = "Feet and Inches"
        reference.calibrateButton.click()
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.LeftButton, pos = first)
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.LeftButton, pos = second)
        measured = QtCore.QLineF(*calibration.points).length()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Return)
        dialog = calibration.dialog
        assert dialog.unitsField.currentData() == "Feet and Inches"
        dialog.distanceField.lineEdit().setText("3' 6\"")
        previousWidth = reference.state["width"]
        dialog.accept()
        assert math.isclose(reference.state["width"], previousWidth * 1066.8 / measured, rel_tol = 1e-6)
        assert v.unitsMode == "Feet and Inches"
        # Adaptive projects use explicit meters for this one-use dimension input.
        v.unitsMode = "Adaptive Metric"
        reference.calibrateButton.click()
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.LeftButton, pos = first)
        QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.LeftButton, pos = second)
        measured = QtCore.QLineF(*calibration.points).length()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Return)
        dialog = calibration.dialog
        assert dialog.unitsField.findData("Adaptive Metric") == -1
        assert dialog.unitsField.currentData() == "Meters"
        assert math.isclose(dialog.distanceField.value() * 1000, measured, abs_tol = 1e-3)
        dialog.reject()
        assert v.unitsMode == "Adaptive Metric"
        # Leaving reference mode cancels unfinished calibration, including its dialog.
        reference.calibrateButton.click()
        main.sidebarTabs.setCurrentIndex(0)
        assert not calibration.active and not reference.active and reference.panel.isEnabled()
        saved = reference.Snapshot()
        project = Path(directory) / "calibrated.plan"
        assert main.SaveProject(project) and main.OpenProject(project)
        assert reference.Snapshot() == saved and not calibration.active
        main.MarkProjectClean()
        main.close()


if __name__ == "__main__":
    Main()
