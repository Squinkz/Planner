"""Export-only opening outlines: independent styles, caches, history and persistence."""
import copy
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from check_tinted_passage_outlines import AssertOutline, AssertNoOutline
from planner_app.export_plan import ExportSceneCache, RenderPlan
from planner_app.graphics.palette import themeColors
from planner_app.models import Door, Wall
from planner_app.project_codec import DecodeProject


def Main():
    with ExampleWindow() as (main, folder):
        view, panel = main.viewport, main.exportPanel
        point = QtCore.QPointF
        divider = Wall(point(-2000, 0), point(2000, 0), 200)
        InstallScene(main, Rectangle(-2000, -2000, 4000, 4000) + [divider, Door(divider, .35, .65)])
        view.showGrid = view.showMeasurements = view.showTips = False
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Digital")
        panel.borderField.setCurrentText("None")
        panel.scaleField.setValue(200)
        view.exportOverlay.bounds = (-2500, -2500, 5000, 5000)
        panel.SetBounds(list(view.exportOverlay.bounds))
        assert panel.drawOpeningOutlinesField.isChecked()
        assert panel.drawOpeningOutlinesField.accessibleName() == "Openings"
        assert panel.sectionContents["Canvas"].isAncestorOf(panel.drawOpeningOutlinesField)
        assert all(panel.sectionContents["Canvas"].isAncestorOf(field) for field in (panel.solidRoomsField, panel.solidObjectsField))
        fill, canvas = QtGui.QColor(themeColors["roomFill"]), QtGui.QColor(themeColors["canvas"])
        for style in ("Canvas", "Tinted"):
            panel.roomStyleField.setCurrentText(style)
            for solid in (True, False):
                panel.solidObjectsField.setChecked(solid)
                for kind in ("png", "svg"):
                    cache = ExportSceneCache()
                    try:
                        source = None
                        for enabled in (True, False, True):
                            panel.drawOpeningOutlinesField.setChecked(enabled)
                            args = panel.RenderArguments(kind, preview = True)
                            result = RenderPlan(**args, sceneCache = cache)
                            assert source is None or cache.viewport is source, "Rebuilt scene geometry for an outline toggle"
                            source = cache.viewport
                            if kind == "svg":
                                image = QtGui.QImage(1000, 1000, QtGui.QImage.Format.Format_ARGB32)
                                image.fill(0)
                                with QtGui.QPainter(image) as painter:
                                    QtSvg.QSvgRenderer(result).render(painter)
                            else:
                                image = result
                            check = AssertOutline if enabled else AssertNoOutline
                            for y in (480, 520):
                                check(image, 500, y, 3, fill if style == "Tinted" else canvas, canvas,
                                      (style, solid, kind, enabled, y))
                    finally:
                        cache.Clear()
        # Both Print and free-crop previews must invalidate their retained artwork.
        for mode in ("Digital", "Architectural", "Print"):
            panel.SetScaleOption("scaleMode", mode)
            panel.SetScaleOption("dpi", 96)
            for kind in ("PNG", "SVG"):
                panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
                images = []
                for enabled in (True, False, True):
                    panel.drawOpeningOutlinesField.setChecked(enabled)
                    images.append(view.grab().toImage())
                    assert not view.exportOverlay.previewError, view.exportOverlay.previewError
                assert images[0] != images[1], (mode, kind, "Preview did not update")
                assert images[0] == images[2], (mode, kind, "Toggle did not restore pixels")
        panel.drawOpeningOutlinesField.setChecked(False)
        view.Undo()
        assert panel.drawOpeningOutlinesField.isChecked()
        view.Redo()
        assert not panel.drawOpeningOutlinesField.isChecked()
        saved = copy.deepcopy(main.BuildProjectData(includeHistory = False))
        assert saved["settings"]["exportSettings"]["drawOpeningOutlines"] is False
        assert "drawOpeningOutlines" not in saved["settings"]
        cli = RenderPlan(folder / "outlines.plan", 200, (-2500, -2500, 5000, 5000),
                         projectData = saved, useExportSettings = True, applyTheme = False,
                         furnishingDefinitions = view.furnishingDefinitions)
        for y in (480, 520):
            AssertNoOutline(cli, 500, y, 3, fill, canvas, ("saved export options", y))
        main.ApplyProject(DecodeProject(saved, view.furnishingDefinitions), None)
        assert view.drawOpeningOutlines and not view.exportOverlay.active
        main.sidebarTabs.setCurrentWidget(panel)
        assert not panel.drawOpeningOutlinesField.isChecked() and not view.drawOpeningOutlines
        main.sidebarTabs.setCurrentWidget(main.buildScrollArea)
        assert view.drawOpeningOutlines
    print("PASS: opening outlines independently toggle across room styles, PNG/SVG/Print previews, retained scenes, undo/redo and project reload")


if __name__ == "__main__":
    Main()
