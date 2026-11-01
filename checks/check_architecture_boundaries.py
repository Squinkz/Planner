"""Independent snapshots, view ownership, complete cache verification and indexed checks."""
import copy
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Door, Arrow, Furnishing, RoomLabel
from planner_app.scene_snapshot import CaptureSceneSnapshot, RestoreWallSnapshots, RestoreOpeningSnapshots
from planner_app.view_settings import CaptureViewportView, ApplyViewportView, viewSettingNames
from planner_app.history_records import HistoryEntryFields
from planner_app.scene_problems import FindSceneProblems
from planner_app import geometry_recovery


def Main():
    isolated = subprocess.run([sys.executable, "-B", "-c",
        "import sys; sys.path.insert(0, sys.argv[1]); from planner_app.scene_snapshot import CaptureSceneSnapshot; "
        "from planner_app.project_history import DecodeHistory; "
        "assert not any(name.startswith('planner_app.viewport') for name in sys.modules)",
        str(root / "planner-main")], capture_output = True, text = True, timeout = 10)
    # Project decoding still needs desktop footprint validation, but importing
    # capture/history policy must not import viewport interaction or widgets.
    assert isolated.returncode == 0, isolated.stderr
    with ExampleWindow() as (main, folder):
        v, panel = main.viewport, main.exportPanel
        point = QtCore.QPointF
        wall = Wall(point(-0.0, 0), point(4000, 0), 240)
        door = Door(wall, .2, .4, hingeAtSecond = True)
        arrow = Arrow(point(0, 2000), point(1500, 2000))
        arrow.directionReversed = True
        InstallScene(main, [wall, arrow, door])
        snapshot = CaptureSceneSnapshot(v.walls, v.windows, [], [])
        assert snapshot.walls[0].width == 240 and snapshot.windows[0].hingeAtSecond
        fields = HistoryEntryFields(0, snapshot.walls[1], "Arrow")
        assert fields["directionReversed"] and fields["tipSize"] == arrow.tipSize
        wall.width = 500
        arrow.directionReversed = False
        door.hingeAtSecond = False
        RestoreWallSnapshots(snapshot.walls)
        RestoreOpeningSnapshots(snapshot.windows)
        assert CaptureSceneSnapshot(v.walls, v.windows, [], []) == snapshot

        furnishing = Furnishing(v.furnishingDefinitions["washer"], point(2000, 1500))
        v.furnishings.append(furnishing)
        for obj, name in ((arrow, "directionReversed"), (furnishing, "behindCounters")):
            revision = v.SceneRenderKey(())
            reference = v.SceneRenderValueKey(())
            setattr(obj, name, not getattr(obj, name))
            assert v.SceneRenderKey(()) != revision and v.SceneRenderValueKey(()) != reference
        room = RoomLabel(point(2000, 2500), "Room")
        v.labels.append(room)
        for obj, name, value in ((room, "unitsOverride", "Inches"), (door, "geometryIssues", ("opening_bounds",))):
            revision, reference = v.SceneRenderKey(()), v.SceneRenderValueKey(())
            setattr(obj, name, value)
            assert v.SceneRenderKey(()) != revision and v.SceneRenderValueKey(()) != reference

        original = CaptureViewportView(v)
        captured = CaptureViewportView(v)
        captured["visibility"]["Walls"] = not captured["visibility"]["Walls"]
        assert captured["visibility"] != v.visibility
        ApplyViewportView(v, captured)
        captured["visibility"]["Walls"] = not captured["visibility"]["Walls"]
        assert v.visibility != captured["visibility"], "Applying borrowed a mutable settings group"
        ApplyViewportView(v, original)
        saved = main.ProjectSettings()
        assert all(saved.get(name, original[name]) == original[name] for name in viewSettingNames)
        main.sidebarTabs.setCurrentWidget(panel)
        projectView = copy.deepcopy(panel.projectView)
        panel.SetOverride("showGrid", not projectView["showGrid"])
        panel.SetOverride("unitsMode", "Inches")
        saved = main.ProjectSettings()
        assert saved["showGrid"] == projectView["showGrid"] and saved["unitsMode"] == projectView["unitsMode"]
        arguments = panel.RenderArguments("png", preview = True)
        assert arguments["projectData"]["settings"]["unitsMode"] == "Inches"
        main.sidebarTabs.setCurrentWidget(main.buildScrollArea)
        assert CaptureViewportView(v) == original

        # Material ownership partitions overlap for painting. Placement also
        # needs the physical bodies used by collision validation at a junction.
        for rotated in (False, True):
            for reversedWall in (False, True):
                for offset in (0, 50000000):
                    points = [(-700, 0), (-200, 0), (200, 300), (0, 850)]
                    points = [point((-y if rotated else x) + offset, (x if rotated else y) - offset)
                              for x, y in points]
                    walls = [Wall(second, first, 240) if reversedWall else Wall(first, second, 240)
                             for first, second in zip(points, points[1:])]
                    InstallScene(main, walls)
                    v.snapEnabled = False
                    unsafe = Door(walls[0], .08, 1) if reversedWall else Door(walls[0], 0, .92)
                    assert not v.OpeningFits(unsafe)
                    for parent in walls:
                        cursor = v.WorldToViewport((parent.firstVertex + parent.secondVertex) / 2)
                        candidate = v.FindWindowPlacement(cursor, openingType = Door,
                            modifiers = QtCore.Qt.KeyboardModifier.NoModifier)
                        assert candidate is not None and candidate.parentWall is parent
                        assert 1 < candidate.length < QtCore.QLineF(parent.firstVertex, parent.secondVertex).length()
                        assert v.OpeningFits(candidate)

        # Count native wall reconstruction, rather than using machine timings.
        counts = []
        for count in (20, 40):
            walls = [Wall(point(index * 6000, 0), point(index * 6000 + 4000, 0)) for index in range(count)]
            doors = [Door(parent, .3, .6) for parent in walls]
            InstallScene(main, walls + doors)
            with patch.object(geometry_recovery, "RecordWall", wraps = geometry_recovery.RecordWall) as convert:
                problems = FindSceneProblems(v, includePotential = False)
            assert not problems
            assert convert.call_count <= 3 * len(walls + doors), convert.call_count
            counts.append(convert.call_count)
        assert counts[1] <= counts[0] * 2 + 2
    print("PASS: independent history boundary, named replay, view ownership, cache fields and linear validation preparation")


if __name__ == "__main__":
    Main()
