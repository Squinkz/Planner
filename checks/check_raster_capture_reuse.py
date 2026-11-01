"""Raster appearance refreshes reuse exact captured Qt commands safely."""
import os
from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Door, Furnishing, RoomLabel
from planner_app.export_plan import ExportSceneCache, RenderPlan
from planner_app.viewport import rendering


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        p = QtCore.QPointF
        walls = [Wall(p(0, 0), p(6000, 0), 200), Wall(p(6000, 0), p(6500, 4500), 200),
                 Wall(p(6500, 4500), p(0, 4500), 200), Wall(p(0, 4500), p(0, 0), 200)]
        InstallScene(main, [*walls, Door(walls[0], .2, .4),
                            Furnishing(v.furnishingDefinitions["washer"], p(2000, 1800)),
                            Furnishing(v.furnishingDefinitions["desk"], p(4000, 2300)),
                            RoomLabel(p(3000, 3000), "Captured room")])
        data = main.BuildProjectData(includeHistory = False, includeActivity = False)
        arguments = dict(planPath = "capture.plan", scale = 100, bounds = (-1000, -1000, 8500, 6500),
                         outputFormat = "png", projectData = data, furnishingDefinitions = v.furnishingDefinitions,
                         preview = True, applyTheme = False, solidObjects = False, roomStyle = "Canvas", solidRooms = False,
                         border = "Ruler", borderSize = 28,
                         titleBlock = dict(enabled = True, logoMode = "None", projectName = "Exact capture"))
        cache = ExportSceneCache()
        actual = RenderPlan(**arguments, sceneCache = cache)
        assert actual == RenderPlan(**arguments), "Initial captured pixels differ"
        source = cache.viewport
        captures = source.exportObjectCaptures
        assert len(captures) == 1
        commands = captures[0][1]
        measurements = source.sceneMeasurements[1]
        maps = (source.furnishingRenderers, source.selectedFurnishingRenderers, source.groupedFurnishingRenderers)
        revision = source.renderChanges.appearance
        # Backgrounds, title text and compositing change while the exact model
        # command sequence remains reusable. Compare every completed image.
        for changes in (dict(solidRooms = True), dict(solidRooms = False),
                        dict(titleBlock = dict(arguments["titleBlock"], comments = "Updated")),
                        dict(vignetteStrength = .2)):
            changed = dict(arguments, **changes)
            with patch.object(rendering, "ObjectPaintDevice", side_effect = AssertionError("Rebuilt unchanged capture")):
                actual = RenderPlan(**changed, sceneCache = cache)
            assert actual == RenderPlan(**changed), "Retained capture changed background/frame pixels"
            assert source.exportObjectCaptures[-1][1] is commands
            assert source.sceneMeasurements[1] is measurements, "Rendering invalidated measurement preparation"
            assert source.renderChanges.appearance == revision, "Temporary capture resources changed scene revision"
            assert all(first is second for first, second in zip(maps, (source.furnishingRenderers, source.selectedFurnishingRenderers, source.groupedFurnishingRenderers)))
        for changes in (dict(wallStyle = "Outline"), dict(roomStyle = "Tinted"),
                        dict(bounds = (-600, -700, 8500, 6500)), dict(rasterSampling = .75),
                        dict(architecturalScale = 100, dpi = 225)):
            changed = dict(arguments, **changes)
            with patch.object(rendering, "ObjectPaintDevice", wraps = rendering.ObjectPaintDevice) as capture:
                actual = RenderPlan(**changed, sceneCache = cache)
                assert capture.called, "Model/scale changes reused stale captured commands"
            assert actual == RenderPlan(**changed), "Changed model capture differs from direct rendering"
        for index in range(8):
            changed = dict(arguments, bounds = (-1000 + index * 100, -1000, 8500, 6500))
            actual = RenderPlan(**changed, sceneCache = cache)
            assert actual == RenderPlan(**changed)
            captures = source.exportObjectCaptures
            assert len(captures) <= 4
            assert sum(len(item[1].engine.commands) for item in captures) <= 8192
            assert sum(item[3] for item in captures) <= 262144
            assert sum(item[4] for item in captures) <= 16 * 1024 * 1024
        changedData = deepcopy(data)
        changedData["scene"]["objects"][0]["width"] += 50
        changed = dict(arguments, projectData = changedData)
        assert RenderPlan(**changed, sceneCache = cache) == RenderPlan(**changed)
        assert cache.viewport is not source
        cache.Clear()
        assert cache.viewport is None
    print("Exact capture/background/decoration pixels, revision stability, invalidation and bounded crop retention passed")


if __name__ == "__main__":
    Main()
