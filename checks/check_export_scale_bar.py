"""Scale bars share calibrated geometry across export modes, previews and files."""
import copy
import math
import os
from pathlib import Path
import sys
from xml.etree import ElementTree
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall
from planner_app.graphics import palette
from planner_app.graphics.icons import UiIcon
from planner_app.graphics.scale_bar import DrawScaleBar, ScaleBarLayout
from planner_app.graphics.text import TextPath
from planner_app.export_plan import RenderPlan
from planner_app.export_settings import NormalizeScaleBar, scaleBarDivisions, scaleBarStyles
from planner_app.project_codec import DecodeProject
from planner_app.ui.export_progress import ExportProgressDialog
from planner_app.print_layout import PrintPageLayout, printPaperSizes


def Main():
    for options in ({"divisions": 0}, {"widthMM": float("nan")}, {"enabled": 1}, {"position": "Other"},
                    {"divisionMode": "Other"}, {"divisionMode": None}, {"style": "Other"}, {"style": None}):
        try:
            NormalizeScaleBar(options)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid scale bar options accepted")
    assert NormalizeScaleBar(dict(enabled = True, position = "Top right", widthMM = 50, widthPixels = 200, divisions = 6)) == dict(enabled = True, position = "Top right")
    for style in scaleBarDivisions:
        assert NormalizeScaleBar(dict(divisionMode = style)) == dict(divisionMode = style)
    for style in scaleBarStyles:
        assert NormalizeScaleBar(dict(style = style)) == dict(style = style)
    for legacy, current in (("Progressive", "Progressive"), ("Equal divisions", "Equal"), ("Subdivided end", "Subdivided")):
        assert NormalizeScaleBar(dict(style = legacy)) == dict(divisionMode = current, style = "Alternating")
    assert NormalizeScaleBar(dict(style = "Equal divisions", divisionMode = "Subdivided")) == dict(divisionMode = "Subdivided", style = "Alternating")
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(1000, 7000), QtCore.QPointF(7000, 7000), 200)])
        main.sidebarTabs.setCurrentWidget(panel)
        names = list(panel.sectionButtons)
        assert names.index("Scale Bar") + 1 == names.index("Title Block")
        assert not panel.scaleBarEnabled.isChecked() and not panel.scaleBarOptions.isEnabled()
        assert panel.scaleBarPositionButtons["Bottom left"].isChecked()
        assert len(panel.scaleBarPositionButtons) == 4 and panel.scaleBarPositionGroup.exclusive()
        for position, rotation in (("Bottom left", 0), ("Bottom right", 270), ("Top left", 90), ("Top right", 180)):
            button = panel.scaleBarPositionButtons[position]
            assert not button.isEnabled() and button.toolTip() == position
            assert button.objectName() == panel.titleBlockPositionButtons["Right"].objectName()
            expected = UiIcon("align_corner_bl", rotation = rotation)
            for mode in (QtGui.QIcon.Mode.Normal, QtGui.QIcon.Mode.Disabled):
                assert button.icon().pixmap(QtCore.QSize(24, 24), mode).toImage() == expected.pixmap(QtCore.QSize(24, 24), mode).toImage()
        assert panel.scaleBarDivisionMode.currentText() == "Subdivided"
        assert not panel.scaleBarDivisionMode.isEnabled()
        assert tuple(panel.scaleBarDivisionMode.itemText(index) for index in range(panel.scaleBarDivisionMode.count())) == scaleBarDivisions
        assert panel.scaleBarStyle.currentText() == "Stepped" and not panel.scaleBarStyle.isEnabled()
        assert tuple(panel.scaleBarStyle.itemText(index) for index in range(panel.scaleBarStyle.count())) == scaleBarStyles
        assert not hasattr(panel, "scaleBarWidth") and not hasattr(panel, "scaleBarDivisions")
        assert panel.scaleBarOptions.layout().rowCount() == 3
        assert panel.scaleBarEnableForm.horizontalSpacing() == panel.titleBlockEnableForm.horizontalSpacing()
        panel.SetOverride("showGrid", False)
        panel.SetOverride("vignetteEnabled", False)
        panel.SetOverride("texture", None)
        panel.SetOverride("gridOrigin", [137, -263])
        panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "None"))
        for mode in ("Digital", "Architectural", "Print"):
            panel.SetScaleOption("scaleMode", mode)
            panel.SetScaleOption("architecturalScale", 100)
            panel.SetScaleOption("dpi", 150)
            panel.scaleBarEnabled.setChecked(True)
            overlay = v.exportOverlay
            if mode == "Print":
                panel.SetScaleOption("pageOrigin", [0, 0])
                width, height = panel.PrintLayout()["paperTile"]
                overlay.bounds = (0, 0, width * 2, height)
            else:
                overlay.bounds = (0, 0, 12000, 9000)
            panel.SetBounds(overlay.bounds)
            x, y, width, height = overlay.bounds
            v.zoom = min(v.DrawingRect().width() / width, v.DrawingRect().height() / height) * .8 / v.basePixelsPerMillimeter
            v.panOffset += v.DrawingRect().center() - v.WorldToViewport(QtCore.QPointF(x + width / 2, y + height / 2))
            for kind in ("PNG", "SVG"):
                panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
                for sampleIndex in range(12):
                    position = ("Bottom left", "Bottom right", "Top left", "Top right")[sampleIndex % 4]
                    divisionMode = scaleBarDivisions[sampleIndex % 3]
                    style = scaleBarStyles[sampleIndex // 3 % 3]
                    panel.scaleBarDivisionMode.setCurrentText(divisionMode)
                    panel.scaleBarStyle.setCurrentText(style)
                    panel.scaleBarPositionButtons[position].click()
                    assert panel.scaleBarPositionButtons[position].isChecked()
                    assert sum(button.isChecked() for button in panel.scaleBarPositionButtons.values()) == 1
                    overlay.printPreviewTimer.stop()
                    overlay.navigationTimer.stop()
                    preview = v.grab().toImage()
                    assert not overlay.previewError, overlay.previewError
                    options = panel.overrides["scaleBar"]
                    assert options.get("divisionMode", "Subdivided") == divisionMode
                    assert options.get("style", "Alternating") == style
                    jobs = panel.ExportJobs(folder / "bar.png", kind.lower())
                    assert len(jobs) == (2 if mode == "Print" else 1)
                    for index, (path, arguments) in enumerate(jobs):
                        scale = panel.PreviewScalePerMeter()
                        border = overlay.borderSize if overlay.drawRuler else 0
                        bounds = arguments["bounds"]
                        plot = QtCore.QRectF(border, border, bounds[2] * scale / 1000, bounds[3] * scale / 1000)
                        layout = ScaleBarLayout(plot, options, scale, v.unitsMode, v.font(), bounds, v.gridOrigin)
                        assert math.isclose(layout["distance"], 10000)
                        assert plot.contains(layout["rect"])
                        expectedMarks = {"Progressive": (0, 1000, 2000, 5000, 10000),
                                         "Equal": (0, 2000, 4000, 6000, 8000, 10000),
                                         "Subdivided": (0, 1000, 2000, 4000, 6000, 8000, 10000)}[divisionMode]
                        assert len(layout["labels"]) == len(expectedMarks)
                        assert layout["distances"] == expectedMarks
                        assert layout["fractions"] == tuple(mark / expectedMarks[-1] for mark in expectedMarks)
                        point = QtCore.QPointF(layout["bar"].left() + layout["bar"].width() * layout["fractions"][1] / 2,
                                              layout["bar"].top() + layout["bar"].height() / 4)
                        if style == "Stepped":
                            # Thin strokes can cover only a fraction of a screen
                            # pixel when two full sheets are fitted in the view.
                            point = QtCore.QPointF(layout["bar"].left() + layout["bar"].width() * layout["fractions"][1],
                                                   layout["bar"].center().y())
                        if mode == "Print":
                            page = sorted(overlay.printPageCache)[index]
                            target = overlay.PrintPageRect(page)
                            size = overlay.PrintLayout()["baselinePixels"]
                            sample = target.topLeft() + QtCore.QPointF(point.x() * target.width() / size[0], point.y() * target.height() / size[1])
                            if kind == "PNG":
                                assert overlay.printPageCache[page] == RenderPlan(**arguments)
                                if index == 0 and position == "Bottom left":
                                    destination = Path(__file__).resolve().parents[1] / "diagnostics" / "scale-bar"
                                    destination.mkdir(exist_ok = True)
                                    overlay.printPageCache[page].save(str(destination / "print-page.png"))
                                    preview.save(str(destination / "preview.png"))
                        else:
                            first = v.WorldToViewport(QtCore.QPointF(bounds[0], bounds[1] + bounds[3]))
                            factor = v.basePixelsPerMillimeter * v.zoom / (scale / 1000)
                            sample = first + (point - QtCore.QPointF(border, border)) * factor
                        actual = preview.pixelColor((sample * v.devicePixelRatioF()).toPoint())
                        expected = QtGui.QColor(palette.themeColors["objectOutline"])
                        background = QtGui.QColor(palette.themeColors["canvas"])
                        inkDistance = sum(abs(a - b) for a, b in zip(actual.getRgb(), expected.getRgb()))
                        backgroundDistance = sum(abs(a - b) for a, b in zip(actual.getRgb(), background.getRgb()))
                        if style == "Stepped":
                            previewFactor = target.width() / size[0] if mode == "Print" else factor
                            pixels = [((sample + QtCore.QPointF((fraction - layout["fractions"][1]) * layout["bar"].width() * previewFactor, 0))
                                       * v.devicePixelRatioF()).toPoint() for fraction in layout["fractions"]]
                            coverage = max(sum(abs(a - b) for a, b in zip(preview.pixelColor(pixel + QtCore.QPoint(dx, dy)).getRgb(), background.getRgb()))
                                           for pixel in pixels for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                            assert coverage > 0, (mode, kind, position, style)
                        else:
                            assert inkDistance < backgroundDistance, (mode, kind, position, style, actual.name(), expected.name())
                        if kind == "SVG":
                            svg = ElementTree.fromstring(RenderPlan(**arguments))
                            assert not svg.findall(".//{http://www.w3.org/2000/svg}text"), "Scale bar labels were not outlined"
            before = dict(panel.overrides["scaleBar"])
            panel.SetScaleBarOption("position", "Top left")
            panel.UndoExport()
            assert panel.overrides["scaleBar"] == before
            assert panel.scaleBarPositionButtons[before["position"]].isChecked()
            panel.scaleBarDivisionMode.setCurrentText("Equal")
            panel.UndoExport()
            assert panel.overrides["scaleBar"] == before and panel.scaleBarDivisionMode.currentText() == before["divisionMode"]
            panel.scaleBarStyle.setCurrentText("Checker")
            panel.UndoExport()
            assert panel.overrides["scaleBar"] == before and panel.scaleBarStyle.currentText() == before["style"]
        shared = v.exportOverlay.printVectorRenderer
        with patch.object(v.exportOverlay, "renderPrintScene", side_effect = AssertionError("Scale bar edit rebuilt model SVG")):
            panel.scaleBarDivisionMode.setCurrentText("Subdivided")
            panel.scaleBarStyle.setCurrentText("Stepped")
            panel.SetScaleBarOption("position", "Bottom right")
            v.grab()
            assert not v.exportOverlay.previewError
            v.exportOverlay.printPreviewTimer.stop()
            v.grab()
            assert v.exportOverlay.printVectorRenderer is shared and not v.exportOverlay.previewError
        dialog = ExportProgressDialog(panel, folder / "bars.png", "png", False)
        assert dialog.exec() == dialog.DialogCode.Accepted, dialog.error
        for path, arguments in panel.ExportJobs(folder / "bars.png", "png"):
            assert QtGui.QImage(str(path)) == RenderPlan(**arguments), "Worker scale bar output differs"
        for units in ("Adaptive Metric", "Meters", "Centimeters", "Millimeters", "Feet and Inches", "Inches"):
            layout = ScaleBarLayout(QtCore.QRectF(0, 0, 3508, 2480), {}, 300 * 1000 / (25.4 * 100), units, v.font())
            assert math.isclose(layout["distance"], 10668 if units == "Feet and Inches" else 10160 if units == "Inches" else 10000)
            assert layout["labels"][0].startswith("0") and layout["labels"][-1]
        for denominator, distance in ((10, 1000), (20, 2000), (25, 2500), (50, 5000), (75, 5000),
                                      (100, 10000), (150, 15000), (200, 20000), (320, 30000),
                                      (500, 50000), (640, 50000), (1000, 100000)):
            scale = 300 * 1000 / (25.4 * denominator)
            layout = ScaleBarLayout(QtCore.QRectF(0, 0, 3508, 2480), {}, scale, "Meters", v.font())
            assert math.isclose(layout["distance"], distance), (denominator, layout["distance"])
            assert math.isclose(layout["bar"].width() * 25.4 / 300, distance / denominator)
            legacy = ScaleBarLayout(QtCore.QRectF(0, 0, 3508, 2480), dict(widthMM = 5, widthPixels = 10, divisions = 1),
                                    scale, "Meters", v.font())
            assert legacy["bar"] == layout["bar"] and legacy["labels"] == layout["labels"]
        # Digital density changes choose useful real-world totals and derive
        # their exact pixel width; they do not stretch a fixed distance label.
        for scale in (.01, .1, 1, 75, 100, 250, 1000, 1000000):
            layout = ScaleBarLayout(QtCore.QRectF(0, 0, 3508, 2480), {}, scale, "Meters", v.font())
            assert math.isclose(layout["bar"].width() / scale * 1000, layout["distance"])
            targetWidth = 100 * 300 / 25.4
            assert .625 * targetWidth <= layout["bar"].width() <= 1.375 * targetWidth
        for scale in (0, -1, float("nan"), float("inf")):
            try:
                ScaleBarLayout(QtCore.QRectF(0, 0, 1000, 1000), {}, scale, "Meters", v.font())
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid scale accepted")
        sample = QtGui.QImage(2000, 1500, QtGui.QImage.Format.Format_ARGB32)
        sample.fill(QtGui.QColor(palette.themeColors["canvas"]))
        plot = QtCore.QRectF(0, 0, sample.width(), sample.height())
        scale = 300 * 1000 / (25.4 * 100)
        alternating = dict(enabled = True, divisionMode = "Progressive", style = "Alternating")
        layout = ScaleBarLayout(plot, alternating, scale, "Meters", v.font())
        assert layout["labels"] == ["0", "1", "2", "5", "10 m"]
        assert abs(TextPath("0123456789", layout["font"].toString(), 96)[0].boundingRect().height() * 25.4 / 300 - 2.0) < .1
        assert layout["font"].family() == "D-DIN Condensed"
        otherFont = ScaleBarLayout(plot, alternating, scale, "Meters", QtGui.QFont("Noto Sans"))
        assert otherFont["font"].family() == "D-DIN Condensed" and otherFont["bar"] == layout["bar"]
        digital = ScaleBarLayout(plot, alternating, 100, "Meters", v.font())
        assert digital["font"].pixelSize() == layout["font"].pixelSize()
        assert digital["bar"].height() == layout["bar"].height()
        assert digital["padding"] == layout["padding"] and digital["labelPadding"] == layout["labelPadding"]
        assert digital["labels"][-1] == "10 m" and digital["bar"].width() == 1000
        # At 300 PPI a 10 m bar at 100 px/m is 84.67 mm wide. A physical
        # 1:100 bar is 100 mm; both use the same lettering, strokes and inset.
        assert math.isclose(digital["bar"].width() * 25.4 / 300, 84.66666666666667)
        with QtGui.QPainter(sample) as painter:
            DrawScaleBar(painter, plot, alternating, scale, "Meters")
        for fraction, ink in ((.0625, True), (.1875, False), (.375, True), (.75, False)):
            point = QtCore.QPointF(layout["bar"].left() + fraction * layout["bar"].width(), layout["bar"].center().y())
            role = "objectOutline" if ink else "canvas"
            assert sample.pixelColor(point.toPoint()) == QtGui.QColor(palette.themeColors[role]), fraction
        # Only individual labels get a backing; gaps stay transparent. Labels
        # and bar segments remain opaque with a transparent canvas color.
        sample.fill(QtCore.Qt.GlobalColor.transparent)
        with patch.dict(palette.themeColors, objectOutline = "#33343c42", canvas = "#00ffffff"):
            with QtGui.QPainter(sample) as painter:
                painter.setOpacity(.25)
                painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Multiply)
                DrawScaleBar(painter, plot, alternating, scale, "Meters")
                assert painter.opacity() == .25
                assert painter.compositionMode() == QtGui.QPainter.CompositionMode.CompositionMode_Multiply
            for fraction, color in ((.0625, "#343c42"), (.1875, "#ffffff"), (.375, "#343c42"), (.75, "#ffffff")):
                point = QtCore.QPointF(layout["bar"].left() + fraction * layout["bar"].width(), layout["bar"].center().y())
                assert sample.pixelColor(point.toPoint()) == QtGui.QColor(color), fraction
        paddingPoint = layout["rect"].topLeft() + QtCore.QPointF(1, 1)
        assert sample.pixelColor(paddingPoint.toPoint()).alpha() == 0
        gapPoint = QtCore.QPointF(layout["bar"].center().x(), layout["bar"].top() - 6)
        assert sample.pixelColor(gapPoint.toPoint()).alpha() == 0
        metrics = QtGui.QFontMetricsF(layout["font"])
        labelSamples = []
        for index in layout["visibleLabels"]:
            path, advance, height, ascent = TextPath(layout["labels"][index], layout["font"].toString(), sample.logicalDpiY())
            origin = QtCore.QPointF(layout["bar"].left() + layout["fractions"][index] * layout["bar"].width() - advance / 2,
                                   layout["rect"].top() + layout["padding"] + metrics.ascent())
            labelPad = layout["labelPadding"]
            point = origin + path.boundingRect().topLeft() - QtCore.QPointF(labelPad / 2, labelPad / 2)
            labelSamples.append(point)
            assert sample.pixelColor(point.toPoint()) == QtGui.QColor("#ffffff"), index
        betweenLabels = QtCore.QPointF(layout["bar"].left() + .35 * layout["bar"].width(), labelSamples[0].y())
        assert sample.pixelColor(betweenLabels.toPoint()).alpha() == 0
        data = QtCore.QByteArray()
        buffer = QtCore.QBuffer(data)
        assert buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        generator = QtSvg.QSvgGenerator()
        generator.setOutputDevice(buffer)
        generator.setSize(sample.size())
        generator.setViewBox(plot)
        with QtGui.QPainter(generator) as painter:
            painter.setFont(v.font())
            DrawScaleBar(painter, plot, alternating, scale, "Meters")
        buffer.close()
        renderer = QtSvg.QSvgRenderer(data)
        assert renderer.isValid()
        sample.fill(QtCore.Qt.GlobalColor.transparent)
        with QtGui.QPainter(sample) as painter:
            renderer.render(painter)
        assert sample.pixelColor(paddingPoint.toPoint()).alpha() == 0
        assert sample.pixelColor(betweenLabels.toPoint()).alpha() == 0
        for point in labelSamples:
            assert sample.pixelColor(point.toPoint()).alpha() == 255
        for fraction in (.0625, .1875, .375, .75):
            point = QtCore.QPointF(layout["bar"].left() + fraction * layout["bar"].width(), layout["bar"].center().y())
            assert sample.pixelColor(point.toPoint()).alpha() == 255, fraction
        # No powers-of-two totals are introduced at intermediate print scales.
        for denominator in range(100, 1001, 10):
            layout = ScaleBarLayout(plot, dict(divisionMode = "Progressive"), 300 * 1000 / (25.4 * denominator), "Meters", v.font())
            assert math.isclose(layout["distance"] / 5000, round(layout["distance"] / 5000)), denominator
            for index, distance in enumerate(layout["distances"]):
                assert math.isclose(layout["fractions"][index] * layout["bar"].width() / (300 * 1000 / (25.4 * denominator)) * 1000, distance)
        for denominator, labels in ((50, ["0", "0.5", "1", "2", "5 m"]),
                                    (100, ["0", "1", "2", "5", "10 m"]),
                                    (320, ["0", "5", "10", "20", "30 m"]),
                                    (640, ["0", "5", "10", "20", "50 m"])):
            layout = ScaleBarLayout(plot, dict(divisionMode = "Progressive"), 300 * 1000 / (25.4 * denominator), "Meters", v.font())
            assert layout["labels"] == labels, (denominator, layout["labels"])
            assert layout["visibleLabels"] == [0, 1, 2, 3, 4], (denominator, layout["visibleLabels"])
        for denominator in (10, 25, 50, 100, 150, 320, 640, 1280, 100000):
            scale = 300 * 1000 / (25.4 * denominator)
            for units in ("Meters", "Millimeters", "Feet and Inches", "Inches"):
                progressive = ScaleBarLayout(plot, dict(divisionMode = "Progressive"), scale, units, v.font())
                equal = ScaleBarLayout(plot, dict(divisionMode = "Equal"), scale, units, v.font())
                subdivided = ScaleBarLayout(plot, dict(divisionMode = "Subdivided"), scale, units, v.font())
                for styled in (equal, subdivided):
                    assert styled["bar"] == progressive["bar"] and styled["rect"] == progressive["rect"]
                    assert styled["labels"][-1] == progressive["labels"][-1]
                    assert styled["visibleLabels"][0] == 0 and styled["visibleLabels"][-1] == len(styled["labels"]) - 1
                    for fraction, distance in zip(styled["fractions"], styled["distances"]):
                        assert math.isclose(fraction * styled["bar"].width() / scale * 1000, distance, abs_tol = 1e-8)
                    for index in styled["visibleLabels"][:-1]:
                        assert not any(unit in styled["labels"][index] for unit in ("m", "ft", "in"))
                intervals = [end - start for start, end in zip(equal["distances"], equal["distances"][1:])]
                assert all(math.isclose(interval, intervals[0]) for interval in intervals)
                assert all(any(math.isclose(mark, value) for value in subdivided["distances"]) for mark in equal["distances"])
                assert len(subdivided["distances"]) > len(equal["distances"])
                assert all(mark < equal["distances"][1] or any(math.isclose(mark, value) for value in equal["distances"])
                           for mark in subdivided["distances"])
        for style, labels in (("Equal", ["0", "2", "4", "6", "8", "10 m"]),
                              ("Subdivided", ["0", "1", "2", "4", "6", "8", "10 m"])):
            styled = ScaleBarLayout(plot, dict(divisionMode = style), 300 * 1000 / (25.4 * 100), "Meters", v.font())
            assert styled["labels"] == labels
            assert styled["visibleLabels"] == list(range(len(labels)))
        # Align the zero mark horizontally to the actual world grid while
        # keeping the vertical inset fixed across all corners and appearances.
        positions = ("Bottom left", "Bottom right", "Top left", "Top right")
        for scale, units, major in ((100, "Meters", 1000), (250, "Millimeters", 500),
                                    (300 * 1000 / (25.4 * 100), "Meters", 1000),
                                    (300 * 1000 / (25.4 * 100), "Feet and Inches", 1219.2)):
            gridPlot = QtCore.QRectF(28, 28, 2000, 1500)
            bounds = (137, -263, gridPlot.width() * 1000 / scale, gridPlot.height() * 1000 / scale)
            gridOrigin = (311, -397)
            spacing = major * scale / 1000
            gridX = gridPlot.left() + (gridOrigin[0] - bounds[0]) * scale / 1000
            for position, divisionMode, style in ((position, divisionMode, style) for position in positions
                                                  for divisionMode in scaleBarDivisions for style in scaleBarStyles):
                options = dict(position = position, divisionMode = divisionMode, style = style)
                original = ScaleBarLayout(gridPlot, options, scale, units, v.font())
                aligned = ScaleBarLayout(gridPlot, options, scale, units, v.font(), bounds, gridOrigin)
                assert aligned["bar"].size() == original["bar"].size()
                assert aligned["labels"] == original["labels"] and aligned["distances"] == original["distances"]
                gridIndex = (aligned["bar"].left() - gridX) / spacing
                assert math.isclose(gridIndex, round(gridIndex), abs_tol = 1e-8)
                delta = aligned["bar"].topLeft() - original["bar"].topLeft()
                assert abs(delta.x()) < spacing + .01 and delta.y() == 0
                assert delta.x() <= .01 if position.endswith("right") else delta.x() >= -.01
                shiftedY = ScaleBarLayout(gridPlot, options, scale, units, v.font(), bounds, (gridOrigin[0], 1234))
                assert shiftedY["rect"] == aligned["rect"] and shiftedY["bar"] == aligned["bar"]
                assert gridPlot.contains(aligned["rect"])
                tightPlot = QtCore.QRectF(QtCore.QPointF(), original["minimum"])
                tightBounds = (*bounds[:2], tightPlot.width() * 1000 / scale, tightPlot.height() * 1000 / scale)
                originalTight = ScaleBarLayout(tightPlot, options, scale, units, v.font())
                alignedTight = ScaleBarLayout(tightPlot, options, scale, units, v.font(), tightBounds, gridOrigin)
                assert QtCore.QLineF(originalTight["bar"].topLeft(), alignedTight["bar"].topLeft()).length() < .02
                assert tightPlot.contains(alignedTight["rect"]), (position, divisionMode, style)
        for divisionMode, style in ((divisionMode, style) for divisionMode in scaleBarDivisions for style in scaleBarStyles):
            options = dict(enabled = True, divisionMode = divisionMode, style = style)
            scale = 300 * 1000 / (25.4 * 100)
            layout = ScaleBarLayout(plot, options, scale, "Meters", v.font())
            plain = ScaleBarLayout(plot, dict(divisionMode = divisionMode), scale, "Meters", v.font())
            assert layout["bar"].width() == plain["bar"].width() and layout["distances"] == plain["distances"]
            assert math.isclose(layout["bar"].height(), plain["bar"].height() * (2 if style == "Checker" else 1))
            sample.fill(QtCore.Qt.GlobalColor.transparent)
            with patch.dict(palette.themeColors, objectOutline = "#343c42", canvas = "#ffffff"):
                with QtGui.QPainter(sample) as painter:
                    painter.setFont(v.font())
                    DrawScaleBar(painter, plot, options, scale, "Meters")
                data = QtCore.QByteArray()
                buffer = QtCore.QBuffer(data)
                assert buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
                generator = QtSvg.QSvgGenerator()
                generator.setOutputDevice(buffer)
                generator.setSize(sample.size())
                generator.setViewBox(plot)
                with QtGui.QPainter(generator) as painter:
                    painter.setFont(v.font())
                    DrawScaleBar(painter, plot, options, scale, "Meters")
                buffer.close()
            svg = ElementTree.fromstring(bytes(data))
            assert not svg.findall(".//{http://www.w3.org/2000/svg}text")
            vector = QtGui.QImage(sample.size(), sample.format())
            vector.fill(QtCore.Qt.GlobalColor.transparent)
            with QtGui.QPainter(vector) as painter:
                QtSvg.QSvgRenderer(data).render(painter)
            for index, (start, end) in enumerate(zip(layout["fractions"], layout["fractions"][1:])):
                x = layout["bar"].left() + (start + end) / 2 * layout["bar"].width()
                if style == "Stepped":
                    stroke = layout["bar"].bottom() if index % 2 == 0 else layout["bar"].top()
                    opposite = layout["bar"].top() if index % 2 == 0 else layout["bar"].bottom()
                    for image in (sample, vector):
                        color = image.pixelColor(QtCore.QPointF(x, stroke).toPoint())
                        assert color.alpha() > 200 and color.red() == QtGui.QColor("#343c42").red(), (divisionMode, style, index)
                        assert image.pixelColor(QtCore.QPointF(x, opposite).toPoint()).alpha() == 0
                        assert image.pixelColor(QtCore.QPointF(x, layout["bar"].center().y()).toPoint()).alpha() == 0
                else:
                    rows = 2 if style == "Checker" else 1
                    for row in range(rows):
                        point = QtCore.QPointF(x, layout["bar"].top() + (row + .5) * layout["bar"].height() / rows).toPoint()
                        expected = QtGui.QColor("#343c42" if (index + row) % 2 == 0 else "#ffffff")
                        assert sample.pixelColor(point) == expected and vector.pixelColor(point) == expected, (divisionMode, style, row, index)
            if style == "Stepped":
                for fraction in layout["fractions"]:
                    point = QtCore.QPointF(layout["bar"].left() + fraction * layout["bar"].width(), layout["bar"].center().y()).toPoint()
                    assert sample.pixelColor(point).alpha() > 200 and vector.pixelColor(point).alpha() > 200
        for size in printPaperSizes:
            for orientation in ("Portrait", "Landscape"):
                for position in ("Right", "Bottom"):
                    page = PrintPageLayout(dict(pageSize = size, pageOrientation = orientation), 128,
                                           dict(enabled = True, position = position), "png")
                    plot = QtCore.QRectF(128, 128, *page["drawingPixels"])
                    for denominator in (26, 36, 75, 80, 150, 1280, 100000):
                        for units in ("Millimeters", "Feet and Inches"):
                            layout = ScaleBarLayout(plot, {},
                                                    300 * 1000 / (25.4 * denominator), units, v.font())
                            assert plot.contains(layout["rect"]), (size, orientation, position, units, denominator)
        for dpi in (150, 300, 600):
            arguments = panel.ExportJobs(folder / "density.png", "png")[0][1]
            image = RenderPlan(**dict(arguments, dpi = dpi))
            assert abs(image.dotsPerMeterX() * .0254 - dpi) < .02
        saved = main.BuildProjectData(includeHistory = False, includeActivity = False)
        for legacy, current in (("Progressive", "Progressive"), ("Equal divisions", "Equal"), ("Subdivided end", "Subdivided")):
            legacySaved = copy.deepcopy(saved)
            legacyOptions = legacySaved["settings"]["exportSettings"]["scaleBar"]
            legacyOptions.pop("divisionMode")
            legacyOptions["style"] = legacy
            decoded = DecodeProject(legacySaved, v.furnishingDefinitions)
            assert decoded[5]["exportSettings"]["scaleBar"] == {key: value for key, value in legacyOptions.items() if key != "style"} | dict(divisionMode = current, style = "Alternating")
        legacySaved = copy.deepcopy(saved)
        legacySaved["settings"]["exportSettings"]["scaleBar"].update(widthMM = 25, widthPixels = 80, divisions = 7)
        decoded = DecodeProject(legacySaved, v.furnishingDefinitions)
        assert decoded[5]["exportSettings"]["scaleBar"] == panel.overrides["scaleBar"]
        main.ApplyProject(decoded, None)
        assert not v.exportOverlay.active and main.sidebarTabs.currentWidget() is main.buildScrollArea
        assert panel.overrides["scaleBar"] == saved["settings"]["exportSettings"]["scaleBar"]
        assert panel.scaleBarDivisionMode.currentText() == "Subdivided"
        assert panel.scaleBarStyle.currentText() == "Stepped"
        assert panel.scaleBarPositionButtons[saved["settings"]["exportSettings"]["scaleBar"]["position"]].isChecked()
    print("Nine scale bar division/appearance combinations, calibrated distances, inverse checker rows, open stepped paths, PNG/SVG parity, undo, units and save/load passed")


if __name__ == "__main__":
    Main()
