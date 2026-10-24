"""Export-only undo, gesture coalescing and disabled construction controls."""
import copy
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets, QtTest
from planner import MainWindow, Wall
from planner_app.project_codec import DecodeProject


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    v, panel = main.viewport, main.exportPanel
    point = QtCore.QPointF
    wall = Wall(point(-1000, 0), point(1000, 0))
    v.walls = [wall]
    v.EnsureObjectIds()
    before = v.CaptureState()
    wall.secondVertex = point(1500, 0)
    v.RecordEdit(before)
    scene = v.CaptureState()
    historyCount = len(v.undoHistory)
    main.sidebarTabs.setCurrentWidget(panel)
    panel.ResetExportHistory()
    v.Undo()
    v.Redo()
    assert v.CaptureState() == scene and len(v.undoHistory) == historyCount
    assert not main.groupModeButton.isEnabled() and not main.transformOrientationButton.isEnabled()
    assert all(not button.isEnabled() for button in (*main.connectedOptions.values(), *main.groupActionButtons.values()))
    for key, modifiers in ((QtCore.Qt.Key.Key_T, QtCore.Qt.KeyboardModifier.NoModifier),
                           (QtCore.Qt.Key.Key_H, QtCore.Qt.KeyboardModifier.AltModifier),
                           (QtCore.Qt.Key.Key_H, QtCore.Qt.KeyboardModifier.ControlModifier),
                           (QtCore.Qt.Key.Key_Q, QtCore.Qt.KeyboardModifier.NoModifier),
                           (QtCore.Qt.Key.Key_V, QtCore.Qt.KeyboardModifier.ControlModifier),
                           (QtCore.Qt.Key.Key_G, QtCore.Qt.KeyboardModifier.ControlModifier)):
        QtTest.QTest.keyClick(v, key, modifiers)
    assert v.CaptureState() == scene and getattr(main, "moveSpecialWindow", None) is None
    panel.SetOverride("showGrid", False)
    assert not v.showGrid and len(panel.exportUndoHistory) == 1
    main.ShowHeaderMenu("Edit")
    assert main.menuButtons["Undo"].isEnabled() and not main.menuButtons["Redo"].isEnabled()
    assert all(not main.menuButtons[label].isEnabled() for label in ("Cut", "Copy", "Paste"))
    main.editMenu.hide()
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert "showGrid" not in panel.overrides and v.showGrid
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier)
    assert panel.overrides["showGrid"] is False and not v.showGrid
    panel.SetOverride("showGrid", True)
    panel.ResetExportHistory()
    slider = panel.gridSliders["overall"]
    slider.setSliderDown(True)
    for value in (800, 600, 450):
        slider.setValue(value)
    slider.setSliderDown(False)
    assert len(panel.exportUndoHistory) == 1
    v.Undo()
    assert "overall" not in panel.overrides.get("viewportSettings", {})
    v.Redo()
    assert panel.overrides["viewportSettings"]["overall"] == .45
    panel.ResetExportHistory()
    bounds = tuple(v.exportOverlay.bounds)
    panel.BeginExportGesture()
    for delta in (100, 200, 300):
        v.exportOverlay.MoveEdge(1, bounds[0] + bounds[2] + delta, modifiers = QtCore.Qt.KeyboardModifier.AltModifier)
    panel.EndExportGesture()
    assert len(panel.exportUndoHistory) == 1
    modifiedBounds = tuple(v.exportOverlay.bounds)
    v.Undo()
    assert tuple(v.exportOverlay.bounds) == bounds and "bounds" not in panel.overrides
    v.Redo()
    assert tuple(v.exportOverlay.bounds) == modifiedBounds
    panel.SetOverride("canvasColor", "#335577")
    colors = copy.deepcopy(panel.overrides)
    v.Undo()
    assert "canvasColor" not in panel.overrides
    v.Redo()
    assert panel.overrides == colors
    panel.ResetExportHistory()
    panel.BeginExportGesture()
    for origin in ([100, 0], [200, 0], [300, 100]):
        panel.SetOverride("gridOrigin", origin)
    panel.EndExportGesture()
    v.Undo()
    assert v.gridOrigin == (0, 0)
    v.Redo()
    assert v.gridOrigin == (300, 100)
    panel.ResetExportHistory()
    originalType = panel.typeField.currentData()
    panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
    assert len(panel.exportUndoHistory) == 1, (originalType, panel.typeField.currentData(), panel.exportUndoHistory, panel.exportGestureBefore)
    v.Undo()
    assert panel.typeField.currentData() == originalType and v.exportOverlay.outputFormat == "png"
    panel.SetOverride("border", "Plain")
    assert not panel.exportRedoHistory
    assert v.CaptureState() == scene and len(v.undoHistory) == historyCount
    panel.scaleField.setValue(125)
    panel.scaleField.setFocus()
    QtTest.QTest.keyClick(panel.scaleField, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert panel.ScalePerMeter() == 100
    QtTest.QTest.keyClick(panel.scaleField, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier)
    assert panel.ScalePerMeter() == 125
    v.Undo()
    main.sidebarTabs.setCurrentIndex(0)
    assert main.groupModeButton.isEnabled()
    v.Undo()
    assert wall.secondVertex == point(1000, 0)
    v.Redo()
    assert wall.secondVertex == point(1500, 0)
    main.sidebarTabs.setCurrentWidget(panel)
    v.Undo()
    assert "border" not in panel.overrides and wall.secondVertex == point(1500, 0)
    data = main.BuildProjectData()
    main.ApplyProject(DecodeProject(data, v.furnishingDefinitions), None)
    assert not panel.exportUndoHistory and not panel.exportRedoHistory
    for index in range(105):
        panel.SetScaleOption("scale", 100 + index)
    assert len(panel.exportUndoHistory) == 100
    main.close()
    app.processEvents()
    print("PASS: independent export undo/redo, sliders, bounds, colors, formats, project resets and scene isolation.")


if __name__ == "__main__":
    Main()
