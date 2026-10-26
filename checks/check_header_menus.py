"""Header menu ordering, dummy actions, history actions and Stacker presentation."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall
from theme import BuildStyle
from planner_app.project_codec import DecodeProject


def Main():
    app = QtWidgets.QApplication([])
    try:
        QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
        app.setStyle("Fusion")
        app.setStyleSheet(BuildStyle())
        window = MainWindow()
        window.show()
        app.processEvents()
        expected = {
            "File": ["New Project", "Open Project", None, "Open Recent", None, "Revert", None, "Save Project", "Save Project as", None, "Save startup file", None, "Close Project"],
            "Edit": ["Undo", "Redo", None, "Cut", "Copy", "Paste", None, "Check for Problems…"],
            "Help": ["Help", "Keyboard shortcuts", None, "About"],
        }
        for name, labels in expected.items():
            menu = window.headerMenus[name]
            assert [None if action.isSeparator() else action.defaultWidget().accessibleName() for action in menu.actions()] == labels
            for action in menu.actions():
                if not action.isSeparator():
                    button = action.defaultWidget()
                    assert button.objectName() == "headerMenuItem" and not button.findChild(QtWidgets.QLabel, "menuIconLabel").pixmap().isNull()
        assert window.menuButtons["Cut"].shortcutLabel.text() == "Ctrl + X"
        assert window.menuButtons["Copy"].shortcutLabel.text() == "Ctrl + C"
        assert window.menuButtons["Paste"].shortcutLabel.text() == "Ctrl + V"
        window.ShowHeaderMenu("Edit")
        assert not window.menuButtons["Undo"].isEnabled() and not window.menuButtons["Redo"].isEnabled()
        window.editMenu.hide()
        viewport = window.viewport
        assert window.viewOptions["showGrid"].shortcutLabel.text() == "G"
        assert [None if action.isSeparator() else action.defaultWidget().accessibleName() for action in window.viewMenu.actions()] == [
            "Draw Grid", None, "Reference Image", None, "Toggle dimensions", None, "Maximize", None, "Show tips", "Show FPS counter"]
        assert not viewport.showFpsCounter and not viewport.performanceLabel.isVisible()
        assert viewport.showTips
        window.ShowViewMenu()
        assert not window.viewOptions["showTips"].iconLabel.pixmap().isNull()
        window.viewMenu.hide()
        tipsImage = viewport.grab().toImage()
        window.viewOptions["showTips"].click()
        assert not viewport.showTips and not window.viewMenu.isVisible()
        assert viewport.grab().toImage() != tipsImage
        window.ShowViewMenu()
        assert window.viewOptions["showTips"].iconLabel.pixmap().isNull()
        window.viewMenu.hide()
        tipsData = window.BuildProjectData(includeHistory = False)
        decodedTips = DecodeProject(tipsData, viewport.furnishingDefinitions)
        assert "showTips" not in tipsData["settings"] and "showTips" not in decodedTips[5]
        window.ApplyProject(decodedTips, None)
        assert not viewport.showTips
        window.viewOptions["showTips"].click()
        assert viewport.showTips
        tipsData["settings"]["showTips"] = False
        window.ApplyProject(DecodeProject(tipsData, viewport.furnishingDefinitions), None)
        assert viewport.showTips
        viewport.openingPlacementMode = "Door"
        placementTips = viewport.grab().toImage()
        window.viewOptions["showTips"].click()
        assert viewport.grab().toImage() != placementTips
        window.viewOptions["showTips"].click()
        viewport.openingPlacementMode = None
        window.ShowViewMenu()
        window.menuButtons["Maximize"].click()
        assert window.viewportOnlyMode and window.sidebarPanel.isHidden() and not window.viewMenu.isVisible()
        window.fullscreenButton.click()
        assert not window.viewportOnlyMode and window.sidebarPanel.isVisible()
        window.ShowSettings()
        panel = window.settingsWindow
        panel.SetMeasurementVisibility("stairs", True)
        assert viewport.showMeasurements and viewport.measurementVisibility["stairs"]
        assert "all" not in panel.measurementVisibilityItems
        window.ShowViewMenu()
        assert not window.viewOptions["showMeasurements"].iconLabel.pixmap().isNull()
        remembered = dict(viewport.measurementVisibility)
        window.viewOptions["showMeasurements"].click()
        assert not viewport.showMeasurements and viewport.measurementVisibility == remembered
        panel.SetMeasurementVisibility("counters", True)
        assert viewport.showMeasurements and viewport.measurementVisibility == dict(remembered, counters = True)
        window.viewOptions["showMeasurements"].click()
        window.viewOptions["showMeasurements"].click()
        assert viewport.showMeasurements and viewport.measurementVisibility == dict(remembered, counters = True)
        panel.hide()
        window.viewOptions["showFpsCounter"].click()
        assert viewport.performanceLabel.isVisible() and viewport.performanceTimer.isActive()
        data = window.BuildProjectData()
        assert "showFpsCounter" not in data["settings"] and "showFpsCounter" not in DecodeProject(data, viewport.furnishingDefinitions)[5]
        window.viewOptions["showFpsCounter"].click()
        assert not viewport.performanceLabel.isVisible() and not viewport.performanceTimer.isActive()
        data["settings"]["showFpsCounter"] = True
        window.ApplyProject(DecodeProject(data, viewport.furnishingDefinitions), None)
        assert not viewport.showFpsCounter
        window.ShowViewMenu()
        app.processEvents()
        window.viewMenu.grab().save("screenshots/view-menu.png")
        window.viewMenu.hide()
        before = viewport.CaptureState()
        wall = Wall(QtCore.QPointF(), QtCore.QPointF(2000, 0))
        viewport.walls.append(wall)
        viewport.RecordEdit(before)
        window.ShowHeaderMenu("Edit")
        assert window.menuButtons["Undo"].isEnabled()
        window.menuButtons["Undo"].click()
        assert not viewport.walls and not window.editMenu.isVisible() and not window.headerButtons["Edit"].isChecked()
        window.ShowHeaderMenu("Edit")
        assert window.menuButtons["Redo"].isEnabled()
        window.menuButtons["Redo"].click()
        assert viewport.walls == [wall]
        window.ShowHeaderMenu("Edit")
        QtTest.QTest.keyClick(window.editMenu, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
        assert not viewport.walls
        viewport.Redo()
        before = viewport.CaptureState()
        for name, labels in expected.items():
            for label in labels:
                if name == "File" or label is None or label in ("Undo", "Redo"):
                    continue
                window.ShowHeaderMenu(name)
                if not window.menuButtons[label].isEnabled():
                    window.headerMenus[name].hide()
                else:
                    window.menuButtons[label].click()
                assert viewport.CaptureState() == before and not window.headerMenus[name].isVisible()
        for name in expected:
            window.ShowHeaderMenu(name)
            app.processEvents()
            assert window.headerButtons[name].isChecked()
            window.headerMenus[name].grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / f"{name.lower()}-menu.png"))
            window.headerMenus[name].hide()
            assert not window.headerButtons[name].isChecked()
        window.close()
        print("PASS: menu ordering/separators/icons/hints, disabled empty history, menu undo/redo, Ctrl+Z in Edit and inert placeholders.")
    finally:
        app.clipboard().clear()
        app.processEvents()



if __name__ == "__main__":
    Main()
