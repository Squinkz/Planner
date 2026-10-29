"""Export blocks editor shortcuts while retaining controls, navigation and history."""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall
from planner_app.project_codec import EncodeScene
from planner_app.graphics.palette import themeColors


def Main():
    with ExampleWindow() as (main, folder):
        v, panel = main.viewport, main.exportPanel
        InstallScene(main, [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), 240)])
        v.showGrid = v.showMeasurements = True
        main.sidebarTabs.setCurrentWidget(panel)
        for button in (*main.connectedOptions.values(), main.groupModeButton, main.transformOrientationButton):
            assert not button.isEnabled()
            image = button.grab().toImage()
            ratio = image.devicePixelRatioF()
            assert image.pixelColor(round(2 * ratio), round(20 * ratio)) == QtGui.QColor(themeColors["controlBackground"]), button.accessibleName()
        initialScene = EncodeScene(v)
        initialSettings = copy.deepcopy(main.ProjectSettings())
        initialOverrides = copy.deepcopy(panel.overrides)
        no = QtCore.Qt.KeyboardModifier.NoModifier
        ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
        alt = QtCore.Qt.KeyboardModifier.AltModifier
        shift = QtCore.Qt.KeyboardModifier.ShiftModifier
        keys = [(key, no) for key in (QtCore.Qt.Key.Key_G, QtCore.Qt.Key.Key_M, QtCore.Qt.Key.Key_B,
                                     QtCore.Qt.Key.Key_Q, QtCore.Qt.Key.Key_W, QtCore.Qt.Key.Key_D,
                                     QtCore.Qt.Key.Key_S, QtCore.Qt.Key.Key_T, QtCore.Qt.Key.Key_H,
                                     QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Space,
                                     QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right)]
        keys += [(key, ctrl) for key in (QtCore.Qt.Key.Key_A, QtCore.Qt.Key.Key_C, QtCore.Qt.Key.Key_X,
                                        QtCore.Qt.Key.Key_V, QtCore.Qt.Key.Key_G, QtCore.Qt.Key.Key_H)]
        keys += [(key, alt) for key in (QtCore.Qt.Key.Key_B, QtCore.Qt.Key.Key_G, QtCore.Qt.Key.Key_H)]
        keys += [(QtCore.Qt.Key.Key_A, ctrl | shift), (QtCore.Qt.Key.Key_V, ctrl | shift)]
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", side_effect = AssertionError("Export opened an image picker")):
            for key, modifiers in keys:
                v.setFocus()
                QtTest.QTest.keyClick(v, key, modifiers)
                QtWidgets.QApplication.processEvents()
                assert main.sidebarTabs.currentWidget() is panel, (key, modifiers)
                assert main.ProjectSettings() == initialSettings, (key, modifiers)
                assert panel.overrides == initialOverrides and EncodeScene(v) == initialScene
                assert v.openingPlacementMode is None and not main.referenceImage.active
            for option in ("showGrid", "showMeasurements", "referenceImage", "editReferenceImage", *v.measurementVisibility):
                main.SetViewOption(option)
            assert not main.referenceImage.Browse() and not main.referenceImage.Load(folder / "missing.png")
            main.referenceImage.ToggleVisibility(True)
            main.referenceImage.Show()
        assert main.ProjectSettings() == initialSettings and panel.overrides == initialOverrides
        assert all(not shortcut.isEnabled() for shortcut in main.editorShortcuts)
        shortcuts = {shortcut.key().toString(): shortcut.isEnabled() for shortcut in main.findChildren(QtGui.QShortcut)}
        for key in ("Ctrl+N", "Ctrl+O", "Ctrl+S", "Ctrl+Shift+S", "Ctrl+W", "F1", "Alt+P"):
            assert shortcuts[key], key
        main.ShowViewMenu()
        for option in ("showGrid", "showMeasurements", "referenceImage"):
            assert not main.viewOptions[option].isEnabled()
            main.viewOptions[option].click()
        assert not main.menuButtons["Setup Reference Image"].isEnabled()
        main.viewMenu.hide()
        main.ShowHeaderMenu("Edit")
        assert all(not main.menuButtons[name].isEnabled() for name in ("Cut", "Copy", "Paste"))
        main.editMenu.hide()
        field = panel.titleBlockFields["projectName"]
        panel.titleBlockEnabled.setChecked(True)
        panel.sectionButtons["Title Block"].setChecked(True)
        panel.scrollArea.ensureWidgetVisible(field)
        field.setFocus()
        QtTest.QTest.keyClick(field, QtCore.Qt.Key.Key_A, ctrl)
        QtTest.QTest.keyClicks(field, "g m b q w d s t h")
        assert field.text() == "g m b q w d s t h"
        panel.ResetExportHistory()
        beforeGrid = v.showGrid
        panel.showGridField.setChecked(not beforeGrid)
        assert v.showGrid != beforeGrid
        v.setFocus()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Z, ctrl)
        assert v.showGrid == beforeGrid
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Z, ctrl | shift)
        assert v.showGrid != beforeGrid
        panel.measurementVisibilityItems["all"].setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        assert not v.showMeasurements
        groupMode = v.groupModeEnabled
        v.setFocus()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Tab, ctrl)
        assert v.groupModeEnabled == groupMode
        main.sidebarTabs.setCurrentWidget(panel)
        orientation = v.localTransforms
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Tab)
        assert v.localTransforms == orientation
        v.setFocus()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_F)
        assert main.viewportOnlyMode
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Escape)
        assert not main.viewportOnlyMode
        v.setFocus()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_1)
        assert main.sidebarTabs.currentWidget() is main.buildScrollArea
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_4)
        assert main.sidebarTabs.currentWidget() is panel and v.exportOverlay.active
        main.sidebarTabs.setCurrentWidget(main.buildScrollArea)
        assert all(shortcut.isEnabled() for shortcut in main.editorShortcuts)
        previousGrid = v.showGrid
        v.setFocus()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_G)
        assert v.showGrid != previousGrid
        image = QtGui.QImage(32, 32, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtCore.Qt.GlobalColor.white)
        imagePath = folder / "reference.png"
        assert image.save(str(imagePath)) and main.referenceImage.Load(imagePath)
        reference = copy.deepcopy(main.referenceImage.state)
        main.sidebarTabs.setCurrentWidget(panel)
        main.ShowViewMenu()
        assert not main.menuButtons["Setup Reference Image"].isEnabled()
        main.viewMenu.hide()
        for modifiers in (no, alt):
            v.setFocus()
            QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_B, modifiers)
        assert main.referenceImage.state == reference and not main.referenceImage.active
        main.sidebarTabs.setCurrentWidget(main.buildScrollArea)
        v.setFocus()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_B, alt)
        assert main.referenceImage.active
        projectPath = folder / "shortcut-save.plan"
        assert main.SaveProjectAs(projectPath)
        main.sidebarTabs.setCurrentWidget(panel)
        panel.showGridField.setChecked(not v.showGrid)
        v.setFocus()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_S, ctrl)
        assert main.sidebarTabs.currentWidget() is main.buildScrollArea
        assert projectPath.is_file() and not main.projectDirty
    print("Export shortcut audit passed")


if __name__ == "__main__":
    Main()
