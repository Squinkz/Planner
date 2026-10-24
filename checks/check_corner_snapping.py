"""Control points and footprint corners have independent persistent policies."""
import copy
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow
from planner_app.models import Wall, Furnishing
from planner_app.project_codec import DecodeProject
from planner_app.viewport.snapping import CornerSnapPoint


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    v = main.viewport
    point = QtCore.QPointF
    plain = QtCore.Qt.KeyboardModifier.NoModifier
    alt = QtCore.Qt.KeyboardModifier.AltModifier
    wall = Wall(point(37, 23), point(837, 523), 1000)
    furnishing = Furnishing(v.furnishingDefinitions["null"], point(2500, 2000))
    v.walls, v.furnishings, v.windows, v.labels = [wall], [furnishing], [], []
    v.zoom = 1
    corner = v.ObjectCorners(furnishing)[0]
    offset = point(9, 7)
    distant = [point(100000 + index * 1000, 200000 + index * 1000) for index in range(40)]
    distant += [CornerSnapPoint(-100000 - index * 1000, -200000 - index * 1000) for index in range(40)]
    for key in ("grid", "midpoints", "alignment"):
        main.snapOptions[key].setChecked(False)
    assert main.snapOptions["corners"].accessibleName() == "Corners"
    for controls in (False, True):
        for corners in (False, True):
            main.snapOptions["vertices"].setChecked(controls)
            main.snapOptions["corners"].setChecked(corners)
            if controls or corners:
                main.snapButton.setChecked(True)
            assert v.vertexSnapEnabled == controls and v.cornerSnapEnabled == corners
            for target, enabled in ((wall.firstVertex, controls), (corner, corners)):
                raw = target + offset
                assert v.SnapPosition(raw, plain) == (target if enabled else raw), (controls, corners, target)
                assert v.SnapPosition(raw, alt) == raw
                assert v.SnapObjectMovement([point()], raw, plain) == (target if enabled else raw)
                assert v.SnapObjectMovement([point()], raw, plain, snapTargets = list(v.SnapVertices()) + distant) == (target if enabled else raw)
            # Explicit footprint pools include joined wall corners as well as
            # furnishing corners, and retain their classification when cached.
            targets = v.StairSnapTargets()
            assert targets is v.StairSnapTargets()
            raw = corner + offset
            assert v.SnapPosition(raw, plain, snapTargets = targets) == (corner if corners else raw)
            wallCorner = v.ObjectCorners(wall)[0]
            raw = wallCorner + offset
            assert v.SnapPosition(raw, plain, snapTargets = targets) == (wallCorner if corners else raw)
            data = main.BuildProjectData(includeHistory = False)
            decoded = DecodeProject(data, v.furnishingDefinitions)
            assert decoded[5]["snap"]["vertices"] == controls
            assert decoded[5]["snap"]["corners"] == corners
            main.ApplyProject(decoded, None)
            assert main.snapOptions["vertices"].isChecked() == controls
            assert main.snapOptions["corners"].isChecked() == corners
    # Alignment can project only enabled target types, including midpoints.
    main.snapOptions["alignment"].setChecked(True)
    main.snapButton.setChecked(True)
    for controls in (False, True):
        for corners in (False, True):
            main.snapOptions["vertices"].setChecked(controls)
            main.snapOptions["corners"].setChecked(corners)
            for target, enabled in ((wall.firstVertex, controls), (corner, corners)):
                raw = target + point(9, 2111)
                expected = point(target.x(), raw.y()) if enabled else raw
                assert v.SnapPosition(raw, plain) == expected, (controls, corners, target)
                assert v.SnapObjectMovement([point()], raw, plain) == expected
                assert v.SnapObjectMovement([point()], raw, plain, snapTargets = list(v.SnapVertices()) + distant) == expected
    main.snapOptions["vertices"].setChecked(False)
    main.snapOptions["corners"].setChecked(False)
    center = (furnishing.firstVertex + furnishing.secondVertex) / 2
    raw = center + point(9, 2111)
    for midpoints in (False, True):
        main.snapOptions["midpoints"].setChecked(midpoints)
        assert v.SnapPosition(raw, plain) == (point(center.x(), raw.y()) if midpoints else raw)
    main.snapOptions["midpoints"].setChecked(False)
    assert v.SnapPosition(point(9, 777), plain, snapTargets = [], alignmentTargets = [point(0, 777)]) == point(9, 777)
    data = main.BuildProjectData(includeHistory = False)
    for controls in (False, True):
        legacy = copy.deepcopy(data)
        legacy["settings"]["snap"].pop("corners")
        legacy["settings"]["snap"]["vertices"] = controls
        settings = DecodeProject(legacy, v.furnishingDefinitions)[5]
        assert settings["snap"]["corners"] == settings["snap"]["vertices"] == controls
        assert "corners" not in legacy["settings"]["snap"], "Loading mutated the source project"
    data["settings"]["snap"]["corners"] = "invalid"
    try:
        DecodeProject(data, v.furnishingDefinitions)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid corner-snap flag was accepted")
    main.MarkProjectClean()
    main.close()


if __name__ == "__main__":
    Main()
