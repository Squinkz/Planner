"""Measurement modes split the correct wall sides and persist per project."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from planner import MainWindow, Wall, Door, Window, SilledWindow, SlidingDoor, PocketDoor, OpenDoorway
from planner_app.project_codec import DecodeProject
from planner_app.graphics.icons import UiIcon
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    main.ShowSettings()
    app.processEvents()
    panel = main.settingsWindow
    panel.tabs.setCurrentIndex(1)
    app.processEvents()
    v = main.viewport
    assert panel.tabs.tabText(1) == "Dimensions"
    assert panel.tabs.tabIcon(1).pixmap(18, 18).toImage() == UiIcon("measure").pixmap(18, 18).toImage()
    precisionBottom = panel.precisionField.mapTo(panel, QtCore.QPoint(0, panel.precisionField.height())).y()
    tree = panel.measurementVisibilityTree
    root = panel.drawDimensionsItem
    assert precisionBottom < panel.measurementHeading.mapTo(panel, QtCore.QPoint()).y()
    assert panel.unitsField.mapTo(panel, QtCore.QPoint()).y() == panel.precisionField.mapTo(panel, QtCore.QPoint()).y()
    assert panel.unitsField.mapTo(panel, QtCore.QPoint()).x() < panel.precisionField.mapTo(panel, QtCore.QPoint()).x()
    assert panel.measurementHeading.titleLabel.text() == "Measure"
    assert any(label.text() == "Canvas precision" and label.buddy() is panel.precisionField
               for label in panel.measurementPage.findChildren(QtWidgets.QLabel))
    assert panel.gridHeading.titleLabel.text() == "Grid"
    assert panel.gridHeading.objectName() == panel.measurementHeading.objectName() == "sectionHeading"
    assert tree.mapTo(panel, tree.rect().bottomLeft()).y() < panel.gridHeading.mapTo(panel, QtCore.QPoint()).y()
    assert panel.gridHeading.mapTo(panel, panel.gridHeading.rect().bottomLeft()).y() < panel.showGridField.mapTo(panel, QtCore.QPoint()).y()
    panel.gridAppearanceButton.click()
    assert panel.tabs.currentWidget() is panel.appearanceTab
    panel.tabs.setCurrentIndex(1)
    if not v.showGrid:
        panel.showGridField.click()
    savedGridIntensities = dict(v.gridIntensities)
    panel.showGridField.click()
    assert not v.showGrid and not panel.gridAppearanceHeading.isEnabled()
    assert all(not widget.isEnabled() for row in panel.gridAppearanceRows for widget in row)
    assert all(not widget.isEnabled() for widget in list(panel.sliders.values()) + list(panel.valueFields.values()) + list(panel.resetButtons.values()))
    assert all(widget.isEnabled() for widget in panel.lineworkSliders.values())
    panel.showGridField.click()
    assert v.showGrid and panel.gridAppearanceHeading.isEnabled()
    assert all(widget.isEnabled() for row in panel.gridAppearanceRows for widget in row)
    assert v.gridIntensities == savedGridIntensities
    assert tree.topLevelItemCount() == 1 and root.childCount() == 4
    assert root.text(0) == "Draw dimensions" and root.isExpanded()
    assert [root.child(index).text(0) for index in range(root.childCount())] == [
        "Walls", "Stairs", "Counters", "Railings"]
    rootRect = tree.visualItemRect(root)
    for item in panel.measurementVisibilityItems.values():
        assert item.parent() is root and tree.visualItemRect(item).left() == rootRect.left() + 24
    assert tree.height() == 160
    root.setExpanded(False)
    app.processEvents()
    assert tree.height() == 32 and v.measurementVisibility["walls"]
    root.setExpanded(True)
    app.processEvents()
    assert tree.height() == 160
    assert v.measurementSettings == {"doors": 1, "windows": 1, "stairs": 2, "counters": 2}
    assert panel.wallMeasurementModeField.currentText() == "Exterior stacked"
    panel.wallMeasurementModeField.setCurrentText("All")
    savedSplits = dict(v.measurementSettings)
    panel.SetMeasurementVisibility("stairs", True)
    panel.SetMeasurementVisibility("walls", False)
    assert v.showMeasurements and not panel.wallMeasurementModeField.isEnabled()
    assert not panel.wallMeasurementModeLabel.isEnabled()
    assert all(not slider.isEnabled() for slider in panel.measurementSliders.values())
    assert all(not button.isEnabled() for button in panel.measurementResetButtons.values())
    panel.SetMeasurementVisibility("walls", True)
    panel.SetMeasurementVisibility("stairs", False)
    assert panel.wallMeasurementModeField.isEnabled()
    assert all(slider.isEnabled() for slider in panel.measurementSliders.values())
    main.SetViewOption("showMeasurements")
    assert not panel.wallMeasurementModeField.isEnabled()
    assert all(not slider.isEnabled() for slider in panel.measurementSliders.values())
    main.SetViewOption("showMeasurements")
    assert panel.wallMeasurementModeField.isEnabled()
    assert v.measurementSettings == savedSplits and v.wallMeasurementMode == "All"
    splitTabs = panel.measurementSplitTabs
    assert [splitTabs.tabText(index) for index in range(splitTabs.count())] == ["Doors", "Windows", "Stairs", "Counters"]
    assert splitTabs.currentIndex() == 0
    splitHeights = {}
    for index, key in enumerate(("doors", "windows", "stairs", "counters")):
        splitTabs.setCurrentIndex(index)
        app.processEvents()
        assert panel.measurementSliders[key].isVisibleTo(splitTabs)
        assert all(not slider.isVisibleTo(splitTabs) for other, slider in panel.measurementSliders.items() if other != key)
        splitHeights[key] = splitTabs.height()
        page = splitTabs.currentWidget()
        slider = panel.measurementSliders[key]
        assert page.rect().contains(slider.mapTo(page, slider.rect().topLeft()))
        assert page.rect().contains(slider.mapTo(page, slider.rect().bottomRight()))
    assert splitHeights["doors"] == splitHeights["windows"]
    assert splitHeights["stairs"] == splitHeights["counters"]
    assert splitHeights["doors"] - splitHeights["stairs"] == 112 - 49
    splitTabs.setCurrentIndex(0)
    panel.SetWallMeasurementMode("Exterior")
    app.processEvents()
    assert splitTabs.height() == splitHeights["stairs"]
    panel.SetWallMeasurementMode("All")
    app.processEvents()
    assert splitTabs.height() == splitHeights["doors"]
    splitTabs.setCurrentIndex(1)
    panel.SetWallMeasurementMode("Exterior stacked")
    assert not panel.measurementSplitWidget.isVisible()
    panel.SetWallMeasurementMode("All")
    assert splitTabs.currentIndex() == 1 and panel.measurementSplitWidget.isVisible()
    for key, slider in panel.measurementSliders.items():
        assert slider.minimum() == 0 and slider.maximum() == (1 if key in ("stairs", "counters") else 2) and slider.invertedAppearance()
    for key in ("doors", "windows"):
        splitTabs.setCurrentIndex(0 if key == "doors" else 1)
        labels = [label for label in panel.measurementPage.findChildren(QtWidgets.QLabel)
                  if label.property("measurementKey") == key]
        slider = panel.measurementSliders[key]
        panel.tabs.currentWidget().ensureWidgetVisible(slider)
        app.processEvents()
        QtTest.QTest.mouseClick(labels[0], QtCore.Qt.MouseButton.LeftButton)
        assert slider.value() == 0
        QtTest.QTest.mousePress(labels[0], QtCore.Qt.MouseButton.LeftButton)
        bottom = labels[0].mapFromGlobal(labels[2].mapToGlobal(labels[2].rect().center()))
        QtTest.QTest.mouseMove(labels[0], bottom)
        assert slider.value() == 2
        QtTest.QTest.mouseRelease(labels[0], QtCore.Qt.MouseButton.LeftButton, pos = bottom)
        assert not slider.isSliderDown() and panel.measurementDragging is None
        for control in (labels[1], slider):
            slider.setValue(2)
            for expected in (1, 0):
                position = QtCore.QPointF(control.rect().center())
                wheel = QtGui.QWheelEvent(position, QtCore.QPointF(control.mapToGlobal(position.toPoint())),
                                         QtCore.QPoint(), QtCore.QPoint(0, 120), QtCore.Qt.MouseButton.NoButton,
                                         QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
                app.sendEvent(control, wheel)
                assert slider.value() == expected
        panel.measurementResetButtons[key].click()
    point = QtCore.QPointF
    # Rotated and reversed walls must keep the same facing-side interpretation.
    for endpoint in (point(5000, 0), point(0, 5000), point(3000, 4000)):
        for reverse in (False, True):
            wall = Wall(endpoint, point()) if reverse else Wall(point(), endpoint)
            axis = (wall.secondVertex - wall.firstVertex) / 5000
            normal = point(-axis.y(), axis.x())
            path = v.ConnectedWallPath([wall])
            for cls in (Door, Window, SilledWindow, SlidingDoor, PocketDoor, OpenDoorway):
                opening = cls(wall, .2, .4)
                key = "doors" if cls in (Door, SlidingDoor, PocketDoor, OpenDoorway) else "windows"
                v.windows = [opening]
                for flipped in (False, True):
                    if hasattr(opening, "swingsOutwards"):
                        opening.swingsOutwards = flipped
                    elif isinstance(opening, SlidingDoor):
                        opening.panelsFlipped = flipped
                    for mode in (0, 1, 2):
                        panel.measurementSliders[key].setValue(mode)
                        spans = v.WallDimensions([wall], path)
                        facing = -normal if flipped else normal
                        counts = [sum(point.dotProduct((first + second) / 2 - wall.firstVertex, facing) * side > 0
                                      for first, second, owners in spans) for side in (1, -1)]
                        expected = [1, 1] if mode == 2 else ([3, 1] if mode == 1 and
                                   cls not in (PocketDoor, OpenDoorway) else [3, 3])
                        assert counts == expected, (cls.__name__, mode, flipped, counts)
    v.windows = []
    panel.SetMeasurementMode("doors", 0)
    panel.SetMeasurementMode("windows", 1)
    app.processEvents()
    assert main.projectDirty
    panel.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "measurement-settings.png"))
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "Measurements.plan"
        assert main.SaveProject(path)
        panel.measurementResetButtons["doors"].click()
        assert v.measurementSettings["doors"] == 1
        assert not panel.measurementResetButtons["doors"].isEnabled()
        assert main.NewProject() and v.measurementSettings == {"doors": 1, "windows": 1, "stairs": 2, "counters": 2}
        assert main.OpenProject(path) and v.measurementSettings == {"doors": 0, "windows": 1, "stairs": 2, "counters": 2}
        assert panel.measurementSliders["doors"].value() == 0
        assert not main.projectDirty
        legacy = main.BuildProjectData()
        del legacy["settings"]["measurementSettings"]
        assert DecodeProject(legacy, v.furnishingDefinitions)[5]["measurementSettings"] == {"doors": 1, "windows": 1, "stairs": 2, "counters": 2}
        legacy["settings"]["measurementSettings"] = {"doors": True, "windows": 1}
        try:
            DecodeProject(legacy, v.furnishingDefinitions)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid measurement mode accepted")
    main.close()
    restored = MainWindow()
    assert restored.viewport.measurementSettings == {"doors": 0, "windows": 1, "stairs": 2, "counters": 2}
    assert not restored.projectDirty
    restored.close()
    print("PASS: Measurement controls, all modes/orientations/types, resets, cache invalidation, project validation and recovery.")


if __name__ == "__main__":
    Main()
