"""Structural cuts, exposed edges, visibility hierarchy and project compatibility."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from planner import MainWindow, Wall, Stair, Counter
from planner_app.models import Furnishing, Railing
from planner_app.project_codec import DecodeProject
from planner_app.graphics.theme import ApplyApplicationTheme


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.show()
    main.ShowSettings()
    panel = main.settingsWindow
    panel.tabs.setCurrentIndex(1)
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    for key in ("stairs", "counters"):
        slider = panel.measurementSliders[key]
        labels = [label for label in panel.measurementPage.findChildren(QtWidgets.QLabel)
                  if label.property("measurementKey") == key]
        assert len(labels) == 2 and slider.maximum() == 1 and slider.value() == 1
        doorLabels = [label for label in panel.measurementPage.findChildren(QtWidgets.QLabel)
                      if label.property("measurementKey") == "doors"]
        referenceSpacing = doorLabels[1].mapTo(panel, doorLabels[1].rect().center()).y() - doorLabels[0].mapTo(panel, doorLabels[0].rect().center()).y()
        actualSpacing = labels[1].mapTo(panel, labels[1].rect().center()).y() - labels[0].mapTo(panel, labels[0].rect().center()).y()
        # Two and three label layouts distribute integer pixels differently with the bundled font.
        assert abs(actualSpacing - referenceSpacing) <= 2, (actualSpacing, referenceSpacing, labels[0].height(), slider.height())
        QtTest.QTest.mouseClick(labels[0], QtCore.Qt.MouseButton.LeftButton)
        assert v.measurementSettings[key] == 0
        QtTest.QTest.mousePress(labels[0], QtCore.Qt.MouseButton.LeftButton)
        bottom = labels[0].mapFromGlobal(labels[1].mapToGlobal(labels[1].rect().center()))
        QtTest.QTest.mouseMove(labels[0], bottom)
        QtTest.QTest.mouseRelease(labels[0], QtCore.Qt.MouseButton.LeftButton, pos = bottom)
        assert v.measurementSettings[key] == 2
        position = QtCore.QPointF(slider.rect().center())
        wheel = QtGui.QWheelEvent(position, QtCore.QPointF(slider.mapToGlobal(position.toPoint())),
                                 QtCore.QPoint(), QtCore.QPoint(0, 120), QtCore.Qt.MouseButton.NoButton,
                                 QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        app.sendEvent(slider, wheel)
        assert v.measurementSettings[key] == 0
        panel.measurementResetButtons[key].click()
        assert v.measurementSettings[key] == 2
    stair = Stair(point(), point(2000, 0), 600)
    for blocker in (None, Wall(point(500, 420), point(1500, 420), 240),
                    Counter(point(500, 600), point(1500, 600), 600),
                    Furnishing({"width": 1000, "length": 600}, point(1000, 600))):
        v.walls = [stair] + ([blocker] if isinstance(blocker, Wall) else [])
        v.furnishings = [blocker] if isinstance(blocker, Furnishing) else []
        v.ConnectedStairPath([stair])
        spans = v.StairDimensions([stair])
        assert len(spans) == (4 if blocker is None else 5), len(spans)
        if blocker is not None:
            blocker.firstVertex += point(0, 1000)
            blocker.secondVertex += point(0, 1000)
            assert len(v.StairDimensions([stair])) == 4
    v.furnishings = []
    wall = Wall(point(), point(4000, 0), 240)
    for cls, key in ((Stair, "stairs"), (Counter, "counters")):
        blocker = cls(point(1500, 420), point(2500, 420), 600)
        v.walls = [wall, blocker]
        path = v.ConnectedWallPath([wall])
        assert len(v.WallDimensions([wall], path)) == 2
        panel.SetMeasurementMode(key, 0)
        dimensions = v.WallDimensions([wall], path)
        assert len(dimensions) == 4
        assert sorted(round(QtCore.QLineF(first, second).length()) for first, second, owners in dimensions) == [1000, 1500, 1500, 4000]
        blocker.firstVertex += point(0, 1000)
        blocker.secondVertex += point(0, 1000)
        assert len(v.WallDimensions([wall], path)) == 2
        panel.SetMeasurementMode(key, 2)
    # A contact on only the upper edge must leave the opposite measurement intact.
    # Repeat rotated/reversed and with multiple independent wall components.
    for cls, key in ((Stair, "stairs"), (Counter, "counters")):
        panel.SetMeasurementMode(key, 0)
        for angle in (0, 37, 90):
            transform = QtGui.QTransform().rotate(angle)
            for reverse in (False, True):
                first, second = transform.map(point()), transform.map(point(4000, 0))
                wall = Wall(second, first, 240) if reverse else Wall(first, second, 240)
                blocker = cls(transform.map(point(1500, 420)), transform.map(point(2500, 420)), 600)
                distant = Wall(point(10000, 10000), point(14000, 10000), 240)
                v.walls = [wall, blocker, distant]
                path = v.ConnectedWallPath([wall, distant])
                dimensions = v.WallDimensions([wall, distant], path, cachedBoundary = True)
                assert len(dimensions) == 6
                lengths = sorted(round(QtCore.QLineF(first, second).length()) for first, second, owners in dimensions)
                assert lengths == [1000, 1500, 1500, 4000, 4000, 4000]
                offset = transform.map(point(0, 1))
                blocker.firstVertex += offset
                blocker.secondVertex += offset
                assert len(v.WallDimensions([wall, distant], path, cachedBoundary = True)) == 4
        panel.SetMeasurementMode(key, 2)
    # A joined landing reaches half a width beyond the control vertex.
    # The wall-side cut must use that outside corner, with no internal cuts
    # from the separate footprint rectangles/triangles or on the far wall side.
    for cls, key in ((Stair, "stairs"), (Counter, "counters")):
        panel.SetMeasurementMode(key, 0)
        for angle in (0, 37, 90):
            transform = QtGui.QTransform().rotate(angle)
            wall = Wall(transform.map(point(-2500, -620)), transform.map(point(1500, -620)), 240)
            joined = [cls(transform.map(point(-3000, 0)), transform.map(point()), 1000),
                      cls(transform.map(point()), transform.map(point(0, 3000)), 1000)]
            v.walls = [wall] + joined
            path = v.ConnectedWallPath([wall])
            dimensions = v.WallDimensions([wall], path, cachedBoundary = True)
            lengths = sorted(round(QtCore.QLineF(first, second).length()) for first, second, owners in dimensions)
            assert lengths == [1000, 3000, 4000], (cls.__name__, angle, lengths)
            inverse, invertible = transform.inverted()
            assert invertible
            nearSide = [(inverse.map(first), inverse.map(second)) for first, second, owners in dimensions
                        if abs(inverse.map((first + second) / 2).y() + 500) < .01]
            assert len(nearSide) == 2
            assert all(min(abs(first.x() - 500), abs(second.x() - 500)) < .02 for first, second in nearSide)
        panel.SetMeasurementMode(key, 2)
    # Exercise the category gates independently of factory visibility defaults.
    panel.SetMeasurementVisibility("stairs", True)
    panel.SetMeasurementVisibility("counters", True)
    items = panel.measurementVisibilityItems
    tree = panel.measurementVisibilityTree
    assert items["all"].text(0) == "Show measurements"
    assert tree.topLevelItemCount() == 1 and items["all"].childCount() == 5

    def Toggle(key):
        tree.setCurrentItem(items[key])
        QtTest.QTest.keyClick(tree, QtCore.Qt.Key.Key_Space)
    # Capture the actual rendered dimension text, including each class gate.
    from planner_app.viewport import rendering
    originalFormat = rendering.FormatLength
    renderedLengths = []

    def RecordLength(length, *args, **kwargs):
        renderedLengths.append(round(length))
        return originalFormat(length, *args, **kwargs)

    rendering.FormatLength = RecordLength
    v.walls = [Wall(point(), point(4000, 0), 240),
               Stair(point(0, 2000), point(2000, 2000), 600),
               Counter(point(0, -2000), point(3000, -2000), 600),
               Railing(point(0, -3200), point(2500, -3200), 80)]
    v.zoom = .4
    v.panOffset = point(-160, 0)
    assert not v.measurementVisibility["railings"]
    assert items["railings"].checkState(0) == QtCore.Qt.CheckState.Unchecked
    v.measurementPictures = ()  # Observe formatting on a cold annotation build.
    renderedLengths.clear()
    v.grab()
    assert 2500 not in renderedLengths
    main.SetViewOption("railings")
    assert items["railings"].checkState(0) == QtCore.Qt.CheckState.Checked
    assert DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)[5]["measurementVisibility"]["railings"]
    panel.SetMeasurementVisibility("walls", False)
    v.measurementPictures = ()  # Observe formatting on a cold annotation build.
    renderedLengths.clear()
    v.grab()
    assert 2500 in renderedLengths and 4000 not in renderedLengths
    panel.SetMeasurementVisibility("walls", True)
    Toggle("railings")
    v.measurementPictures = ()  # Observe formatting on a cold annotation build.
    renderedLengths.clear()
    v.grab()
    assert 2500 not in renderedLengths and 4000 in renderedLengths
    legacy = main.BuildProjectData()
    del legacy["settings"]["measurementVisibility"]["railings"]
    expectedVisibility = dict(legacy["settings"]["measurementVisibility"], railings = False)
    assert DecodeProject(legacy, v.furnishingDefinitions)[5]["measurementVisibility"] == expectedVisibility
    for key, length in (("walls", 4000), ("stairs", 2000), ("counters", 3000)):
        v.measurementPictures = ()  # Observe formatting on a cold annotation build.
        renderedLengths.clear()
        v.viewportSceneKey = None
        v.grab()
        assert length in renderedLengths, (key, renderedLengths)
        Toggle(key)
        v.measurementPictures = ()  # Observe formatting on a cold annotation build.
        renderedLengths.clear()
        v.grab()
        assert length not in renderedLengths, (key, renderedLengths)
        Toggle(key)
    rendering.FormatLength = originalFormat
    Toggle("stairs")
    assert not v.measurementVisibility["stairs"]
    assert items["all"].checkState(0) == QtCore.Qt.CheckState.Checked
    remembered = dict(v.measurementVisibility)
    Toggle("all")
    assert not v.showMeasurements
    assert v.measurementVisibility == remembered
    assert items["all"].checkState(0) == QtCore.Qt.CheckState.Unchecked
    assert all(items[key].checkState(0) == (QtCore.Qt.CheckState.Checked if enabled else QtCore.Qt.CheckState.Unchecked)
               for key, enabled in remembered.items())
    assert all(item.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled for item in items.values())
    Toggle("all")
    assert v.showMeasurements and v.measurementVisibility == remembered
    main.SetViewOption("showMeasurements")  # Same path as M.
    assert not v.showMeasurements and v.measurementVisibility == remembered
    main.SetViewOption("showMeasurements")
    assert v.showMeasurements and v.measurementVisibility == remembered
    assert items["all"].checkState(0) == QtCore.Qt.CheckState.Checked
    for key in v.measurementVisibility:
        panel.SetMeasurementVisibility(key, key in ("walls", "elevators"))
    data = main.BuildProjectData()
    decoded = DecodeProject(data, v.furnishingDefinitions)[5]
    assert decoded["measurementVisibility"] == {"walls": True, "stairs": False, "counters": False, "railings": False, "elevators": True}
    del data["settings"]["measurementVisibility"]
    data["settings"]["measurementSettings"] = {"doors": 1, "windows": 2}
    decoded = DecodeProject(data, v.furnishingDefinitions)[5]
    assert decoded["measurementSettings"]["stairs"] == 2
    assert decoded["measurementVisibility"] == {"walls": True, "stairs": False, "counters": False, "railings": False, "elevators": False}
    data["settings"]["measurementSettings"]["stairs"] = 1
    try:
        DecodeProject(data, v.furnishingDefinitions)
    except ValueError:
        pass
    else:
        raise AssertionError("Facing-side mode accepted for stairs")
    main.close()
    restored = MainWindow()
    assert restored.viewport.measurementVisibility == {"walls": True, "stairs": False, "counters": False, "railings": False, "elevators": True}
    restored.close()


if __name__ == "__main__":
    Main()
