"""Export title blocks preserve the drawing, survive save/load and stay out of the editor."""
import base64
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))

from PySide6 import QtCore, QtGui, QtSvg, QtTest, QtWidgets
from planner import MainWindow, Wall
from planner_app.export_plan import RenderPlan
from planner_app.export_settings import ExportPixelSize, NormalizeTitleBlock
from planner_app.graphics.title_block import TitleBlockLayout, TitleBlockCells, TitleBlockFont, DrawTitleBlock, DrawTitleBlockText, TitleBlockUnitScale
from planner_app.graphics import palette
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.project_codec import DecodeProject


def Main():
    with tempfile.TemporaryDirectory(dir = Path(__file__).parent) as folder:
        folder = Path(folder)
        os.environ["PLANNER_SESSION_PATH"] = str(folder / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(folder / "startup.plan")
        app = QtWidgets.QApplication([])
        ApplyApplicationTheme(app)
        main = MainWindow()
        main.projectPath = folder / "Smith Residence.plan"
        main.viewport.walls = [Wall(QtCore.QPointF(1000, 1000), QtCore.QPointF(6000, 1000), 240),
                               Wall(QtCore.QPointF(6000, 1000), QtCore.QPointF(6000, 8000), 240)]
        main.viewport.EnsureObjectIds()
        main.viewport.sceneRevision += 1
        main.show()
        panel = main.exportPanel
        main.sidebarTabs.setCurrentWidget(panel)
        panel.sectionButtons["Title Block"].setChecked(True)
        sections = list(panel.sectionButtons)
        assert sections.index("Title Block") + 1 == sections.index("Composite")
        assert not panel.titleBlockEnabled.isChecked() and not panel.titleBlockOptions.isEnabled()
        assert panel.titleBlockFields["sheetNumber"].text() == "0001"
        assert "scale" not in panel.titleBlockFields
        assert panel.titleBlockEnabled.text() == ""
        assert panel.titleBlockEnabled.accessibleName() == "Draw Title Block"
        assert panel.titleBlockEnableForm.horizontalSpacing() == 24
        assert panel.titleBlockFields["projectName"].text() == "Smith Residence"
        assert panel.titleBlockLogoMode.currentText() == "Planner"
        assert panel.titleBlockLogoOptions.isHidden()
        assert [panel.titleBlockLogoMode.itemText(index) for index in range(3)] == ["None", "Planner", "Custom"]
        main.projectPath = folder / "Renamed Project.plan"
        panel.RefreshControls()
        assert panel.titleBlockFields["projectName"].text() == "Renamed Project"

        panel.titleBlockEnabled.setChecked(True)
        assert panel.titleBlockOptions.isEnabled()
        dateField = panel.titleBlockFields["date"]
        assert isinstance(dateField, QtWidgets.QDateEdit) and dateField.calendarPopup()
        assert dateField.date() == QtCore.QDate.currentDate()
        chosenDate = QtCore.QDate(2026, 11, 15)
        dateField.setDate(chosenDate)
        assert panel.overrides["titleBlock"]["date"] == "2026-11-15"
        panel.RefreshControls()
        assert dateField.date() == chosenDate
        panel.titleBlockDateReset.click()
        assert dateField.date() == QtCore.QDate.currentDate()
        assert panel.overrides["titleBlock"]["date"] == QtCore.QDate.currentDate().toString(QtCore.Qt.DateFormat.ISODate)
        dateField.setDate(chosenDate)
        panel.scrollArea.ensureWidgetVisible(dateField)
        app.processEvents()
        QtTest.QTest.mouseClick(dateField, QtCore.Qt.MouseButton.LeftButton,
                               pos = QtCore.QPoint(dateField.width() - 10, dateField.height() // 2))
        app.processEvents()
        assert dateField.calendarWidget().isVisible(), "Date dropdown must open its calendar"
        dateField.calendarWidget().window().hide()
        field = panel.titleBlockFields["projectName"]
        field.setFocus()
        field.selectAll()
        QtTest.QTest.keyClicks(field, "Smith Residence")
        assert panel.overrides["titleBlock"]["projectName"] == "Smith Residence"
        panel.titleBlockFields["address"].setPlainText("12 Oak Street\nCape Town")
        panel.titleBlockFields["comments"].setPlainText("Proposed layout.\nVerify dimensions on site.")
        panel.SetTitleBlockOption("drawingTitle", "Ground Floor Plan")
        panel.SetTitleBlockOption("preparedBy", "ACME Architects")
        main.viewport.exportOverlay.bounds = (0, 0, 8000, 11000)
        panel.SetScale(100)
        panel.SetBorder("Plain")

        logo = QtGui.QImage(180, 90, QtGui.QImage.Format.Format_ARGB32)
        logo.fill(QtGui.QColor("#d92332"))
        logoPath = folder / "logo.png"
        assert logo.save(str(logoPath))
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value = ("", "")) as chooser:
            panel.titleBlockLogoMode.setCurrentText("Custom")
            chooser.assert_called_once()
        assert panel.titleBlockLogoMode.currentText() == "Planner"
        assert panel.titleBlockLogoOptions.isHidden()
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value = (str(logoPath), "")):
            panel.titleBlockLogoMode.setCurrentText("Custom")
        assert panel.titleBlockLogoName.text() == "logo.png"
        assert panel.titleBlockLogoMode.currentText() == "Custom"
        assert not panel.titleBlockLogoOptions.isHidden()
        for mode in ("None", "Planner"):
            panel.titleBlockLogoMode.setCurrentText(mode)
            assert panel.titleBlockLogoOptions.isHidden()
            assert panel.TitleBlockOptions()["logoMode"] == mode
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value = ("", "")):
            panel.titleBlockLogoMode.setCurrentText("Custom")
        assert panel.titleBlockLogoMode.currentText() == "Planner"
        assert panel.titleBlockLogoOptions.isHidden()
        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", return_value = (str(logoPath), "")):
            panel.titleBlockLogoMode.setCurrentText("Custom")
        logoPath.unlink()  # Embedded images must no longer depend on the source file.

        data = main.BuildProjectData(includeHistory = False, includeActivity = False)
        loaded = DecodeProject(json.loads(json.dumps(data)), main.viewport.furnishingDefinitions)
        assert loaded[5]["exportSettings"]["titleBlock"] == panel.overrides["titleBlock"]
        options = copy.deepcopy(panel.overrides["titleBlock"])
        assert base64.b64decode(options["logo"])
        for invalid in ({"enabled": 1}, {"position": "Left"}, {"projectName": 12}, {"logo": "bad!"}, {"logoMode": "Other"}):
            try:
                NormalizeTitleBlock(invalid)
            except ValueError:
                pass
            else:
                raise AssertionError(invalid)

        args = panel.RenderArguments("png")
        args["titleBlock"] = {}
        originalDrawingBounds = tuple(args["bounds"])
        original = RenderPlan(**args)
        diagnostics = root / "diagnostics" / "title-block"
        diagnostics.mkdir(parents = True, exist_ok = True)
        # Long unbroken words and blank paragraphs must fit without adding a
        # trailing newline. Inspect actual paint baselines inside the address cell.
        def RecordTitleText(painter, position, text):
            metrics = QtGui.QFontMetricsF(painter.font(), painter.device())
            painter.paintedText.append((text, painter.worldTransform().map(position), metrics, painter.worldTransform().m11()))
            DrawTitleBlockText(painter, position, text)

        for position in ("Right", "Bottom"):
            wrapOptions = dict(enabled = True, position = position, logoEnabled = False,
                               revision = "A", address = "jhlkajshdflkjahslkdjfhlkjahsdlkjfl" * 3 + "\nasdfjlaskjdlfkj\n\n\nasdf\nLAST ADDRESS LINE")
            width, height, block = TitleBlockLayout(1, 1, wrapOptions)
            addressCell = next(cell for name, label, value, cell in TitleBlockCells(block, wrapOptions, 100) if name == "address")
            image = QtGui.QImage(width, height, QtGui.QImage.Format.Format_RGB32)
            image.fill(QtCore.Qt.GlobalColor.white)
            painter = QtGui.QPainter(image)
            painter.paintedText = []
            with patch("planner_app.graphics.title_block.DrawTitleBlockText", side_effect = RecordTitleText):
                DrawTitleBlock(painter, block, wrapOptions, 100)
            painter.end()
            factor = TitleBlockUnitScale(100)
            pairedCells = {name: cell for name, label, value, cell in TitleBlockCells(block, wrapOptions, 100)}
            dateCell, scaleCell = pairedCells["date"], pairedCells["scale"]
            assert TitleBlockFont("date").pixelSize() == TitleBlockFont("scale").pixelSize() == TitleBlockFont("comments").pixelSize()
            for field in ("date", "scale", "revision"):
                cell = pairedCells[field]
                entries = [(text, point, metrics, fontScale) for text, point, metrics, fontScale in painter.paintedText
                           if cell.top() + 18 * factor <= point.y() < cell.bottom()
                           and cell.left() <= point.x() < cell.right()]
                assert entries
                for text, point, metrics, fontScale in entries:
                    assert abs(point.x() + metrics.horizontalAdvance(text) * fontScale - (cell.right() - 6 * factor)) < .01
            if position == "Right":
                assert dateCell.top() == scaleCell.top() and dateCell.bottom() == scaleCell.bottom()
                assert abs(dateCell.right() - scaleCell.left()) < .001
            else:
                assert dateCell.left() == scaleCell.left() and dateCell.right() == scaleCell.right()
                assert abs(dateCell.bottom() - scaleCell.top()) < .001
            addressText = [(text, point, metrics, fontScale) for text, point, metrics, fontScale in painter.paintedText
                           if addressCell.top() + 18 * factor <= point.y() < addressCell.bottom()
                           and addressCell.left() + 5 * factor < point.x() < addressCell.right()]
            assert any(text == "LAST ADDRESS LINE" for text, point, metrics, fontScale in addressText)
            for text, point, metrics, fontScale in addressText:
                assert point.y() + metrics.descent() * fontScale < addressCell.bottom() - 5 * factor, "Address clipped at the bottom"
                assert point.x() + metrics.horizontalAdvance(text.rstrip()) * fontScale <= addressCell.right() - 5 * factor, "Long address word clipped at the right"
            sheetCell = next(cell for name, label, value, cell in TitleBlockCells(block, wrapOptions, 100) if name == "sheetNumber")
            text, point, metrics, fontScale = next(item for item in painter.paintedText if item[0] == "0001")
            assert abs(point.x() + metrics.horizontalAdvance(text) * fontScale - (sheetCell.right() - 6 * factor)) < .01
            if position == "Bottom":
                assert abs(point.y() + metrics.descent() * fontScale - (sheetCell.bottom() - 6 * factor)) < factor
            image.save(str(diagnostics / f"address-wrap-{position.lower()}.png"))
            # Outer corners must be solid square joins, not white bevel wedges.
            for point in (QtCore.QPointF(block[0] + .5, block[1] + .5),
                          QtCore.QPointF(block[0] + block[2] - 1, block[1] + block[3] - 1)):
                assert image.pixelColor(int(point.x()), int(point.y())) == QtGui.QColor(palette.themeColors["rulerMajorTick"])
        for position in ("Right", "Bottom"):
            panel.titleBlockPositionButtons[position].click()
            assert panel.titleBlockPositionButtons[position].isChecked()
            assert sum(button.isChecked() for button in panel.titleBlockPositionButtons.values()) == 1
            assert panel.TitleBlockOptions()["position"] == position
            panel.RefreshControls()
            overlay = main.viewport.exportOverlay
            originalBounds = overlay.bounds
            for edge in range(4):
                overlay.bounds = originalBounds
                x, y, cropWidth, cropHeight = originalBounds
                opposite = (x + cropWidth, x, y + cropHeight, y)[edge]
                overlay.MoveEdge(edge, opposite + (100000 if edge % 2 == 0 else -100000),
                                 modifiers = QtCore.Qt.KeyboardModifier.AltModifier)
                cropPixels = ExportPixelSize(overlay.bounds, overlay.scale, overlay.borderSize if overlay.drawRuler else 0)
                layoutWidth, layoutHeight, minimumBlock = TitleBlockLayout(1, 1, overlay.titleBlock, overlay.scale,
                    overlay.architecturalScale, overlay.outputFormat, overlay.titleBlockDpi)
                assert cropPixels[0] >= minimumBlock[2] and cropPixels[1] >= minimumBlock[3], "Crop crossed the title block minimum"
                movedX, movedY, movedWidth, movedHeight = overlay.bounds
                assert abs((movedX + movedWidth if edge == 0 else movedX if edge == 1 else
                            movedY + movedHeight if edge == 2 else movedY) - opposite) < .001
            overlay.bounds = originalBounds
            panel.SetBounds(originalBounds)
            args = panel.RenderArguments("png")
            baseArgs = dict(args, titleBlock = {})
            drawing = RenderPlan(**baseArgs)
            result = RenderPlan(**args)
            baseWidth, baseHeight = ExportPixelSize(args["bounds"], args["scale"], args["borderSize"])
            expectedWidth, expectedHeight, block = TitleBlockLayout(baseWidth, baseHeight, args["titleBlock"], args["scale"])
            expected = (expectedWidth, expectedHeight)
            cells = TitleBlockCells(block, args["titleBlock"], args["scale"])
            logoCell = cells[0][3]
            assert cells[0][0] == "logo" and logoCell.width() != logoCell.height(), "Logo should fit its aspect ratio"
            commentCell = next(cell for name, label, value, cell in cells if name == "comments")
            if position == "Bottom":
                assert block[3] < 120 * TitleBlockUnitScale(args["scale"]), "Horizontal title block should be compact"
                widerBlock = (block[0], block[1], block[2] + 400, block[3])
                widerCells = {name: cell for name, label, value, cell in TitleBlockCells(widerBlock, args["titleBlock"], args["scale"])}
                originalCells = {name: cell for name, label, value, cell in cells}
                assert abs(widerCells["comments"].width() - commentCell.width() - 400) < .001
                assert widerCells["projectName"].width() == originalCells["projectName"].width()
                assert abs(widerCells["sheetNumber"].right() - (widerBlock[0] + widerBlock[2])) < .001
            assert (result.width(), result.height()) == expected
            assert result.copy(0, 0, drawing.width(), drawing.height()) == drawing, "Title block moved or changed the drawing"
            assert tuple(field.value() for field in panel.resolutionFields) == expected
            svg = panel.Render("svg")
            renderer = QtSvg.QSvgRenderer(svg)
            assert renderer.isValid() and renderer.viewBoxF().size().toSize() == result.size()
            assert not ElementTree.fromstring(svg).findall(".//{http://www.w3.org/2000/svg}text"), "SVG text should be outlined"
            sceneArgs = panel.RenderArguments("svg", preview = True, previewScene = True)
            sceneArgs["titleBlock"] = {}
            assert panel.Render("svg", preview = True, previewScene = True) == RenderPlan(**sceneArgs), "Title block leaked into scene cache"
            result.save(str(diagnostics / f"{position.lower()}.png"))
            (diagnostics / f"{position.lower()}.svg").write_bytes(svg)
            # Exercise the visible export preview, not only its scene cache.
            # PNG and SVG share the appended block while retaining their own
            # drawing caches and normal crop controls.
            v = main.viewport
            overlay = v.exportOverlay
            for fileType in ("PNG", "SVG"):
                panel.typeField.setCurrentIndex(panel.typeField.findData(fileType))
                app.processEvents()
                # Changing layout/format can expand the crop to the title block's minimum.
                args = panel.RenderArguments("png")
                result = RenderPlan(**args)
                factor = .45
                v.zoom = factor * panel.ScalePerMeter() / (1000 * v.basePixelsPerMillimeter)
                x, y, cropWidth, cropHeight = args["bounds"]
                cropTop = v.WorldToViewport(QtCore.QPointF(x, y + cropHeight))
                first = cropTop - QtCore.QPointF(args["borderSize"] * factor, args["borderSize"] * factor)
                v.panOffset += v.DrawingRect().topLeft() + QtCore.QPointF(20, 20) - first
                preview = v.grab().toImage()
                width, height = ExportPixelSize(args["bounds"], panel.ScalePerMeter(), args["borderSize"])
                outputWidth, outputHeight, block = TitleBlockLayout(width, height, args["titleBlock"])
                logoCenter = TitleBlockCells(block, args["titleBlock"], panel.ScalePerMeter())[0][3].center()
                sample = v.DrawingRect().topLeft() + QtCore.QPointF(20, 20) + logoCenter * factor
                assert preview.pixelColor(sample.toPoint()) == QtGui.QColor("#d92332"), f"Logo missing from {position} {fileType} preview"
                picture = overlay.titleBlockPicture
                bitmap = overlay.titleBlockImage
                if fileType == "PNG":
                    assert bitmap is not None and bitmap.size() == QtCore.QSize(int(block[2]), int(block[3]))
                    expectedBlock = result.copy(int(block[0]), int(block[1]), int(block[2]), int(block[3]))
                    assert bitmap == expectedBlock.convertToFormat(QtGui.QImage.Format.Format_ARGB32), "Raster preview must match exported title block pixels"
                    assert v.rasterCacheBudget.Entries()["titleBlock"] is bitmap
                else:
                    assert bitmap is None, "SVG preview should retain vector title block rendering"
                v.grab()
                assert overlay.titleBlockPicture is picture, "Panning/painting should reuse the title block"
                assert overlay.titleBlockImage is bitmap, "Viewing zoom should reuse the export-resolution bitmap"
                if fileType == "PNG":
                    class FilteringPainter(QtGui.QPainter):
                        def drawImage(self, *args):
                            self.filtering.append(self.testRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform))
                            super().drawImage(*args)

                    surface = QtGui.QImage(v.size(), QtGui.QImage.Format.Format_ARGB32)
                    surface.fill(QtCore.Qt.GlobalColor.transparent)
                    probePainter = FilteringPainter(surface)
                    probePainter.filtering = []
                    previousZoom = v.zoom
                    v.zoom = 4 * panel.ScalePerMeter() / (1000 * v.basePixelsPerMillimeter)
                    overlay.DrawTitleBlockPreview(probePainter, v.DrawingRect())
                    v.zoom = previousZoom
                    probePainter.end()
                    assert probePainter.filtering == [True], "Raster title block should filter at magnified zoom like the canvas"
                preview.save(str(diagnostics / f"preview-{position.lower()}-{fileType.lower()}.png"))
            panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        panel.SetTitleBlockOption("position", "Right")
        main.viewport.exportOverlay.bounds = (0, 0, 1, 1)
        panel.SetBounds((0, 0, 1, 1))
        tiny = panel.Render("png")
        assert tiny.height() > 200 and tiny.width() > 220
        previousLimit = main.viewport.viewportRasterByteLimit
        main.viewport.viewportRasterByteLimit = 64 * 1024
        main.viewport.grab()
        assert main.viewport.exportOverlay.titleBlockImage is not None
        assert main.viewport.rasterCacheBudget.RetainedBytes() <= main.viewport.viewportRasterByteLimit
        main.viewport.viewportRasterByteLimit = previousLimit
        panel.titleBlockLogoMode.setCurrentText("None")
        assert panel.overrides["titleBlock"]["logo"], "Disabling should retain the selected image"
        options = panel.TitleBlockOptions()
        width, height, block = TitleBlockLayout(1000, 1000, options)
        cells = TitleBlockCells(block, options, 100)
        assert cells[0][0] == "projectName", "Disabled logos must not reserve space"
        assert panel.titleBlockLogoOptions.isHidden()
        options["comments"] = ""
        options["position"] = "Right"
        width, height, block = TitleBlockLayout(1000, 1000, options)
        commentCell = next(cell for name, label, value, cell in TitleBlockCells(block, options, 100) if name == "comments")
        minimumHeight = 24 + 4 * QtGui.QFontMetricsF(TitleBlockFont("comments")).height()
        assert commentCell.height() >= minimumHeight * TitleBlockUnitScale(100)
        options["position"] = "Bottom"
        width, height, block = TitleBlockLayout(1000, 1000, options)
        assert not any(name == "comments" for name, label, value, cell in TitleBlockCells(block, options, 100))
        widerBlock = (block[0], block[1], block[2] + 400, block[3])
        cells = {name: cell for name, label, value, cell in TitleBlockCells(widerBlock, options, 100)}
        assert cells["spacer"].width() >= 400
        assert abs(cells["sheetNumber"].right() - (widerBlock[0] + widerBlock[2])) < .001
        previousFont = palette.labelFont
        originalText = panel.Render("png")
        main.viewport.grab()
        originalPicture = main.viewport.exportOverlay.titleBlockPicture
        palette.labelFont = "Arial"
        assert TitleBlockFont("comments").family() == "D-DIN Condensed"
        assert TitleBlockFont("comments", heading = True).family() == "Noto Sans"
        assert panel.Render("png") == originalText, "Canvas font changed title-block text"
        main.viewport.grab()
        assert main.viewport.exportOverlay.titleBlockPicture is originalPicture, "Canvas font invalidated the fixed title-block fonts"
        palette.labelFont = previousFont
        panel.titleBlockEnabled.setChecked(False)
        assert not panel.titleBlockOptions.isEnabled()
        main.viewport.exportOverlay.bounds = originalDrawingBounds
        panel.SetBounds(originalDrawingBounds)
        assert panel.Render("png") == original
        panel.titleBlockEnabled.setChecked(True)
        app.processEvents()
        panel.scrollArea.ensureWidgetVisible(panel.titleBlockPosition)
        app.processEvents()
        panel.titleBlockOptions.grab().save(str(diagnostics / "controls.png"))
        main.sidebarTabs.setCurrentIndex(0)
        app.processEvents()
        assert not main.viewport.exportOverlay.active
        assert main.viewport.exportOverlay.titleBlockPicture is None
        assert main.viewport.exportOverlay.titleBlockImage is None
        main.MarkProjectClean()
        main.close()
        app.processEvents()
    print("Export title block checks passed")


if __name__ == "__main__":
    Main()
