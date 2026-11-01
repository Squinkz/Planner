"""PDF categories, Print-only modes, multipage pixels/vectors and atomic export."""
import copy
import os
from pathlib import Path
import re
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
import numpy as np
from PySide6 import QtCore, QtGui, QtPdf, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.export_plan import RenderPlan
from planner_app.models import Wall
from planner_app.project_codec import DecodeProject
from planner_app.ui.export_progress import ExportProgressDialog


def Main():
    with ExampleWindow() as (main, folder):
        panel, view = main.exportPanel, main.viewport
        corners = [(1000, 1000), (50000, 1000), (50000, 16000), (1000, 16000)]
        walls = [Wall(QtCore.QPointF(*first), QtCore.QPointF(*second), 200)
                 for first, second in zip(corners, corners[1:] + corners[:1])]
        for wall in walls:
            wall.material = "Brick"
        InstallScene(main, walls)
        main.sidebarTabs.setCurrentWidget(panel)
        assert [panel.typeField.itemText(index) for index in range(panel.typeField.count())] == [
            "Raster", "PNG (raster)", "Optimized PNG (raster)", "PDF (raster)", "Vector", "SVG (vector)", "PDF (vector)"]
        for index in (0, 4):
            assert panel.typeField.model().item(index).flags() == QtCore.Qt.ItemFlag.NoItemFlags
            assert panel.typeField.model().item(index).background() == panel.pageSizeHeadings[0].background()
        panel.SetScaleOption("scaleMode", "Architectural")
        panel.SetScaleOption("architecturalScale", 50)
        crop = (-3000, -2000, 24000, 18000)
        view.exportOverlay.bounds = crop
        panel.SetBounds(crop)
        panel.ResetExportHistory()
        panel.typeField.setCurrentIndex(panel.typeField.findData("PDF_RASTER"))
        assert panel.overrides["scaleMode"] == "Print" and len(panel.exportUndoHistory) == 1
        assert [panel.scaleModeTabs.isTabVisible(index) for index in range(3)] == [True, False, False]
        panel.SetScaleOption("scaleMode", "Digital")
        assert panel.overrides["scaleMode"] == "Print"
        panel.UndoExport()
        assert panel.typeField.currentData() == "PNG" and panel.overrides["scaleMode"] == "Architectural"
        assert view.exportOverlay.bounds == crop and panel.overrides["architecturalScale"] == 50
        assert all(panel.scaleModeTabs.isTabVisible(index) for index in range(3))
        panel.RedoExport()
        assert panel.typeField.currentData() == "PDF_RASTER" and panel.overrides["scaleMode"] == "Print"
        panel.SetScaleOption("dpi", 96)
        panel.SetScaleOption("pageOrigin", [0, 0])
        panel.SetOverride("canvasTheme", "Light Canvas")
        panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "None", projectName = "PDF export",
            drawingTitle = "Ground Floor Plan", address = "12 Oak Avenue\nParkview\nJohannesburg",
            comments = "Verify dimensions on site.", revision = "B", sheetNumber = "A-101"))
        panel.SetOverride("scaleBar", dict(enabled = True))
        panel.SetBorder("Ruler + Reference Zones")
        layout = panel.PrintLayout()
        width, height = layout["paperTile"]
        view.exportOverlay.bounds = (0, 0, 2 * width, height)
        panel.SetBounds(view.exportOverlay.bounds)
        diagnostics = Path(__file__).resolve().parents[1] / "diagnostics" / "pdf-export"
        diagnostics.mkdir(parents = True, exist_ok = True)
        for kind, renderFormat in (("PDF_RASTER", "png"), ("PDF_VECTOR", "svg")):
            panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
            panel.SetOverride("vignetteEnabled", True)
            panel.SetOverride("vignetteStrength", .4)
            assert view.exportOverlay.outputFormat == renderFormat
            assert panel.compositeSection.isHidden() == (kind == "PDF_VECTOR")
            assert panel.dpiRow.isHidden() == (kind == "PDF_VECTOR")
            panel.fileNameField.setText("result.svg")
            assert panel.OutputPath().suffix == ".pdf" and panel.OutputPath().name == "result.pdf"
            path = folder / (kind.lower() + ".pdf")
            jobs = panel.ExportJobs(path, kind.lower())
            assert len(jobs) == 2 and all(target == path for target, render in jobs)
            assert all(render["outputFormat"] == renderFormat for target, render in jobs)
            expected = [RenderPlan(**dict(render, outputFormat = "png",
                vignetteStrength = render["vignetteStrength"] if kind == "PDF_RASTER" else 0)) for target, render in jobs]
            dialog = ExportProgressDialog(panel, path, kind.lower(), False, jobs = jobs)
            assert dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted, dialog.error
            assert len(dialog.outputFiles) == 1 and not list(folder.glob(".planner-export-*"))
            encoded = path.read_bytes()
            (diagnostics / path.name).write_bytes(encoded)
            if kind == "PDF_VECTOR":
                from planner_app.graphics.svg_preview import SvgPreviewRenderer
                vector = RenderPlan(**jobs[0][1])
                (diagnostics / "vector-reference.svg").write_bytes(vector)
                renderer = SvgPreviewRenderer(vector)
                sample = QtGui.QImage(expected[0].size(), QtGui.QImage.Format.Format_ARGB32)
                sample.fill(QtCore.Qt.GlobalColor.white)
                with QtGui.QPainter(sample) as painter:
                    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
                    renderer.render(painter)
                sample.save(str(diagnostics / "vector-reference.png"))
                renderer.deleteLater()
            assert encoded.startswith(b"%PDF-") and encoded.rstrip().endswith(b"%%EOF")
            images = len(re.findall(rb"/Subtype\s*/Image\b", encoded))
            if kind == "PDF_RASTER":
                assert images >= 2
                assert b"/DCTDecode" not in encoded, "Raster PDF introduced JPEG loss"
                assert re.search(rb"/Width\s+" + str(expected[0].width()).encode() + rb"\b", encoded)
                assert re.search(rb"/Height\s+" + str(expected[0].height()).encode() + rb"\b", encoded)
            else:
                assert images == 0, ("Vector geometry was rasterized", images)
                assert not re.search(rb"/Type\s*/Font\b", encoded), "Outlined text became a font dependency"
            document = QtPdf.QPdfDocument()
            assert document.load(str(path)).value == 0
            assert document.pageCount() == 2
            for index, reference in enumerate(expected):
                points = document.pagePointSize(index)
                assert abs(points.width() * 25.4 / 72 - layout["paper"][0]) < .1
                assert abs(points.height() * 25.4 / 72 - layout["paper"][1]) < .1
                actual = document.render(index, reference.size()).convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
                reference = reference.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
                assert not actual.isNull()
                first = np.frombuffer(actual.constBits(), dtype = np.uint8).reshape(actual.height(), actual.bytesPerLine())
                second = np.frombuffer(reference.constBits(), dtype = np.uint8).reshape(reference.height(), reference.bytesPerLine())
                difference = np.abs(first.astype(np.int16) - second.astype(np.int16))
                actual.save(str(diagnostics / f"{kind.lower()}-{index + 1}.png"))
                reference.save(str(diagnostics / f"{kind.lower()}-{index + 1}-reference.png"))
                assert difference.mean() < 3 and (difference > 32).mean() < .03, (kind, index, difference.mean())
                # Catch filled glyphs accidentally acquiring outlines: their
                # sparse ink is too small to dominate the whole-page average.
                titleWidth = round(40 / layout["paper"][0] * reference.width())
                assert difference[:, -titleWidth * 4:].mean() < 3, ("Title-block ink changed", kind, index)
            document.close()
            from shiboken6 import delete
            delete(document)
            (diagnostics / path.name).write_bytes(encoded)
            dialog.deleteLater()
            panel.folderField.setText(str(folder))
            panel.fileNameField.setText(path.stem)
            with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.No) as prompt:
                panel.Export()
            assert prompt.call_args.kwargs["informativeText"] == str(path), "PDF overwrite prompt repeated its destination per page"
            assert path.read_bytes() == encoded
            # Failure on the second page must not publish a partial PDF.
            broken = panel.ExportJobs(path, kind.lower())
            broken[1][1]["scale"] = -1
            failed = ExportProgressDialog(panel, path, kind.lower(), False, jobs = broken)
            assert failed.exec() == QtWidgets.QDialog.DialogCode.Rejected and failed.error
            assert path.read_bytes() == encoded and not list(folder.glob(".planner-export-*"))
            failed.deleteLater()
            cancelled = ExportProgressDialog(panel, path, kind.lower(), False)
            cancelled.process.started.connect(cancelled.reject)
            assert cancelled.exec() == QtWidgets.QDialog.DialogCode.Rejected and cancelled.cancelled
            assert path.read_bytes() == encoded and not list(folder.glob(".planner-export-*"))
            cancelled.deleteLater()
            data = main.BuildProjectData(includeHistory = False)
            decoded = DecodeProject(data, view.furnishingDefinitions)
            assert decoded[5]["exportSettings"]["fileType"] == kind
            main.ApplyProject(decoded, folder / "saved.plan")
            main.sidebarTabs.setCurrentWidget(panel)
            assert panel.typeField.currentData() == kind
            assert [panel.scaleModeTabs.isTabVisible(index) for index in range(3)] == [True, False, False]
            brokenData = copy.deepcopy(data)
            brokenData["settings"]["exportSettings"]["scaleMode"] = "Architectural"
            try:
                DecodeProject(brokenData, view.furnishingDefinitions)
            except ValueError:
                pass
            else:
                raise AssertionError("Accepted PDF outside Print mode")
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        assert all(panel.scaleModeTabs.isTabVisible(index) for index in range(3))
        panel.SetScaleOption("scaleMode", "Architectural")
        assert view.exportOverlay.bounds == crop and panel.overrides["architecturalScale"] == 50
    print("PASS: grouped types, Print-only PDFs, independent mode restore, vector/outlined and raster multipage output, page sizes, parity, failure and cancellation")


if __name__ == "__main__":
    Main()
