"""Configurable wall/opening defaults apply to placement and recover on launch."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, Door, SlidingDoor, PocketDoor, OpenDoorway, Window, SilledWindow
from planner_app.models import Railing, Pillar
from planner_app.preferences import miscDefaultSizes
from planner_app.project_codec import DecodeProject
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    main.ShowSettings()
    settings = main.settingsWindow
    assert settings.tabs.tabText(0) == "Build" and settings.tabs.tabText(1) == "Dimensions" and settings.tabs.tabText(2) == "Appearance"
    assert main.viewport.unitsMode == "Millimeters"
    assert [settings.sizeFields[index].value() for index in range(4)] == [100, 150, 200, 300]
    assert all(field.suffix() == " mm" for field in settings.sizeFields.values())
    assert set(settings.buildResetButtons) == {0, 1, 2, 3, "Door", "DoubleDoor", "SwingingDoor", "SlidingDoor", "PocketDoor", "BarnDoor", "BifoldDoor",
                                                "OpenDoorway", "Window", "SilledWindow", "CasementWindow", "AwningWindow", "DoubleCasementWindow", "Stair", "Counter",
                                                "Railing", "Pillar", "Column", "Fireplace", "Elevator"}
    assert [settings.buildTabs.tabText(index) for index in range(settings.buildTabs.count())] == ["General", "Walls", "Doors", "Windows", "Misc"]
    assert all(not button.isEnabled() for button in settings.buildResetButtons.values())
    assert settings.buildScrollArea.verticalScrollBar().maximum() == 0
    with patch.object(settings, "screen", return_value = SimpleNamespace(availableGeometry = lambda: QtCore.QRect(0, 0, 600, 400))):
        settings.FitToContents()
        app.processEvents()
        assert settings.frameGeometry().height() <= 400
        assert settings.buildScrollArea.verticalScrollBar().maximum() > 0
    settings.FitToContents()
    app.processEvents()
    assert settings.buildScrollArea.verticalScrollBar().maximum() == 0
    v = main.viewport
    main.snapButton.setChecked(False)
    point = QtCore.QPointF
    existing = Wall(point(-2500, 0), point(2500, 0), 120)
    before = v.CaptureState()
    v.walls.append(existing)
    v.RecordEdit(before)
    for index, value in enumerate((9, 13, 17, 31)):
        settings.sizeFields[index].setValue(value * 10)
    assert main.wallWidthSelector.widths == (9, 13, 17, 31) and v.newWallWidth == 170
    assert existing.width == 120
    for index, width in enumerate(v.wallPresetWidths):
        main.wallWidthSelector.slider.setValue(index)
        assert v.newWallWidth == width * 10
    position = v.WorldToViewport(point())
    types = (Door, SlidingDoor, PocketDoor, OpenDoorway, Window, SilledWindow)
    sizes = (100, 110, 80, 140, 150, 170)
    for cls, size in zip(types, sizes):
        settings.sizeFields[cls.__name__].setValue(size * 10)
        expected = size * (20 if cls in (SlidingDoor, PocketDoor) else 10)
        assert v.InactiveOpening(point(0, 2000), cls).length == expected
        preview = v.FindWindowPlacement(position, openingType = cls)
        assert preview is not None and abs(preview.length - expected) < 1e-8
        v.UpdateOpeningPreview(position, cls, QtCore.Qt.KeyboardModifier.NoModifier)
        assert abs(v.windowDropPreview.length - expected) < 1e-8
        placed = v.PlaceWindow(position, openingType = cls)
        assert placed is not None and abs(placed.length - expected) < 1e-8
        before = v.CaptureState()
        v.windows.remove(placed)
        v.RecordEdit(before)
    # Editing defaults must not resize an already-placed opening.
    oldDoor = v.PlaceWindow(position, openingType = Door)
    settings.sizeFields["Door"].setValue(1050)
    assert abs(oldDoor.length - 1000) < 1e-8
    # Defaults affect new placement, while pillars start square and retain the
    # wall tool's material. Existing objects and copied stairs retain their size.
    oldStair = v.FindStairPlacement(v.WorldToViewport(point(10000, 10000)))
    for key, size in (("Stair", 110), ("Counter", 70), ("Railing", 12), ("Pillar", 45), ("Column", 45), ("Fireplace", 144), ("Elevator", 150)):
        settings.sizeFields[key].setValue(size * 10)
        assert v.miscDefaultSizes[key] == size
    position = v.WorldToViewport(point(10000, 10000))
    assert v.FindStairPlacement(position).width == 1100
    assert oldStair.width == 1000 and v.FindStairPlacement(position, source = oldStair).width == 1000
    assert v.FindCounterPlacement(position, QtCore.Qt.KeyboardModifier.NoModifier).width == 700
    assert v.FindArrowPlacement(position, QtCore.Qt.KeyboardModifier.NoModifier, Railing).width == 120
    v.newWallMaterial = "Brick"
    pillar = v.FindArrowPlacement(position, QtCore.Qt.KeyboardModifier.NoModifier, Pillar)
    assert pillar.width == pillar.length == 450 and pillar.material == "Brick"
    data = main.BuildProjectData()
    del data["settings"]["buildSettings"]["miscSizes"]
    assert DecodeProject(data, v.furnishingDefinitions)[5]["buildSettings"]["miscSizes"] == miscDefaultSizes
    for key, field in settings.sizeFields.items():
        if key in ("BarnDoor", "BifoldDoor", "CasementWindow", "AwningWindow", "DoubleCasementWindow", "SwingingDoor", "DoubleDoor"):
            field.setValue(1000)
        value = field.value()
        assert settings.buildResetButtons[key].isEnabled()
        settings.buildResetButtons[key].click()
        assert not settings.buildResetButtons[key].isEnabled()
        if isinstance(key, int):
            assert v.wallPresetWidths[key] * 10 == field.value()
            assert main.wallWidthSelector.widths[key] * 10 == field.value()
        elif key in v.miscDefaultSizes:
            assert v.miscDefaultSizes[key] * 10 == field.value()
        else:
            assert v.openingDefaultSizes[key] * 10 == field.value()
        field.setValue(value)
    defaults = (list(v.wallPresetWidths), dict(v.openingDefaultSizes), dict(v.miscDefaultSizes))
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "Custom.plan"
        assert main.SaveProject(path) and main.OpenProject(path)
        assert v.newWallWidth == 310 and v.walls[0].width == 120
        assert main.NewProject() and v.newWallWidth == 200
        assert v.wallPresetWidths == [10, 15, 20, 30]
        assert v.miscDefaultSizes == miscDefaultSizes
        assert settings.sizeFields["Door"].value() == 900
        assert main.OpenProject(path)
        assert (v.wallPresetWidths, v.openingDefaultSizes, v.miscDefaultSizes) == defaults
        assert settings.sizeFields["Door"].value() == 1050
        settings.sizeFields["Door"].setValue(1060)
        app.processEvents()
        assert main.projectDirty
        settings.buildResetButtons["Door"].click()
        assert settings.sizeFields["Door"].value() == 900
        settings.sizeFields["Door"].setValue(1050)
        app.processEvents()
        assert not main.projectDirty
    app.processEvents()
    settings.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "build-settings.png"))
    settings.buildTabs.setCurrentIndex(4)
    settings.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "build-misc-settings.png"))
    main.close()
    restored = MainWindow()
    assert (restored.viewport.wallPresetWidths, restored.viewport.openingDefaultSizes, restored.viewport.miscDefaultSizes) == defaults
    assert restored.wallWidthSelector.widths == tuple(defaults[0])
    restored.ShowSettings()
    assert restored.settingsWindow.sizeFields["Door"].value() == 1050
    restored.close()
    print("PASS: Build ordering/icons, configurable presets, all opening placement paths, existing geometry retained, custom project widths and recovery.")


if __name__ == "__main__":
    Main()
