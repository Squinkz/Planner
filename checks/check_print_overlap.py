"""Signed overlap uses project lengths and identical preview/export page cuts."""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner_app.print_layout import PrintPageLayout, PrintDrawingBounds, SelectedPrintPages, UpgradePrintOverlap
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan
from planner_app.models import Wall
from fixtures.parity_examples import ExampleWindow, InstallScene


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    options = dict(architecturalScale = 100, pageOverlap = [500, -250])
    reference = None
    for ppi in (96, 150, 300, 600):
        layout = PrintPageLayout(dict(options, dpi = ppi), 56, dict(enabled = True, position = "Right"))
        assert layout["stride"] == (layout["tile"][0] - 500, layout["tile"][1] + 250)
        if reference is not None:
            assert layout["stride"] == reference["stride"] and layout["tile"] == reference["tile"]
        reference = layout
        w, h = layout["paperTile"]
        stepX, stepY = layout["paperStride"]
        assert (stepX, stepY) == (w, h)
        origin = (1234, -678)
        first = PrintDrawingBounds((*origin, w, h), layout, origin)
        right = PrintDrawingBounds((origin[0] + stepX, origin[1], w, h), layout, origin)
        above = PrintDrawingBounds((origin[0], origin[1] + stepY, w, h), layout, origin)
        assert abs(first[0] + first[2] - right[0] - 500) < 1e-8
        assert abs(above[1] - first[1] - first[3] - 250) < 1e-8
    assert len(SelectedPrintPages((0, 0, 180, 220), (100, 100), stride = (80, 120))) == 4
    assert not SelectedPrintPages((105, 0, 10, 100), (100, 100), fullyEnclosed = False, stride = (120, 100))
    for overlap in ([2000, 1000], [-1500, -700]):
        old = dict(scaleMode = "Print", pageOverlap = overlap, pageOrigin = [1234, -678], architecturalScale = 100)
        extent = (29700, 21000)
        old["bounds"] = [1234, -678, extent[0] * 2 - overlap[0], extent[1] * 2 - overlap[1]]
        upgraded = UpgradePrintOverlap(old)
        assert upgraded["bounds"][2:] == [extent[0] * 2, extent[1] * 2]
        assert all(abs(upgraded["pageOrigin"][axis] + upgraded["pageOverlapOffset"][axis] - old["pageOrigin"][axis]) < 1e-7 for axis in range(2))
        assert UpgradePrintOverlap(upgraded) is upgraded
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(0, 0), QtCore.QPointF(35000, 0), 200)])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetBorder("Plain")
        panel.SetScaleOption("dpi", 96)
        panel.SetScaleOption("pageOrigin", [1234, -678])
        overlay = v.exportOverlay
        width, height = panel.PrintLayout()["paperTile"]
        overlay.bounds = (1234, -678, width * 2, height * 2)
        panel.SetBounds(overlay.bounds)
        assert panel.pageOverlapRow.isEnabled() and panel.pageOverlapLabel.isEnabled()
        panel.SetScaleOption("pageOverlap", [500, -250])
        overlay.bounds = (1234, -678, width, height)
        panel.SetBounds(overlay.bounds)
        assert "1 page selected" in panel.printNote.text()
        assert not panel.pageOverlapLabel.isEnabled() and panel.pageOverlapRow.isEnabled()
        assert panel.pageOverlapReset.isEnabled() and all(not field.isEnabled() for field in panel.pageOverlapFields)
        assert panel.overrides["pageOverlap"] == [500, -250]
        panel.ResetExportHistory()
        panel.pageOverlapReset.click()
        assert panel.overrides["pageOverlap"] == [0, 0]
        assert not panel.pageOverlapReset.isEnabled() and all(not field.isEnabled() for field in panel.pageOverlapFields)
        assert "1 page selected" in panel.printNote.text()
        panel.UndoExport()
        assert panel.overrides["pageOverlap"] == [500, -250] and panel.pageOverlapReset.isEnabled()
        assert all(not field.isEnabled() for field in panel.pageOverlapFields)
        overlay.bounds = (1234, -678, width * 2, height * 2)
        panel.SetBounds(overlay.bounds)
        assert panel.pageOverlapRow.isEnabled() and panel.pageOverlapLabel.isEnabled()
        assert panel.pageOverlapReset.isEnabled() and all(field.isEnabled() for field in panel.pageOverlapFields)
        assert panel.overrides["pageOverlap"] == [500, -250]
        panel.SetScaleOption("pageOverlap", [0, 0])
        v.zoom = min(v.DrawingRect().width() / (width * 2.1), v.DrawingRect().height() / (height * 2.1)) / v.basePixelsPerMillimeter
        v.panOffset += v.DrawingRect().center() - v.WorldToViewport(QtCore.QPointF(1234 + width, -678 + height))
        # The crop includes asymmetric partial margins: its centre differs
        # from both the page group's centre and the canvas origin.
        overlay.bounds = (1234 - width * .1, -678 - height * .2, width * 2.3, height * 2.3)
        panel.SetBounds(overlay.bounds)
        for overlap in ([2000, 1000], [-1500, -700], [0, 0]):
            before = overlay.bounds
            centre = QtCore.QPointF(before[0] + before[2] / 2, before[1] + before[3] / 2)
            camera = (v.zoom, QtCore.QPointF(v.panOffset))
            origin = overlay.pageOrigin
            previous = panel.PrintLayout()
            anchor = ((centre.x() - origin[0]) / width - .5, (centre.y() - origin[1]) / height - .5)
            anchored = [origin[axis] + previous["offset"][axis] + anchor[axis] * previous["stride"][axis] for axis in range(2)]
            panel.SetScaleOption("pageOverlap", overlap)
            layout = panel.PrintLayout()
            selected = SelectedPrintPages(overlay.bounds, layout["paperTile"], overlay.pageOrigin, stride = layout["paperStride"])
            assert len(selected) == 4
            assert overlay.bounds == before and overlay.pageOrigin == origin
            assert layout["paperStride"] == layout["paperTile"]
            assert all(abs(origin[axis] + layout["offset"][axis] + anchor[axis] * layout["stride"][axis] - anchored[axis]) < 1e-7
                       for axis in range(2)), "Coverage changed around the canvas origin instead of the crop centre"
            x, y, w, h = overlay.bounds
            assert abs(x + w / 2 - centre.x()) < 1e-7 and abs(y + h / 2 - centre.y()) < 1e-7
            assert (v.zoom, v.panOffset) == camera
            assert w == before[2] and h == before[3]
            first, second = sorted(selected)[:2]
            assert first[2:] == second[2:] == (width, height)
            for axis in (0, 1):
                point = list((x + w * .37, y + h * .37))
                point[axis] = overlay.pageOrigin[axis] + layout["paperStride"][axis]
                assert overlay.HitPrintGuide(v.WorldToViewport(QtCore.QPointF(*point))) == axis
        for mode, suffix, value, millimeters in (("Meters", "m", .125, 125), ("Centimeters", "cm", 12.5, 125),
                ("Millimeters", "mm", 125, 125), ("Inches", "in", 2, 50.8), ("Feet and Inches", "ft", .5, 152.4)):
            panel.projectView["unitsMode"] = mode
            panel.SetOverride("unitsMode", "Millimeters")
            assert panel.pageOverlapFields[0].suffix() == (" " + suffix if suffix != "ft" else "")
            panel.pageOverlapFields[0].setValue(value)
            panel.pageOverlapFields[1].setValue(-value)
            assert all(abs(a - b) < 1e-6 for a, b in zip(panel.overrides["pageOverlap"], (millimeters, -millimeters)))
        panel.projectView["unitsMode"] = "Millimeters"
        panel.RefreshControls()
        panel.SetScaleOption("pageOverlap", [500, -250])
        for kind in ("PNG", "SVG"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
            overlay.printPreviewTimer.stop()
            v.grab()
            assert not overlay.previewError, overlay.previewError
            jobs = panel.ExportJobs(folder / ("overlap." + kind.lower()), kind.lower())
            assert len(jobs) == 4
            for page, (path, arguments) in zip(sorted(overlay.printPageCache, key = lambda page: (-page[1], page[0])), jobs):
                assert arguments["bounds"] == PrintDrawingBounds(page, panel.PrintLayout(), overlay.pageOrigin)
                if kind == "PNG":
                    assert overlay.printPageCache[page] == RenderPlan(**arguments)
            if kind == "SVG":
                scene = overlay.printVectorRenderer
                with patch.object(overlay, "renderPrintScene", side_effect = AssertionError("Overlap rebuilt model vectors")):
                    panel.SetScaleOption("pageOverlap", [600, -300])
                    overlay.printPreviewTimer.stop()
                    v.grab()
                    assert not overlay.previewError and overlay.printVectorRenderer is scene
        panel.ResetExportHistory()
        before = copy.deepcopy(panel.overrides)
        panel.pageOverlapFields[0].setValue(700)
        assert panel.overrides["pageOverlap"][0] == 700
        panel.UndoExport()
        assert panel.overrides == before
        panel.RedoExport()
        assert panel.overrides["pageOverlap"][0] == 700
        before = copy.deepcopy(panel.overrides)
        panel.BeginExportGesture()
        panel.pageOverlapFields[1].setValue(-400)
        panel.FinishPageOverlapDrag(True)
        assert panel.overrides == before
        panel.ResetExportHistory()
        assert panel.pageOverlapReset.isEnabled()
        panel.pageOverlapReset.click()
        assert panel.overrides["pageOverlap"] == [0, 0]
        assert all(field.value() == 0 for field in panel.pageOverlapFields)
        assert not panel.pageOverlapReset.isEnabled() and len(panel.exportUndoHistory) == 1
        panel.UndoExport()
        assert panel.overrides == before and panel.pageOverlapReset.isEnabled()
        panel.RedoExport()
        assert panel.overrides["pageOverlap"] == [0, 0]
        saved = main.BuildProjectData(includeHistory = False)
        decoded = DecodeProject(copy.deepcopy(saved), v.furnishingDefinitions)
        assert decoded[5]["exportSettings"]["pageOverlap"] == panel.overrides["pageOverlap"]
        panel.pageOverlapFields[0].setValue(1e9)
        assert panel.overrides["pageOverlap"][0] < panel.PrintLayout()["tile"][0]
        panel.SetScaleOption("pageSize", "A0")
        panel.SetScaleOption("pageOverlap", [50000, 40000])
        panel.SetScaleOption("pageSize", "A4")
        layout = panel.PrintLayout()
        assert all(amount < size for amount, size in zip(panel.overrides["pageOverlap"], layout["tile"]))
        assert len(SelectedPrintPages(overlay.bounds, layout["paperTile"], overlay.pageOrigin, stride = layout["paperStride"])) == 4
    print("Signed overlap, project/imperial units, PPI invariance, PNG/SVG cuts, vector reuse, save and undo passed")


if __name__ == "__main__":
    Main()
