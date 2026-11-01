"""A4 print controls, tiled selection, offsets, exact page output and batch export."""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner_app.export_plan import RenderPlan
from planner_app.export_settings import ExportScalePerMeter
from planner_app.print_layout import SelectedPrintPages, PrintPaperSize, ConstrainPrintBounds, printPaperSizes
from planner_app.project_codec import DecodeProject
from planner_app.ui.export_progress import ExportProgressDialog
from fixtures.parity_examples import ExampleWindow


def Main():
    # Minimum crop preserves a complete cell, even between grid lines or below zero.
    for origin in ((0, 0), (1234, -678)):
        for edge in range(4):
            options = dict(architecturalScale = 1)
            bounds = (origin[0] + 20, origin[1] + 30, 50, 40)
            constrained = ConstrainPrintBounds(bounds, options, origin, edge)
            assert SelectedPrintPages(constrained, (297, 210), origin)
            opposite = edge ^ 1
            before = (bounds[0], bounds[0] + bounds[2], bounds[1], bounds[1] + bounds[3])
            after = (constrained[0], constrained[0] + constrained[2], constrained[1], constrained[1] + constrained[3])
            assert before[opposite] == after[opposite]
    assert SelectedPrintPages((0, 0, 100, 200), (100, 200)) == [(0, 0, 100, 200)]
    assert SelectedPrintPages((-100, -200, 200, 400), (100, 200)) == [
        (-100, 0, 100, 200), (0, 0, 100, 200), (-100, -200, 100, 200), (0, -200, 100, 200)]
    assert SelectedPrintPages((10, 20, 100, 200), (100, 200), (10, 20)) == [(10, 20, 100, 200)]
    try:
        SelectedPrintPages((0, 0, 10000, 10000), (1, 1))
    except ValueError:
        pass
    else:
        raise AssertionError("Unbounded batch accepted")
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        main.sidebarTabs.setCurrentWidget(panel)
        panel.scaleModeTabs.setCurrentIndex(0)
        assert panel.overrides["scaleMode"] == "Print" and v.exportOverlay.printMode
        assert panel.architecturalRow.isVisible() and panel.dpiRow.isVisible()
        assert panel.resolutionRow.isHidden() and panel.architecturalResolutionRow.isHidden()
        assert panel.pageSizeField.currentData() == "A4"
        assert panel.pageSizeField.currentText() == "A4 (297 × 210 mm)"
        assert panel.pageSizeField.count() == len(printPaperSizes) + 3
        for index, label in ((0, "A Series"), (6, "ARCH Series"), (12, "US Sizes")):
            item = panel.pageSizeField.model().item(index)
            assert item.text() == label and item.flags() == QtCore.Qt.ItemFlag.NoItemFlags
        assert [panel.pageSizeField.itemText(index) for index in range(13, 16)] == [
            "Letter (11 × 8.5 in)", "Legal (14 × 8.5 in)", "Tabloid (17 × 11 in)"]
        assert panel.pageSizeField.itemText(panel.pageSizeField.findData("ARCH A")) == "ARCH A (12 × 9 in)"
        panel.pageOrientationButtons["Portrait"].click()
        assert panel.pageSizeField.currentText() == "A4 (210 × 297 mm)"
        assert panel.pageSizeField.itemText(panel.pageSizeField.findData("Letter")) == "Letter (8.5 × 11 in)"
        panel.pageOrientationButtons["Landscape"].click()
        for name, portrait in printPaperSizes.items():
            assert PrintPaperSize(dict(pageSize = name, pageOrientation = "Portrait")) == portrait
            v.exportOverlay.bounds = (0, 0, 1, 1)
            panel.pageSizeField.setCurrentIndex(panel.pageSizeField.findData(name))
            layout = panel.PrintLayout()
            assert layout["paper"] == portrait[::-1]
            assert SelectedPrintPages(v.exportOverlay.bounds, layout["paperTile"], v.exportOverlay.pageOrigin)
            saved = main.BuildProjectData(includeHistory = False)
            assert DecodeProject(copy.deepcopy(saved), v.furnishingDefinitions)[5]["exportSettings"]["pageSize"] == name
        panel.pageSizeField.setCurrentIndex(panel.pageSizeField.findData("A4"))
        w, h = panel.PrintLayout()["paperTile"]
        for edge, coordinate in ((0, w * 3), (1, -w * 3), (2, h * 3), (3, -h * 3)):
            v.exportOverlay.bounds = (0, 0, w * 2, h * 2)
            v.exportOverlay.MoveEdge(edge, coordinate, modifiers = QtCore.Qt.KeyboardModifier.AltModifier)
            assert SelectedPrintPages(v.exportOverlay.bounds, (w, h))
        panel.SetScaleOption("dpi", 300)
        panel.SetScaleOption("architecturalScale", 100)
        assert panel.PrintLayout()["pixels"] == (3508, 2480)
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        assert panel.dpiRow.isHidden() and panel.architecturalResolutionRow.isHidden()
        assert "Page resolution" not in panel.printNote.text() and "selected." in panel.printNote.text()
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        panel.SetScaleOption("pageOrigin", [0, 0])
        panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "Planner", projectName = "A4 at 300 PPI"))
        w, h = panel.PrintLayout()["paperTile"]
        v.exportOverlay.bounds = (0, 0, w, h)
        panel.SetBounds(v.exportOverlay.bounds)
        initialBounds = v.exportOverlay.bounds
        panel.ResetExportHistory()
        for axis, coordinate in ((0, 1234), (1, -678)):
            v.exportOverlay.pageDragStarted.emit()
            v.exportOverlay.dragPage = axis
            v.exportOverlay.pageDragOffset = 0
            origin = list(v.exportOverlay.pageOrigin)
            origin[axis] = coordinate
            v.exportOverlay.MovePrintOrigin(v.WorldToViewport(QtCore.QPointF(*origin)))
            v.exportOverlay.dragPage = None
            v.exportOverlay.pageDragFinished.emit()
            offset = v.exportOverlay.pageOrigin
            assert abs(v.exportOverlay.bounds[0] - initialBounds[0] - offset[0]) < .001
            assert abs(v.exportOverlay.bounds[1] - initialBounds[1] - offset[1]) < .001
            assert v.exportOverlay.bounds[2:] == initialBounds[2:]
            assert len(panel.ExportJobs(folder / "following.png", "png")) == 1
        panel.UndoExport()
        panel.UndoExport()
        assert v.exportOverlay.pageOrigin == (0, 0)
        assert all(abs(a - b) < .001 for a, b in zip(v.exportOverlay.bounds, initialBounds))
        fullSize = panel.Render("png")
        assert (fullSize.width(), fullSize.height()) == (3508, 2480)
        # Raster and vector use the same print geometry, including border units.
        assert ExportScalePerMeter(panel.overrides, "PNG") == ExportScalePerMeter(panel.overrides, "SVG")
        panel.SetScaleOption("dpi", 96)
        panel.SetBorder("Ruler + Reference Zones")
        for orientation in ("Landscape", "Portrait"):
            panel.pageOrientationButtons[orientation].click()
            panel.SetScaleOption("pageOrigin", [0, 0])
            assert panel.pageOrientationButtons[orientation].isChecked()
            for position in (None, "Right", "Bottom"):
                options = dict(enabled = position is not None, position = position or "Right", logoMode = "Planner",
                    projectName = "Print Project", drawingTitle = "Ground floor", address = "1 Oak Avenue\nTown",
                    revision = "A2-B", sheetNumber = "ABC-No-Number", comments = "Notes")
                panel.SetOverride("titleBlock", options)
                layout = panel.PrintLayout()
                w, h = layout["paperTile"]
                v.exportOverlay.bounds = (0, 0, w, h)
                panel.SetBounds(v.exportOverlay.bounds)
                jobs = panel.ExportJobs(folder / "pages.png", "png")
                assert len(jobs) == 1 and jobs[0][0].name == "pages_001.png"
                assert jobs[0][1]["titleBlock"]["sheetNumber"] == "ABC-No-Number"
                image = RenderPlan(**jobs[0][1])
                assert (image.width(), image.height()) == layout["pixels"], (orientation, position, image.size(), layout)
                assert abs(image.dotsPerMeterX() * .0254 - 96) < .02
                svgJob = panel.ExportJobs(folder / "pages.svg", "svg")[0][1]
                svg = ElementTree.fromstring(RenderPlan(**svgJob))
                assert (svg.get("width"), svg.get("height")) == tuple(f"{value}mm" for value in layout["paper"])
                assert not svg.findall(".//{http://www.w3.org/2000/svg}text")
                preview = v.grab().toImage()
                assert not preview.isNull() and not v.exportOverlay.previewError
                panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
                v.grab()
                assert not v.exportOverlay.previewError
                assert any(not isinstance(page, QtGui.QImage) for page in v.exportOverlay.printPageCache.values())
                panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        # Drag a dotted guide; the crop follows while the ruler origin stays fixed.
        panel.SetOverride("titleBlock", dict(enabled = False))
        panel.pageOrientationButtons["Landscape"].click()
        panel.SetScaleOption("pageOrigin", [0, 0])
        w, h = panel.PrintLayout()["paperTile"]
        v.exportOverlay.bounds = (-w * .1, -h * .1, w * 1.2, h * 1.2)
        panel.SetBounds(v.exportOverlay.bounds)
        v.zoom = .6 / v.basePixelsPerMillimeter / (w / 400)
        v.panOffset = QtCore.QPointF()
        point = v.WorldToViewport(QtCore.QPointF(0, h * .15))
        v.panOffset += v.DrawingRect().center() - point
        point = v.WorldToViewport(QtCore.QPointF(0, h * .15)).toPoint()
        assert v.exportOverlay.HitPrintGuide(QtCore.QPointF(point)) == 0
        oldBounds, oldGrid = v.exportOverlay.bounds, v.gridOrigin
        previewArgs = panel.RenderArguments("svg", preview = True, previewScene = True)
        tileWidth, tileHeight = panel.PrintLayout()["tile"]
        assert previewArgs["bounds"] == (-tileWidth, -tileHeight, 3 * tileWidth, 3 * tileHeight), "Print preview must include complete drawing areas"
        panel.ResetExportHistory()
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = point)
        QtTest.QTest.mouseMove(v, point + QtCore.QPoint(30, 0))
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = point + QtCore.QPoint(30, 0))
        assert panel.overrides["pageOrigin"][0] != 0
        movedBounds = v.exportOverlay.bounds
        assert abs(movedBounds[0] - oldBounds[0] - panel.overrides["pageOrigin"][0]) < .001
        assert movedBounds[1:] == oldBounds[1:] and v.gridOrigin == oldGrid
        panel.UndoExport()
        assert v.exportOverlay.pageOrigin == (0, 0)
        assert v.exportOverlay.bounds == oldBounds
        panel.RedoExport()
        assert v.exportOverlay.pageOrigin[0] != 0
        assert v.exportOverlay.bounds == movedBounds
        originPoint = v.WorldToViewport(QtCore.QPointF(v.exportOverlay.pageOrigin[0], h * .15)).toPoint()
        QtTest.QTest.mouseDClick(v, QtCore.Qt.MouseButton.LeftButton, pos = originPoint)
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = originPoint)
        assert v.exportOverlay.pageOrigin == (0, 0)
        assert all(abs(a - b) < .001 for a, b in zip(v.exportOverlay.bounds, oldBounds))
        panel.SetScaleOption("pageOrigin", [0, 0])
        # Two whole pages, each independently rendered and published after success.
        panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "None", sheetNumber = "AB-UNCHANGED"))
        w, h = panel.PrintLayout()["paperTile"]
        v.exportOverlay.bounds = (0, 0, w * 2, h)
        panel.SetBounds(v.exportOverlay.bounds)
        for kind in ("png", "svg"):
            path = folder / ("batch." + kind)
            jobs = panel.ExportJobs(path, kind)
            assert len(jobs) == 2 and all(render["titleBlock"]["sheetNumber"] == "AB-UNCHANGED" for target, render in jobs)
            dialog = ExportProgressDialog(panel, path, kind, False)
            assert dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted, dialog.error
            for target, render in jobs:
                assert target.exists()
                expected = RenderPlan(**render)
                if kind == "png":
                    assert QtGui.QImage(str(target)) == expected
                else:
                    assert target.read_bytes() == expected
            previous = [target.read_bytes() for target, render in jobs]
            broken = [(target, dict(render, scale = -1) if index == 1 else render) for index, (target, render) in enumerate(jobs)]
            failed = ExportProgressDialog(panel, path, kind, False)
            with patch.object(panel, "ExportJobs", return_value = broken):
                assert failed.exec() == QtWidgets.QDialog.DialogCode.Rejected
            assert [target.read_bytes() for target, render in jobs] == previous
            assert not list(folder.glob(".planner-export-*"))
            cancelled = ExportProgressDialog(panel, path, kind, False)
            cancelled.process.started.connect(cancelled.reject)
            assert cancelled.exec() == QtWidgets.QDialog.DialogCode.Rejected
            assert [target.read_bytes() for target, render in jobs] == previous
            assert not list(folder.glob(".planner-export-*"))
            # Publishing errors roll back previously replaced pages as well.
            import planner_app.ui.export_progress as progress
            realReplace = progress.os.replace
            replacements = []
            def Replace(source, target):
                if Path(target) == jobs[1][0] and not replacements:
                    replacements.append(target)
                    raise OSError("Simulated publish failure")
                return realReplace(source, target)
            changed = [(target, dict(render, titleBlock = dict(render["titleBlock"], sheetNumber = "CHANGED"))) for target, render in jobs]
            publication = ExportProgressDialog(panel, path, kind, False)
            with patch.object(panel, "ExportJobs", return_value = changed), patch.object(progress.os, "replace", side_effect = Replace):
                assert publication.exec() == QtWidgets.QDialog.DialogCode.Rejected
            assert replacements and [target.read_bytes() for target, render in jobs] == previous
            assert not list(folder.glob(".planner-export-*"))
        optimized = ExportProgressDialog(panel, folder / "optimized.png", "png", True)
        assert optimized.exec() == QtWidgets.QDialog.DialogCode.Accepted, optimized.error
        for target, render in panel.ExportJobs(folder / "optimized.png", "png"):
            image = QtGui.QImage(str(target))
            assert image.size() == QtCore.QSize(*panel.PrintLayout()["pixels"])
            assert image.colorCount() <= 256 and abs(image.dotsPerMeterX() * .0254 - 96) < .02
        saved = main.BuildProjectData(includeHistory = False)
        decoded = DecodeProject(copy.deepcopy(saved), v.furnishingDefinitions)
        assert decoded[5]["exportSettings"]["scaleMode"] == "Print"
        assert decoded[5]["exportSettings"]["pageOrientation"] == "Landscape"
        main.ApplyProject(decoded, None)
        assert main.sidebarTabs.currentWidget() is main.buildScrollArea
        main.sidebarTabs.setCurrentWidget(panel)
        assert panel.scaleModeTabs.tabText(panel.scaleModeTabs.currentIndex()) == "Print"
        assert v.exportOverlay.printMode and len(panel.ExportJobs(folder / "restored.png", "png")) == 2
        diagnostics = root / "diagnostics" / "print"
        diagnostics.mkdir(parents = True, exist_ok = True)
        fullSize.save(str(diagnostics / "a4-landscape-300ppi.png"))
        main.grab().save(str(diagnostics / "controls-and-page-grid.png"))
    print("Print A4 layout, selection, dragging/undo, page output and batch failure checks passed")


if __name__ == "__main__":
    Main()
