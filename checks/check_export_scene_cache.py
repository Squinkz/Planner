"""Prepared PNG scenes retain geometry, invalidate safely, and match fresh output."""
import os
from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.export_plan import ExportSceneCache, RenderPlan
from planner_app.export_scene import PrepareExportScene
from planner_app.export_settings import BorderSize
from planner_app.project_codec import DecodeProject
from planner_app.print_layout import PrintPageLayout
from planner_app.models import Wall, Window, Furnishing, RoomLabel
from planner_app.graphics import palette


def Main():
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        points = [(0, 0), (8000, 0), (8000, 6000), (0, 6000)]
        walls = [Wall(QtCore.QPointF(*first), QtCore.QPointF(*second), 200)
                 for first, second in zip(points, points[1:] + points[:1])]
        InstallScene(main, [*walls, Window(walls[0], .2, .3),
                           Furnishing(v.furnishingDefinitions["desk"], QtCore.QPointF(3000, 2500)),
                           Furnishing(v.furnishingDefinitions["washer"], QtCore.QPointF(6000, 2500)),
                           RoomLabel(QtCore.QPointF(4000, 4000), "Prepared room")])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetScaleOption("dpi", 96)
        panel.SetBorder("Ruler + Reference Zones")
        panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "None", projectName = "Retained scene"))
        panel.SetScaleOption("pageOrigin", [0, 0])
        layout = panel.PrintLayout()
        overlay = v.exportOverlay
        overlay.bounds = (0, 0, layout["paperTile"][0] * 2, layout["paperTile"][1])
        panel.SetBounds(overlay.bounds)
        arguments = panel.ExportJobs(folder / "page.png", "png")[0][1]
        cache = ExportSceneCache()
        with patch("planner_app.project_codec.DecodeProject", wraps = DecodeProject) as decode, \
                patch("planner_app.export_scene.PrepareExportScene", wraps = PrepareExportScene) as prepare:
            RenderPlan(**arguments, sceneCache = cache)
            source = cache.viewport
            roomBuilds = source.roomDetection.rebuildCount
            # Page offsets, overlap coverage, density, sampling and decorations
            # change the output without changing the prepared model.
            variants = [dict(arguments, bounds = (x, y, *arguments["bounds"][2:])) for x, y in ((1000, -250), (-500, 700))]
            variants += [dict(arguments, dpi = density) for density in (150, 300, 96)]
            variants += [dict(arguments, preview = True, rasterSampling = sampling) for sampling in (.4, .75, 1)]
            variants += [dict(arguments, titleBlock = dict(arguments["titleBlock"], comments = "Updated notes", sheetNumber = "B-104"))]
            variants += [dict(arguments, gridOrigin = (250, -175), vignetteStrength = .25)]
            for border, title in ((90, arguments["titleBlock"]),
                                  (arguments["borderSize"], dict(arguments["titleBlock"], position = "Bottom"))):
                frame = PrintPageLayout(panel.overrides, BorderSize(arguments["border"], border), title, "png")
                variants.append(dict(arguments, borderSize = border, titleBlock = title, bounds = (0, 0, *frame["tile"])))
            variants += [dict(arguments, architecturalScale = 80, bounds = (0, 0, *[value * .8 for value in arguments["bounds"][2:]]))]
            for variant in variants:
                try:
                    actual = RenderPlan(**variant, sceneCache = cache)
                except ValueError as error:
                    error.add_note(str({name: variant[name] for name in ("bounds", "dpi", "borderSize", "titleBlock")}))
                    raise
                assert cache.viewport is source and source.roomDetection.rebuildCount == roomBuilds
                assert decode.call_count == prepare.call_count == 1, "Page changes repeated scene preparation"
                with patch("planner_app.project_codec.DecodeProject", DecodeProject), \
                        patch("planner_app.export_scene.PrepareExportScene", PrepareExportScene):
                    expected = RenderPlan(**variant)
                assert actual == expected, "Prepared page pixels differ from a fresh render"
                assert actual.dotsPerMeterX() == expected.dotsPerMeterX()
            # A fresh project snapshot with only saved export/UI changes still
            # represents the same render scene.
            data = deepcopy(arguments["projectData"])
            data["settings"]["exportSettings"]["borderSize"] = 80
            data["settings"]["roomStyle"] = "Canvas"
            data["settings"]["solidRooms"] = True
            data["ui"]["unrelated"] = True
            RenderPlan(**dict(arguments, projectData = data), sceneCache = cache)
            assert cache.viewport is source and decode.call_count == 1
            # Catch edits to an existing dictionary, not just replacement data.
            data["scene"]["objects"][0]["width"] += 20
            RenderPlan(**dict(arguments, projectData = data), sceneCache = cache)
            assert cache.viewport is not source and decode.call_count == prepare.call_count == 2
            source = cache.viewport
            changed = dict(arguments, solidObjects = False, solidRooms = True, roomStyle = "Canvas")
            actual = RenderPlan(**changed, sceneCache = cache)
            assert cache.viewport is not source and decode.call_count == prepare.call_count == 3
            with patch("planner_app.project_codec.DecodeProject", DecodeProject), \
                    patch("planner_app.export_scene.PrepareExportScene", PrepareExportScene):
                assert actual == RenderPlan(**changed)
            source = cache.viewport
            for appearance in (dict(changed, wallStyle = "Solid"), dict(changed, roomStyle = "Tinted"),
                               dict(changed, solidRooms = False), dict(changed, solidObjects = True)):
                actual = RenderPlan(**appearance, sceneCache = cache)
                assert cache.viewport is source and decode.call_count == prepare.call_count == 3
                with patch("planner_app.project_codec.DecodeProject", DecodeProject), \
                        patch("planner_app.export_scene.PrepareExportScene", PrepareExportScene):
                    assert actual == RenderPlan(**appearance), "Appearance reuse differs from a fresh scene"
            oldColor = palette.themeColors["objectOutline"]
            try:
                palette.themeColors["objectOutline"] = "#124879"
                source = cache.viewport
                RenderPlan(**changed, sceneCache = cache)
                assert cache.viewport is not source and decode.call_count == prepare.call_count == 4
            finally:
                palette.themeColors["objectOutline"] = oldColor
        # A failed draw discards the retained scene instead of leaving partially
        # mutated geometry for the next page.
        from planner_app.viewport.widget import DrawingViewport
        with patch.object(DrawingViewport, "DrawLabels", side_effect = ValueError("Draw failed")):
            try:
                RenderPlan(**arguments, sceneCache = cache)
            except ValueError as error:
                assert str(error) == "Draw failed"
            else:
                raise AssertionError("Expected the injected rendering failure")
        assert cache.viewport is None and cache.key is None
        RenderPlan(**arguments, sceneCache = cache)
        cache.Clear()
        assert cache.viewport is None and cache.decoded is None
        # Qt may destroy top-level render widgets before the editor emits its
        # own destroyed signal during shutdown. Cleanup and reuse must tolerate
        # Python wrappers whose C++ widget has already gone away.
        from shiboken6 import delete, isValid
        RenderPlan(**arguments, sceneCache = cache)
        delete(cache.viewport)
        cache.Clear()
        cache.Clear()
        assert cache.viewport is None and cache.key is None
        RenderPlan(**arguments, sceneCache = cache)
        deleted = cache.viewport
        delete(deleted)
        RenderPlan(**arguments, sceneCache = cache)
        assert cache.viewport is not deleted and isValid(cache.viewport)
        cache.Clear()
        # Preview integration retains the scene across fresh page arguments,
        # then releases it on leaving Export.
        overlay.printPreviewTimer.stop()
        v.grab()
        assert not overlay.previewError, overlay.previewError
        retained = overlay.printSceneCache.viewport
        panel.SetTitleBlockOption("comments", "Frame edit")
        v.grab()
        overlay.printPreviewTimer.stop()
        v.grab()
        assert not overlay.previewError and overlay.printSceneCache.viewport is retained
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        v.grab()
        assert not overlay.previewError and overlay.printSceneCache.viewport is not retained
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        v.grab()
        assert overlay.printSceneCache.viewport is not None
        panel.SetScaleOption("scaleMode", "Digital")
        v.grab()
        assert overlay.printSceneCache.viewport is None
        panel.SetScaleOption("scaleMode", "Print")
        v.grab()
        assert overlay.printSceneCache.viewport is not None
        panel.SetActive(False)
        assert overlay.printSceneCache.viewport is None
    print("Prepared PNG scene reuse, density/crop parity, invalidation, failure and cleanup passed")


if __name__ == "__main__":
    Main()
