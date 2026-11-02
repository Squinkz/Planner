"""Sheet prefixes and reading-order numbering agree in cached/live page output."""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))

from PySide6 import QtCore, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_export_preview_process import WaitForPreview
from planner_app.export_plan import RenderPlan
from planner_app.graphics.title_block import DrawTitleBlock, TitleBlockFields
from planner_app.models import Wall
from planner_app.print_layout import SelectedPrintPages
from planner_app.project_codec import DecodeProject


def Main():
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(), QtCore.QPointF(7000, 5000), 200)])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.sectionButtons["Title Block"].setChecked(True)
        assert panel.titleBlockFields["sheetNumber"].text() == "A-1"
        for name, text in (("sheetNumber", "Sheet prefix"), ("revision", "Revision")):
            field = panel.titleBlockFields[name]
            label = next(label for label in panel.titleBlockOptions.findChildren(QtWidgets.QLabel) if label.buddy() is field)
            assert label.text() == text
            layout = panel.titleBlockOptions.layout()
            assert any(item.layout() is not None and item.layout().indexOf(label) >= 0
                       and item.layout().indexOf(field) >= 0
                       for item in (layout.itemAt(index) for index in range(layout.count())))
        for prefix in ("A-1", "Plan-", "", "X9-", "Étage "):
            for index, suffix in ((1, "01"), (9, "09"), (10, "10"), (99, "99"),
                                  (100, "101"), (198, "199"), (199, "201"), (256, "258")):
                fields = TitleBlockFields(dict(sheetNumber = prefix, sheetIndex = index), 100)
                assert next(field[2] for field in fields if field[0] == "sheetNumber") == prefix + suffix

        panel.SetScaleOption("dpi", 72)
        panel.SetScaleOption("pageOrigin", [0, 0])
        panel.SetBorder("Frame")
        panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "None", sheetNumber = "A-1"))
        layout = panel.PrintLayout()
        width, height = layout["paperTile"]
        bounds = (-width, -height, width * 2, height * 2)
        overlay = v.exportOverlay
        overlay.bounds = bounds
        panel.SetBounds(bounds)
        pages = SelectedPrintPages(bounds, layout["paperTile"], stride = layout["paperStride"])
        assert [(page[0], page[1]) for page in pages] == [(-width, 0), (0, 0), (-width, -height), (0, -height)]
        v.zoom = min(v.DrawingRect().width() / (2.2 * width), v.DrawingRect().height() / (2.2 * height)) / v.basePixelsPerMillimeter
        v.panOffset += v.DrawingRect().center() - v.WorldToViewport(QtCore.QPointF())
        for kind in ("png", "svg", "pdf_raster", "pdf_vector"):
            jobs = panel.ExportJobs(folder / ("pages.pdf" if kind.startswith("pdf") else "pages." + kind), kind)
            assert [render["sheetIndex"] for target, render in jobs] == [1, 2, 3, 4]
            assert all(render["titleBlock"]["sheetNumber"] == "A-1" for target, render in jobs)
        seen = []

        def RecordBlock(painter, block, options, scale, *args, **kwargs):
            fields = TitleBlockFields(options, scale)
            seen.append((options.get("sheetIndex", 1), next(field[2] for field in fields if field[0] == "sheetNumber")))
            return DrawTitleBlock(painter, block, options, scale, *args, **kwargs)

        for position in ("Right", "Bottom"):
            panel.SetTitleBlockOption("position", position)
            for kind in ("png", "svg"):
                panel.typeField.setCurrentIndex(panel.typeField.findData(kind.upper()))
                overlay.printPreviewTimer.stop()
                overlay.ClearPrintPreview()
                seen.clear()
                with patch("planner_app.graphics.title_block.DrawTitleBlock", side_effect = RecordBlock), \
                        patch("planner_app.viewport.print_pages.DrawTitleBlock", side_effect = RecordBlock):
                    v.grab()
                assert not overlay.previewError, overlay.previewError
                assert set(seen) == {(1, "A-101"), (2, "A-102"), (3, "A-103"), (4, "A-104")}, (kind, position, seen)
                previous = dict(overlay.printPageCache)
                jobs = panel.ExportJobs(folder / ("numbered." + kind), kind)
                for index, (target, render) in enumerate(jobs, 1):
                    seen.clear()
                    with patch("planner_app.graphics.title_block.DrawTitleBlock", side_effect = RecordBlock):
                        output = RenderPlan(**render)
                    assert seen == [(index, f"A-1{index:02d}")], seen
                    if kind == "png":
                        assert output == overlay.printPageCache[pages[index - 1]], "Raster preview/output sheet numbers differ"
                # Remove the top row. Remaining pages must become 01/02,
                # without reusing their previous 03/04 decorations.
                overlay.bounds = (-width, -height, width * 2, height)
                panel.SetBounds(overlay.bounds)
                overlay.printPreviewTimer.stop()
                seen.clear()
                with patch("planner_app.graphics.title_block.DrawTitleBlock", side_effect = RecordBlock), \
                        patch("planner_app.viewport.print_pages.DrawTitleBlock", side_effect = RecordBlock):
                    v.grab()
                assert not overlay.previewError, overlay.previewError
                assert set(seen) == {(1, "A-101"), (2, "A-102")}, (kind, seen)
                assert all(overlay.printPageCache[page] is not previous[page] for page in pages[2:])
                overlay.bounds = bounds
                panel.SetBounds(bounds)

        # Sequence rollover is applied by the real render path, not the prefix.
        render = panel.ExportJobs(folder / "rollover.svg", "svg")[0][1]
        seen.clear()
        with patch("planner_app.graphics.title_block.DrawTitleBlock", side_effect = RecordBlock):
            RenderPlan(**dict(render, sheetIndex = 100))
        assert seen == [(100, "A-1101")]
        saved = main.BuildProjectData(includeHistory = False)
        assert DecodeProject(copy.deepcopy(saved), v.furnishingDefinitions)[5]["exportSettings"]["titleBlock"]["sheetNumber"] == "A-1"
        assert "sheetIndex" not in saved["settings"]["exportSettings"]["titleBlock"]

        # Worker results also depend on the sequence after crop-only edits.
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        overlay.printPreviewTimer.stop()
        overlay.ClearPrintPreview()
        os.environ.pop("PLANNER_SYNCHRONOUS_PREVIEW", None)
        try:
            WaitForPreview(v, "png")
            overlay.bounds = (-width, -height, width * 2, height)
            panel.SetBounds(overlay.bounds)
            overlay.printPreviewTimer.stop()
            WaitForPreview(v, "png")
            for page, (target, render) in zip(pages[2:], panel.ExportJobs(folder / "worker.png", "png")):
                assert overlay.printPageCache[page] == RenderPlan(**render)
        finally:
            os.environ["PLANNER_SYNCHRONOUS_PREVIEW"] = "1"
            if overlay.previewProcess is not None:
                overlay.previewProcess.Close()
    print("Sheet numbering, rollover, inline controls, PNG/SVG/PDF jobs and crop renumbering passed")


if __name__ == "__main__":
    Main()
